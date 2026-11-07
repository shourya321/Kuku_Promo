"""Quality check for a finished run.

  python evaluate.py outputs/<run>                       # rule checks + stats (free, no API)
  python evaluate.py outputs/<run> --vs-baseline          # + blind comparison: AI picks vs keyword picks vs random clips,
                                                          #   all scored by the same judge/cold-viewer models
  python evaluate.py outputs/<run> --human-sheet          # + blind rating sheet for 1-3 humans
  python evaluate.py outputs/<run> --score-human ratings.csv

There is no ground truth for "best promo", so we triangulate:
  1. hard rules (hook <= 3 s, 20-60 s, no mid-line cuts) - must be 100%
  2. coverage / diversity / episode-ending bias
  3. a "stranger" model that only sees the clip: did it understand it?
  4. AI picks vs a keyword baseline vs random clips, judged blind by the same model
  5. blind human ratings (directional at this sample size)
"""
import argparse
import csv
import json
import random
import statistics as st
from pathlib import Path

from promo_finder.assemble import clip_text, overlap_ratio
from promo_finder.parser import fmt, is_clean_cut, load_show, shot_boundaries
from promo_finder.pipeline import Run
from promo_finder.policy import trope_family


def load(run_dir):
    r = Path(run_dir)
    ranked = json.loads((r / "03_promos_ranked.json").read_text(encoding="utf-8"))
    allc = json.loads((r / "02_all_candidates.json").read_text(encoding="utf-8"))
    summary = json.loads((r / "run_summary.json").read_text(encoding="utf-8"))
    return ranked, allc, summary


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 2) if xs else None


def rule_checks(ranked, episodes):
    res = {"hook_within_3s": 0, "length_20_60": 0, "no_midline_cut": 0}
    for p in ranked:
        res["hook_within_3s"] += 0 <= p.get("hook_offset", 99) <= 3.01
        res["length_20_60"] += 20 <= p["duration"] <= 60.01
        res["no_midline_cut"] += all(is_clean_cut(episodes[s["episode"]], t) for s in p["segments"] for t in (s["start"], s["end"]))
    n = len(ranked) or 1
    return {k: f"{v}/{len(ranked)} ({100 * v / n:.0f}%)" for k, v in res.items()}


def random_clips(episodes, n, seed=7):
    """Random valid 20-60 s windows that start and end on clean shot boundaries."""
    rng, out = random.Random(seed), []
    eps = list(episodes.values())
    while len(out) < n:
        ep = rng.choice(eps)
        pts = [t for t in shot_boundaries(ep) if is_clean_cut(ep, t)]
        s = rng.choice(pts)
        ends = [t for t in pts if 25 <= t - s <= 45]
        if not ends:
            continue
        e = rng.choice(ends)
        out.append({"id": f"RND-{len(out) + 1}", "source": "random", "segments": [
            {"episode": ep.number, "start": s, "end": e, "start_tc": fmt(s), "end_tc": fmt(e)}],
            "duration": round(e - s, 2), "flags": [], "reject_reasons": [], "status": "ok", "episode": ep.number})
    return out


GROUP_NAMES = {"AI": "AI picks", "KW": "keyword baseline", "RND": "random 25-45s clips",
               "V1": "v1 AI picks", "V2": "v2 AI picks"}   # V1/V2: head-to-head pool (tools/make_h2h_pool.py)
# Groq free tier allows few tokens per minute, so its judge gets small batches and a slow pace.
JUDGE_PACE = {"groq": {"rpm": 3, "batch": 4}}


def judge_only_score(j: dict | None) -> float | None:
    """0-100 from the 5 rubric scores only (no stranger test), so two judges are compared like for like."""
    return Run.score({"judge": j}) if j else None


