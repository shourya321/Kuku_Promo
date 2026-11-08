"""Blind rating sheet for a head-to-head pool, and scoring of a filled sheet.

  python tools/blind_sheet.py make  <pool.json> <run_dir> <out_dir>
      -> blind_sheet.csv + blind_sheet.md (give to raters: script text only, shuffled, ids C01..)
      -> blind_key.csv (keep hidden: which system made each clip)
  python tools/blind_sheet.py score <filled.csv> <out_dir> --rater "name" [--judged eval_comparison_clips.json]
      -> per-system means, % "would post", and agreement with each model judge on the same clips

The rater column is free text so the result says WHO rated: a human, or an AI rater (which is then just
another model's opinion, not a human ground truth).
"""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from promo_finder.assemble import clip_text                # noqa: E402
from promo_finder.parser import Block, Episode             # noqa: E402
from promo_finder.stats import pair_agreement, spearman    # noqa: E402

DIMS = ("hook_1to5", "cliffhanger_1to5", "makes_sense_alone_1to5")
GROUP_NAMES = {"KW": "keyword baseline", "RND": "random clips", "V1": "v1 AI picks", "V2": "v2 AI picks", "AI": "AI picks"}
RUBRIC = """Rate each clip from its script only (what would be seen and heard, in order, with time from the clip start).
- hook_1to5: do the first 3 seconds stop a scroll? 5 = slap / shocking line / reveal at once, 1 = slow setup
- cliffhanger_1to5: does it end on an unresolved peak? 5 = you must know what happens, 1 = resolved or flat
- makes_sense_alone_1to5: would a stranger who never saw the show follow who is against whom? 5 = clear, 1 = lost
- would_post_yes_no: would you spend ad money on this clip as it is?"""


def make(pool_file, run_dir, out_dir, seed=2026):
    pool = json.loads(Path(pool_file).read_text(encoding="utf-8"))
    raw = json.loads((Path(run_dir) / "00_episodes_parsed.json").read_text(encoding="utf-8"))
    episodes = {int(k): Episode(**{**d, "blocks": [Block(**b) for b in d["blocks"]]}) for k, d in raw.items()}
    random.Random(seed).shuffle(pool)       # a fresh order: not the order any model judge saw
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    md = ["# Blind rating sheet", "", RUBRIC, ""]
    with open(out / "blind_sheet.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["clip", "length_s", "script", *DIMS, "would_post_yes_no", "note"])
        for i, p in enumerate(pool, 1):
            text = clip_text(episodes, p, with_rel_time=True)
            w.writerow([f"C{i:02d}", round(p["duration"]), text, "", "", "", "", ""])
            md += [f"## C{i:02d} ({p['duration']:.0f}s)", "```", text, "```", ""]
    (out / "blind_sheet.md").write_text("\n".join(md), encoding="utf-8")
    with open(out / "blind_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["clip", "pool_id"])
        for i, p in enumerate(pool, 1):
            w.writerow([f"C{i:02d}", p["id"]])
    print(f"wrote {len(pool)} clips to {out / 'blind_sheet.csv'} (+ .md); key in blind_key.csv (do not show raters)")


def overall(r):
    v = [float(r[k]) for k in DIMS if str(r.get(k, "")).strip()]
    return round(sum((x - 1) / 4 for x in v) / len(v) * 100, 1) if v else None


def score(filled, out_dir, rater, judged=None):
    out = Path(out_dir)
    key = {r["clip"]: r["pool_id"] for r in csv.DictReader(open(out / "blind_key.csv", encoding="utf-8"))}
    rows = [r for r in csv.DictReader(open(filled, encoding="utf-8-sig")) if r["clip"] in key]
    by_id = {key[r["clip"]]: r for r in rows}
    groups = {}
    for pid, r in by_id.items():
        groups.setdefault(pid.split("-")[0], []).append(r)
    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    res = {"rater": rater, "clips_rated": len(rows), "by_system": {}}
    for g, rs in sorted(groups.items()):
        res["by_system"][GROUP_NAMES.get(g, g)] = {
            **{k: mean([float(r[k]) for r in rs if r[k].strip()]) for k in DIMS},
            "would_post_pct": round(100 * sum(r["would_post_yes_no"].strip().lower().startswith("y") for r in rs) / len(rs)),
            "overall_0_100": mean([overall(r) for r in rs if overall(r) is not None]), "n": len(rs)}
    if judged:   # same clips, model judges' scores (5-dim rubric, 0-100): how much does this rater agree?
        from promo_finder.pipeline import Run
        res["agreement_with_model_judges"] = {}
        clips = json.loads(Path(judged).read_text(encoding="utf-8"))
        names = sorted({n for c in clips for n in c.get("judges", {})})
        for n in names:
            ids = [c["id"] for c in clips if c["judges"].get(n) and c["id"] in by_id and overall(by_id[c["id"]]) is not None]
            js = {c["id"]: Run.score({"judge": c["judges"][n]}) for c in clips if c["id"] in ids}
            x, y = [overall(by_id[i]) for i in ids], [js[i] for i in ids]
            res["agreement_with_model_judges"][n] = {"clips": len(ids), "spearman_rho": spearman(x, y), **pair_agreement(x, y)}
    (out / "blind_sheet_result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "score"]); ap.add_argument("args", nargs="+")
    ap.add_argument("--rater", default="human"); ap.add_argument("--judged"); ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    if a.cmd == "make":
        make(*a.args[:3], seed=a.seed)
    else:
        score(a.args[0], a.args[1], a.rater, a.judged)
