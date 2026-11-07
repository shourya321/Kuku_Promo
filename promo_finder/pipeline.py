"""End-to-end run: parse -> mine -> assemble/filter -> montage -> judge -> cold viewer -> rank -> outputs."""
from __future__ import annotations

import csv
import re
import json
import random
import time
from pathlib import Path

from . import heuristic, prompts as P
from .assemble import assemble, clip_text, dedupe, norm_id, snap
from .parser import Episode, fmt, is_clean_cut, load_show

WEIGHTS = {"hook": 0.25, "cliffhanger": 0.20, "standalone": 0.20, "trope": 0.15, "visual": 0.10, "keep_watching": 0.10}


def norm_clip_id(x) -> str:
    """Models sometimes echo ids as "CLIP E09-P1", "id: e09-p1" etc. Normalise before matching."""
    return re.sub(r"^\s*(clip|id)[\s:#]*", "", str(x), flags=re.I).strip().upper()


def _now():
    return time.strftime("%H:%M:%S")


class Run:
    def __init__(self, show_input, out_dir, llm=None, mode="llm", judge_top=40, cold_top=15,
                 rank_top=12, max_eps=None, montage=True, log=print, progress=None):
        self.show, eps = load_show(show_input)
        if max_eps:
            eps = eps[:max_eps]
        self.episodes: dict[int, Episode] = {e.number: e for e in eps}
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.llm, self.mode = llm, mode
        self.judge_top, self.cold_top, self.rank_top = judge_top, cold_top, rank_top
        self.do_montage = montage and mode == "llm"
        # "w", not "a": a rerun into the same folder must not mix its log with an older run's log
        self.logf = open(self.out / "run_log.txt", "w", encoding="utf-8")
        self._log, self.progress = log, progress or (lambda *a: None)
        if llm is not None:
            llm.log = self.log  # model retries/fallbacks also go into run_log.txt
        self.errors: list[str] = []
        self.t0 = time.time()

    def log(self, msg):
        line = f"[{_now()}] {msg}"
        self._log(line)
        self.logf.write(line + "\n"); self.logf.flush()

    def dump(self, name, obj):
        (self.out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------ stages
    def mine(self) -> tuple[list[dict], list[dict]]:
        cands, moments, mined_raw = [], [], {}
        eps = list(self.episodes.values())
        for i, ep in enumerate(eps):
            self.progress("mine", i, len(eps))
            if self.mode == "heuristic":
                out = heuristic.mine_episode(ep)
                meta = {"model": "keyword-baseline"}
            else:
                prev = self.episodes.get(ep.number - 1)
                try:
                    obj, meta = self.llm.json("miner", P.MINER_SYSTEM, P.miner_user(self.show, ep, prev.logline if prev else ""),
                                              P.MinerOut, temperature=0.3, tag=f"miner_E{ep.number:02d}")
                    out = obj.model_dump()
                except Exception as e:
                    self.errors.append(f"miner E{ep.number}: {e}")
                    self.log(f"E{ep.number:02d}: miner failed ({str(e)[:120]}) -> keyword fallback")
                    out, meta = heuristic.mine_episode(ep), {"model": "keyword-fallback"}
            mined_raw[ep.number] = {"meta": meta, **out}
            for j, c in enumerate(out["candidates"], 1):
                c = dict(c); c["id"] = f"E{ep.number:02d}-P{j}"; c["source"] = meta["model"]
                cands.append(assemble(ep, c))
            for j, m in enumerate(out.get("moments", []), 1):
                mm = self._moment(ep, m, f"E{ep.number:02d}-M{j}")
                if mm:
                    moments.append(mm)
            ok = sum(1 for c in cands if c["episode"] == ep.number and c["status"] == "ok")
            self.log(f"E{ep.number:02d}: {len(out['candidates'])} candidates ({ok} valid), "
                     f"{len(out.get('moments', []))} moments [{meta['model']}{' cached' if meta.get('cached') else ''}]")
        self.dump("01_mined_raw.json", mined_raw)
        return cands, moments

    def _moment(self, ep, m, mid):
        a, b = norm_id(ep, m.get("start_block")), norm_id(ep, m.get("end_block"))
        if not a or not b:
            return None
        s, e = ep.block(a).start, max(ep.block(a).end, ep.block(b).end)
        s = snap(ep, s, s - 1.0, s + 0.5) if not is_clean_cut(ep, s) else s
        e = snap(ep, e, e, e + 1.5) if e is not None else None
        if s is None or e is None or not (2.0 <= e - s <= 15.0):
            return None
        return {"id": mid, "episode": ep.number, "start": round(s, 2), "end": round(e, 2),
                "duration": round(e - s, 2), "label": m.get("label", ""), "kind": m.get("kind", "")}

    def montages(self, moments: list[dict]) -> list[dict]:
        if not self.do_montage or len(moments) < 3:
            return []
        moments = moments[:60]
        short = {f"M{i + 1:02d}": m for i, m in enumerate(moments)}
        listing = "\n".join(f"{k}: episode {m['episode']}, {m['duration']:.1f}s, {m['kind']} - {m['label']}"
                            for k, m in short.items())
        premise = " / ".join(self.episodes[n].logline for n in sorted(self.episodes)[:3])
        user = f"SHOW: {self.show}\nPREMISE (episodes 1-3): {premise}\n\nMOMENTS:\n{listing}"
        try:
            obj, meta = self.llm.json("montage", P.MONTAGE_SYSTEM, user, P.MontageOut, temperature=0.4, tag="montage")
        except Exception as e:
            self.errors.append(f"montage: {e}"); self.log(f"montage failed: {str(e)[:120]}")
            return []
        out = []
        for i, mp in enumerate(obj.montages, 1):
            ms = [short.get(x.strip()) for x in mp.moment_ids]
            p = {"id": f"MONTAGE-{i}", "source": meta["model"], "title": mp.title, "hook": mp.hook,
                 "cliffhanger": mp.cliffhanger, "why": mp.why, "trope": "montage", "hook_type": "montage",
                 "open_question": "", "standalone_risk": "", "spoiler_risk": "medium", "strength": 6,
                 "flags": ["cross-episode montage"], "reject_reasons": [], "episode": None}
            if any(m is None for m in ms):
                p["reject_reasons"].append(f"unknown moment id in {mp.moment_ids}")
                ms = [m for m in ms if m]
            for a_i, a in enumerate(ms):
                for b in ms[a_i + 1:]:
                    if a["episode"] == b["episode"] and min(a["end"], b["end"]) > max(a["start"], b["start"]):
                        p["reject_reasons"].append(f"moments {a['id']} and {b['id']} overlap")
            if len({m["episode"] for m in ms}) < 2:
                p["flags"].append("montage uses a single episode")
            p["segments"] = [{"episode": m["episode"], "start": m["start"], "end": m["end"],
                              "start_tc": fmt(m["start"]), "end_tc": fmt(m["end"])} for m in ms]
            p["duration"] = round(sum(m["duration"] for m in ms), 2)
            p["hook_offset"] = 0.0
            p["ends_on_episode_end"] = False
            if not (20 <= p["duration"] <= 60):
                p["reject_reasons"].append(f"montage length {p['duration']}s outside 20-60s")
            p["status"] = "rejected" if p["reject_reasons"] else "ok"
            out.append(p)
        self.log(f"montage: {len(out)} proposed, {sum(p['status'] == 'ok' for p in out)} valid")
        return out

    def shortlist(self, valid: list[dict], n: int, per_ep: int = 2, ep_end_quota: float = 0.4) -> list[dict]:
        """Top-n by miner strength, max per_ep per episode, max 40% ending on an episode's final beat."""
        out, per, ends = [], {}, 0
        for p in sorted(valid, key=lambda x: (-x.get("strength", 0), x["id"])):
            e = p.get("episode") or "montage"
            if per.get(e, 0) >= per_ep:
                continue
            if p.get("ends_on_episode_end") and ends >= ep_end_quota * n:
                continue
            out.append(p); per[e] = per.get(e, 0) + 1; ends += bool(p.get("ends_on_episode_end"))
            if len(out) >= n:
                break
        return out

    def judge(self, items: list[dict]):
        batch = 8
        for i in range(0, len(items), batch):
            chunk = items[i:i + batch]
            self.progress("judge", i, len(items))
            if self.mode == "heuristic":
                for p in chunk:
                    p["judge"] = heuristic.judge_text(clip_text(self.episodes, p))
                continue
            payload = [(p["id"], clip_text(self.episodes, p)) for p in chunk]
            try:
                obj, meta = self.llm.json("judge", P.JUDGE_SYSTEM, P.judge_user(payload), P.JudgeOut,
                                          temperature=0.0, tag=f"judge_{i // batch + 1:02d}")
                # Fall back to position when the reply has exactly one score per clip.
                got = {norm_clip_id(s.id): s.model_dump() for s in obj.scores}
                positional = len(obj.scores) == len(chunk)
                for k, p in enumerate(chunk):
                    sc = got.get(norm_clip_id(p["id"])) or (obj.scores[k].model_dump() if positional else None)
                    if sc:
                        p["judge"] = {**sc, "model": meta["model"]}
                    else:
                        self.errors.append(f"judge skipped {p['id']}")
                self.log(f"judge batch {i // batch + 1}: {len(got)}/{len(chunk)} scored [{meta['model']}]")
            except Exception as e:
                self.errors.append(f"judge batch {i}: {e}")
                self.log(f"judge batch failed: {str(e)[:120]} -> keyword judge")
                for p in chunk:
                    p["judge"] = {**heuristic.judge_text(clip_text(self.episodes, p)), "model": "keyword-fallback"}

    def cold(self, items: list[dict]):
        if self.mode == "heuristic":
            return
        for i, p in enumerate(items):
            self.progress("cold viewer", i, len(items))
            text = clip_text(self.episodes, p, with_rel_time=False, kinds=("ACTION", "DIALOGUE", "SFX", "CAMERA"))
            try:
                obj, meta = self.llm.json("cold_viewer", P.COLD_SYSTEM, f"VIDEO SCRIPT:\n{text}", P.ColdOut,
                                          temperature=0.0, tag=f"cold_{p['id']}")
                p["cold"] = {**obj.model_dump(), "model": meta["model"]}
            except Exception as e:
                self.errors.append(f"cold {p['id']}: {e}")
        self.log(f"cold viewer: {sum('cold' in p for p in items)}/{len(items)} tested")

    @staticmethod
    def score(p: dict) -> float:
        j = p.get("judge")
        if not j:
            return 0.0
        standalone = j["standalone"]
        kw = None
        if p.get("cold"):
            standalone = (j["standalone"] + p["cold"]["clarity"]) / 2
            kw = p["cold"]["keep_watching"]
        parts = {"hook": j["hook"], "cliffhanger": j["cliffhanger"], "standalone": standalone,
                 "trope": j["trope"], "visual": j["visual"], "keep_watching": kw}
        wsum = sum(w for k, w in WEIGHTS.items() if parts[k] is not None)
        s = sum(WEIGHTS[k] * (parts[k] - 1) / 4 for k in WEIGHTS if parts[k] is not None) / wsum * 100
        if str(p.get("spoiler_risk", "")).lower() == "high":
            s -= 5
        if any("cold open" in f or "compressed" in f for f in p.get("flags", [])):
            s -= 2  # needs an editor's eye
        return round(s, 1)

    def rank(self, items: list[dict]):
        """Two ranking calls in different orders; average the positions (detects position bias)."""
        if self.mode == "heuristic" or len(items) < 3:
            return None
        def describe(p):
            j = p.get("judge", {}); c = p.get("cold", {})
            return (f"{p['id']} | {p['duration']:.0f}s | trope: {p.get('trope', '')} | HOOK: {p.get('hook', '')} | "
                    f"CLIFF: {p.get('cliffhanger', '')} | judge h{j.get('hook')}/c{j.get('cliffhanger')}/s{j.get('standalone')} | "
                    f"stranger understood: {c.get('what_is_happening', 'n/a')} (keep watching {c.get('keep_watching', 'n/a')}/5)")
        orders, reasons = [], {}
        for k, seq in enumerate([items, list(reversed(items))]):
            user = "SHORTLIST:\n" + "\n".join(describe(p) for p in seq)
            try:
                obj, meta = self.llm.json("ranker", P.RANK_SYSTEM, user, P.RankOut, temperature=0.0, tag=f"rank_{'AB'[k]}")
                ids = [r.id.strip() for r in obj.order if r.id.strip() in {p["id"] for p in items}]
                ids += [p["id"] for p in items if p["id"] not in ids]
                orders.append(ids)
                for r in obj.order:
                    reasons.setdefault(r.id.strip(), r.reason)
            except Exception as e:
                self.errors.append(f"rank {k}: {e}")
        if not orders:
            return None
        pos = {p["id"]: sum(o.index(p["id"]) for o in orders) / len(orders) for p in items}
        for p in items:
            p["rank_reason"] = reasons.get(p["id"], "")
            p["rank_positions"] = [o.index(p["id"]) + 1 for o in orders]
        consistency = None
        if len(orders) == 2:
            n = len(items)
            d2 = sum((orders[0].index(i) - orders[1].index(i)) ** 2 for i in pos)
            consistency = round(1 - 6 * d2 / (n * (n * n - 1)), 3)  # Spearman rho
        return sorted(items, key=lambda p: (pos[p["id"]], -p["score"])), consistency

    # ------------------------------------------------------------ main
    def run(self) -> dict:
        self.log(f"Show: {self.show} | {len(self.episodes)} episodes | mode={self.mode}"
                 + (f" | models={self.llm.describe()}" if self.llm else ""))
        self.dump("00_episodes_parsed.json", {n: e.to_dict() for n, e in self.episodes.items()})

        cands, moments = self.mine()
        cands += self.montages(moments)
        self.dump("01b_moments.json", moments)
        valid = [c for c in cands if c["status"] == "ok"]
        dedupe(valid)
        valid = [c for c in valid if c["status"] == "ok"]
        self.log(f"candidates: {len(cands)} total, {len(valid)} valid after filters+dedupe")

        short = self.shortlist(valid, self.judge_top)
        self.judge(short)
        for p in short:
            p["score"] = self.score(p)
        short.sort(key=lambda p: -p["score"])
        self.cold(short[:self.cold_top])
        for p in short:
            p["score"] = self.score(p)
        short.sort(key=lambda p: -p["score"])

        consistency = None
        top = short[:self.rank_top]
        r = self.rank(top)
        if r:
            top, consistency = r
        final = top + short[self.rank_top:]
        for i, p in enumerate(final, 1):
            p["rank"] = i

        self.dump("02_all_candidates.json", cands)
        self.dump("03_promos_ranked.json", final)
        summary = self.write_tables(final, cands, consistency)
        self.logf.close()
        return summary

    # ------------------------------------------------------------ outputs
    def write_tables(self, final, cands, consistency):
        def segs_str(p):
            return " + ".join(f"E{s['episode']:02d} {s['start_tc']}-{s['end_tc']}" for s in p["segments"])
        cols = ["rank", "id", "title", "segments", "duration_s", "hook", "hook_offset_s", "cliffhanger",
                "open_question", "why", "trope", "score", "hook_5", "cliff_5", "standalone_5", "trope_5", "visual_5",
                "stranger_clarity_5", "stranger_keep_watching_5", "stranger_understood", "flags", "rank_reason",
                "judge_critique", "source"]
        with open(self.out / "promos_ranked.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(cols)
            for p in final:
                j, c = p.get("judge", {}), p.get("cold", {})
                w.writerow([p["rank"], p["id"], p.get("title"), segs_str(p), p["duration"], p.get("hook"),
                            p.get("hook_offset"), p.get("cliffhanger"), p.get("open_question"), p.get("why"),
                            p.get("trope"), p.get("score"), j.get("hook"), j.get("cliffhanger"), j.get("standalone"),
                            j.get("trope"), j.get("visual"), c.get("clarity"), c.get("keep_watching"),
                            c.get("what_is_happening"), "; ".join(p.get("flags", [])), p.get("rank_reason", ""),
                            j.get("critique", ""), p.get("source")])
        with open(self.out / "edit_decision_list.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["rank", "promo_id", "segment", "episode", "start", "end", "length_s"])
            for p in final:
                for k, s in enumerate(p["segments"], 1):
                    w.writerow([p["rank"], p["id"], k, s["episode"], s["start_tc"], s["end_tc"], round(s["end"] - s["start"], 2)])
        with open(self.out / "rejected_candidates.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["id", "status", "reasons", "title", "hook", "source"])
            for p in cands:
                if p["status"] != "ok":
                    w.writerow([p["id"], p["status"], "; ".join(p["reject_reasons"]), p.get("title"), p.get("hook"), p.get("source")])

        md = [f"# Promo picks: {self.show}", "",
              f"Mode: {self.mode}. Episodes: {len(self.episodes)}. Ranked promos: {len(final)}.", ""]
        for p in final[:25]:
            j, c = p.get("judge", {}), p.get("cold", {})
            md += [f"## #{p['rank']} {p.get('title')}  ({p['id']}, score {p.get('score')})",
                   f"- **Segments:** {segs_str(p)}  ({p['duration']:.1f}s)",
                   f"- **Hook (+{p.get('hook_offset', 0):.1f}s):** {p.get('hook')}",
                   f"- **Cliffhanger:** {p.get('cliffhanger')}",
                   f"- **Why it works:** {p.get('why')}"]
            if p.get("rank_reason"):
                md.append(f"- **Why post here:** {p['rank_reason']}")
            if j:
                md.append(f"- **Judge:** hook {j.get('hook')}/5, cliff {j.get('cliffhanger')}/5, standalone {j.get('standalone')}/5, "
                          f"trope {j.get('trope')}/5, visual {j.get('visual')}/5. {j.get('critique', '')}")
            if c:
                md.append(f"- **Stranger test:** \"{c.get('what_is_happening')}\" (clarity {c.get('clarity')}/5, "
                          f"keep watching {c.get('keep_watching')}/5)" + (f"; confused by: {', '.join(c['confusing'])}" if c.get("confusing") else ""))
            if p.get("flags"):
                md.append(f"- **Flags:** {', '.join(p['flags'])}")
            md.append("")
        (self.out / "promos_ranked.md").write_text("\n".join(md), encoding="utf-8")

        stats = self.llm.stats if self.llm else {}
        summary = {"show": self.show, "mode": self.mode, "episodes": len(self.episodes),
                   "models": self.llm.describe() if self.llm else {"all": "keyword-baseline"},
                   "candidates_total": len(cands),
                   "candidates_valid": sum(c["status"] == "ok" for c in cands),
                   "rejected_by_reason": _reason_counts(cands),
                   "ranked": len(final), "ranker_order_consistency_spearman": consistency,
                   "llm_stats": stats, "errors": self.errors, "runtime_s": round(time.time() - self.t0, 1)}
        self.dump("run_summary.json", summary)
        self.log(f"done in {summary['runtime_s']}s -> {self.out}")
        return summary


def _reason_counts(cands):
    out = {}
    for c in cands:
        for r in c.get("reject_reasons", []):
            key = r.split("(")[0].split(" at ")[0].split(" in ")[0].strip()
            key = "overlaps another promo" if key.startswith("overlaps") else key
            out[key] = out.get(key, 0) + 1
    return out