def compare_judges(pool, episodes, llm, a, rd):
    """Score the same blind pool with every judge in --judges, then measure how much the judges agree.

    One judge from the same model family as the miner could share its blind spots ("grading its own
    homework"). If a judge from a different family ranks AI > keyword > random too, the result is sturdier."""
    from promo_finder.stats import pair_agreement, spearman
    pool = [dict(p) for p in pool]
    for p in pool:
        p.pop("judge", None)
    r = Run.__new__(Run)                       # a Run without a show folder: we only need judge()/cold()
    r.episodes, r.mode, r.errors = episodes, "llm", []
    r.log = lambda s: print(s); r.progress = lambda *x: None
    r.llm = llm
    r.cold([p for p in pool if not p.get("cold")])   # stranger test once (default profile); cached if reused

    by_judge, scores, judged = {}, {}, {}
    for spec in a.judges.split(","):
        prov, model = spec.strip().split(":", 1)
        pace = JUDGE_PACE.get(prov, {})
        llm.roles = {**llm.roles, "judge": {"provider": prov, "model": model, "rpm": pace.get("rpm", 8)}}
        clips = [dict(p) for p in pool]
        r.llm = llm
        r.judge(clips, batch=pace.get("batch", 8))
        name = f"{prov}:{model}"
        scores[name] = {p["id"]: judge_only_score(p.get("judge")) for p in clips}
        groups = {}
        for p in clips:
            groups.setdefault(p["id"].split("-")[0], []).append(p)
        by_judge[name] = {GROUP_NAMES.get(g, g): {k: mean([p.get("judge", {}).get(k) for p in ps])
                                           for k in ("hook", "cliffhanger", "standalone", "trope", "visual")}
                          | {"stranger_clarity": mean([p.get("cold", {}).get("clarity") for p in ps]),
                             "stranger_keep_watching": mean([p.get("cold", {}).get("keep_watching") for p in ps]),
                             "overall_score_0_100": mean([Run.score(p) for p in ps]),
                             "scored": sum(1 for p in ps if p.get("judge"))}
                          for g, ps in sorted(groups.items())}
        o = {g: v["overall_score_0_100"] or 0 for g, v in by_judge[name].items()}
        kw, rnd = o.get("keyword baseline", 0), o.get("random 25-45s clips", 0)
        for ai in ("AI picks", "v1 AI picks", "v2 AI picks"):
            if ai in o:
                by_judge[name][f"_ordering_{ai}>KW>RND"] = o[ai] > kw > rnd
        for p in clips:
            judged.setdefault(p["id"], {})[name] = p.get("judge")

    names = list(scores)
    agreement = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ids = [c for c in scores[names[i]] if scores[names[i]][c] is not None and scores[names[j]].get(c) is not None]
            x, y = [scores[names[i]][c] for c in ids], [scores[names[j]][c] for c in ids]
            agreement[f"{names[i]} vs {names[j]}"] = {"clips": len(ids), "spearman_rho": spearman(x, y), **pair_agreement(x, y)}
    for p in pool:
        p["judges"] = judged.get(p["id"], {})    # every judge's scores, side by side, per clip
    (rd / "eval_comparison_clips.json").write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"by_judge": by_judge, "judge_agreement": agreement,
            "ordering_holds_under_all_judges": all(x for v in by_judge.values() for k, x in v.items() if k.startswith("_ordering"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--input", help="show folder/zip (default: re-use parsed episodes from the run)")
    ap.add_argument("--vs-baseline", action="store_true")
    ap.add_argument("--baseline-run", help="a heuristic run folder (default: computed on the fly)")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--config", default="models.yaml")
    ap.add_argument("--judges", default="gemini:gemini-flash-lite-latest,groq:llama-3.3-70b-versatile",
                    help="comma list of provider:model; every judge scores the same blind clips")
    ap.add_argument("--reuse-pool", help="eval_comparison_clips.json from an earlier evaluation: re-score those exact clips")
    ap.add_argument("--human-sheet", action="store_true")
    ap.add_argument("--score-human")
    a = ap.parse_args()
    rd = Path(a.run_dir)
    ranked, allc, summary = load(rd)

    # episodes: re-parse from the dump
    from promo_finder.parser import Episode, Block
    raw = json.loads((rd / "00_episodes_parsed.json").read_text(encoding="utf-8"))
    episodes = {}
    for k, d in raw.items():
        blocks = [Block(**b) for b in d.pop("blocks")]
        episodes[int(k)] = Episode(**d, blocks=blocks)

    m = {"run": str(rd), "mode": summary["mode"], "models": summary["models"]}
    top = ranked[:a.n]
    m["candidates_total"] = summary["candidates_total"]
    m["candidates_valid"] = summary["candidates_valid"]
    m["reject_reasons"] = summary["rejected_by_reason"]
    m["rule_checks_ranked"] = rule_checks(ranked, episodes)
    m["distinct_episodes_in_top10"] = len({s["episode"] for p in top for s in p["segments"]})
    m["top10_ending_on_episode_final_beat"] = sum(bool(p.get("ends_on_episode_end")) for p in top)
    valid = [c for c in allc if c["status"] == "ok"]
    m["valid_ending_on_episode_final_beat_pct"] = round(100 * sum(bool(c.get("ends_on_episode_end")) for c in valid) / max(1, len(valid)), 1)
    covered = {c["episode"] for c in valid if c.get("ends_on_episode_end")}
    m["authored_episode_cliffhangers_found"] = f"{len(covered)}/{len(episodes)}"
    m["multi_segment_promos_ranked"] = sum(len(p["segments"]) > 1 for p in ranked)
    m["auto_fixed_ranked"] = sum(any("cold open" in f or "compressed" in f or "moved" in f or "trimmed" in f for f in p.get("flags", [])) for p in ranked)
    cold = [p["cold"] for p in ranked if p.get("cold")]
    if cold:
        m["stranger_test"] = {"tested": len(cold), "mean_clarity_5": mean([c["clarity"] for c in cold]),
                              "mean_keep_watching_5": mean([c["keep_watching"] for c in cold]),
                              "confused_clips(clarity<=2)": sum(c["clarity"] <= 2 for c in cold)}
    m["ranker_consistency"] = summary.get("ranker_consistency", summary.get("ranker_order_consistency_spearman"))
    m["repair_loop"] = summary.get("repair_loop")
    m["ranked_with_repeated_footage"] = f"{sum('flash-forward cold open' in p.get('flags', []) for p in ranked)}/{len(ranked)}"
    m["top10_distinct_trope_families"] = len({trope_family(p.get("trope", "")) for p in top})
    m["top10_max_per_episode"] = max([sum(1 for q in top if q.get("episode") == p.get("episode")) for p in top] or [0])
    capped = [p for p in ranked if p.get("cold") and p.get("cold_captioned")]
    if capped:
        m["caption_effect_same_clips"] = {
            "clips": len(capped),
            "clarity_without": mean([p["cold"]["clarity"] for p in capped]),
            "clarity_with_caption": mean([p["cold_captioned"]["clarity"] for p in capped]),
            "keep_watching_without": mean([p["cold"]["keep_watching"] for p in capped]),
            "keep_watching_with_caption": mean([p["cold_captioned"]["keep_watching"] for p in capped]),
            "clips_with_confusing_items_without": sum(bool(p["cold"].get("confusing")) for p in capped),
            "clips_with_confusing_items_with_caption": sum(bool(p["cold_captioned"].get("confusing")) for p in capped)}
    m["llm_usage"] = summary.get("llm_stats", {}).get("by_model")

    if a.vs_baseline:
        from promo_finder.llm import LLM
        llm = LLM(a.config, a.profile, cache_dir=rd.parent / "llm_cache")
        pool_file = rd / "eval_comparison_clips.json"
        if a.reuse_pool:  # re-score the exact same blind clips (e.g. v1's) with other judges
            pool = json.loads(Path(a.reuse_pool).read_text(encoding="utf-8"))
            m["blind_comparison"] = compare_judges(pool, episodes, llm, a, rd)
            m["blind_comparison_same_judge"] = next(iter(m["blind_comparison"]["by_judge"].values()))
            pool = None
        elif a.baseline_run:
            base = json.loads((Path(a.baseline_run) / "03_promos_ranked.json").read_text(encoding="utf-8"))[:a.n]
        else:
            from promo_finder import heuristic
            from promo_finder.assemble import assemble
            bc = []
            for ep in episodes.values():
                for j, c in enumerate(heuristic.mine_episode(ep)["candidates"], 1):
                    c["id"] = f"KW-E{ep.number:02d}-{j}"; bc.append(assemble(ep, c))
            bc = [c for c in bc if c["status"] == "ok"]
            for c in bc:
                c["kwscore"] = sum(heuristic.judge_text(clip_text(episodes, c))[k] for k in ("hook", "cliffhanger", "standalone", "trope", "visual"))
            bc.sort(key=lambda c: -c["kwscore"])
            base = []
            for c in bc:
                if all(overlap_ratio(c, b) < 0.3 for b in base):
                    base.append(c)
                if len(base) == a.n:
                    break
        if not a.reuse_pool:
            for i, b in enumerate(base, 1):
                b["id"] = f"KW-{i}"
            rnd = random_clips(episodes, a.n)
            ai = [dict(p, id=f"AI-{i}") for i, p in enumerate(top, 1)]
            for p in ai:
                p.pop("judge", None); p.pop("cold", None)
            pool = ai + base + rnd
            random.Random(1).shuffle(pool)  # blind: the judge never sees which system made a clip
            m["blind_comparison"] = compare_judges(pool, episodes, llm, a, rd)
            m["blind_comparison_same_judge"] = next(iter(m["blind_comparison"]["by_judge"].values()))

    if a.human_sheet:
        rnd = random_clips(episodes, a.n, seed=11)
        pool = [dict(p, key="AI") for p in top] + [dict(p, key="RANDOM") for p in rnd]
        random.Random(3).shuffle(pool)
        with open(rd / "human_rating_sheet.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["clip", "segments", "script", "hook_1to5", "cliffhanger_1to5", "makes_sense_alone_1to5", "would_post_yes_no"])
            for i, p in enumerate(pool, 1):
                w.writerow([f"C{i:02d}", " + ".join(f"E{s['episode']} {s['start_tc']}-{s['end_tc']}" for s in p["segments"]),
                            clip_text(episodes, p, with_rel_time=True), "", "", "", ""])
        with open(rd / "human_rating_key.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["clip", "source", "id"])
            for i, p in enumerate(pool, 1):
                w.writerow([f"C{i:02d}", p["key"], p.get("id")])
        print("Wrote human_rating_sheet.csv (give to raters) and human_rating_key.csv (keep hidden).")

    if a.score_human:
        key = {r["clip"]: r["source"] for r in csv.DictReader(open(rd / "human_rating_key.csv", encoding="utf-8"))}
        rows = list(csv.DictReader(open(a.score_human, encoding="utf-8-sig")))
        res = {}
        for r in rows:
            g = key.get(r["clip"])
            for k in ("hook_1to5", "cliffhanger_1to5", "makes_sense_alone_1to5"):
                if r.get(k, "").strip():
                    res.setdefault(g, {}).setdefault(k, []).append(float(r[k]))
            if r.get("would_post_yes_no", "").strip():
                res.setdefault(g, {}).setdefault("would_post", []).append(r["would_post_yes_no"].strip().lower().startswith("y"))
        m["human_blind_rating"] = {g: {k: round(st.mean(v), 2) for k, v in d.items()} | {"n": len(d.get("hook_1to5", []))}
                                   for g, d in res.items()}

    (rd / "eval_metrics.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# Evaluation: {rd.name}", "", "```json", json.dumps(m, ensure_ascii=False, indent=2), "```"]
    (rd / "eval_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(m, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
