"""Long cuts (90 s - 3 min) for paid UA, built from a finished run's valid promos.

  python tools/long_cut.py <run_dir> [--no-stranger]
      -> <run_dir>/long_cuts.json, long_cuts.md, long_cuts_edl.csv

1 model call (role "montage") picks chains of already-valid promos; code checks order, overlap, length
and every cut (promo_finder/longcut.py). Each valid long cut then gets the same stranger test as the
short promos (role "cold_viewer", 1 call each), so "can a stranger follow the jumps?" is measured, not assumed.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from promo_finder import prompts as P                       # noqa: E402
from promo_finder.assemble import clip_text                 # noqa: E402
from promo_finder.llm import LLM                            # noqa: E402
from promo_finder.longcut import LONG_SYSTEM, LongOut, build, listing  # noqa: E402
from promo_finder.parser import Block, Episode              # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir"); ap.add_argument("--config", default="models.yaml"); ap.add_argument("--profile")
    ap.add_argument("--no-stranger", action="store_true", help="skip the stranger test (saves 1 call per cut)")
    a = ap.parse_args()
    rd = Path(a.run_dir)
    cands = json.loads((rd / "02_all_candidates.json").read_text(encoding="utf-8"))
    raw = json.loads((rd / "00_episodes_parsed.json").read_text(encoding="utf-8"))
    episodes = {int(k): Episode(**{**d, "blocks": [Block(**b) for b in d["blocks"]]}) for k, d in raw.items()}
    # single-episode promos only, and no "flash-forward cold open" promos: they jump back in time inside
    # themselves, which a story-order long cut must not do (longcut.build rejects it anyway)
    valid = [c for c in cands if c["status"] == "ok" and c.get("episode")
             and not any("cold open" in f for f in c.get("flags", []))]
    by_id = {c["id"].upper(): c for c in valid}
    premise = " / ".join(episodes[n].logline for n in sorted(episodes)[:3])
    llm = LLM(a.config, a.profile, cache_dir=rd.parent / "llm_cache")

    user = f"PREMISE (episodes 1-3): {premise}\n\nAPPROVED CLIPS ({len(valid)}):\n{listing(valid)}"
    obj, meta = llm.json("montage", LONG_SYSTEM, user, LongOut, temperature=0.4, tag="longcut")
    cuts = [build(pk.model_dump(), by_id, episodes, f"LONG-{i}") for i, pk in enumerate(obj.cuts, 1)]
    for c in cuts:
        c["source"] = meta["model"]
    ok = [c for c in cuts if c["status"] == "ok"]
    print(f"long cuts: {len(cuts)} proposed, {len(ok)} valid [{meta['model']}{' cached' if meta.get('cached') else ''}]")

    if not a.no_stranger:
        for c in ok:
            text = clip_text(episodes, c, with_rel_time=False, kinds=("ACTION", "DIALOGUE", "SFX", "CAMERA"))
            try:
                co, cm = llm.json("cold_viewer", P.COLD_SYSTEM, f"VIDEO SCRIPT:\n{text}", P.ColdOut,
                                  temperature=0.0, tag=f"cold_{c['id']}")
                c["cold"] = {**co.model_dump(), "model": cm["model"]}
            except Exception as e:
                c["flags"].append(f"stranger test failed: {str(e)[:80]}")

    (rd / "long_cuts.json").write_text(json.dumps(cuts, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(rd / "long_cuts_edl.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["long_cut", "segment", "episode", "start", "end", "length_s"])
        for c in ok:
            for k, s in enumerate(c["segments"], 1):
                w.writerow([c["id"], k, s["episode"], s["start_tc"], s["end_tc"], round(s["end"] - s["start"], 2)])
    md = ["# Long cuts (90 s - 3 min)", "",
          f"{len(cuts)} proposed by {meta['model']}, {len(ok)} passed the code checks.", ""]
    for c in cuts:
        md.append(f"## {c['id']} {c['title']} ({c['duration']:.0f}s, {c['status']})")
        md.append(f"- **Parts:** {' -> '.join(c['parts'])}")
        md.append(f"- **Segments:** " + " + ".join(f"E{s['episode']:02d} {s['start_tc']}-{s['end_tc']}" for s in c["segments"]))
        md += [f"- **Hook:** {c['hook']}", f"- **Cliffhanger:** {c['cliffhanger']}", f"- **Why:** {c['why']}"]
        if c.get("cold"):
            cc = c["cold"]
            md.append(f"- **Stranger test:** \"{cc['what_is_happening']}\" (clarity {cc['clarity']}/5, keep watching "
                      f"{cc['keep_watching']}/5)" + (f"; confused by: {', '.join(cc['confusing'])}" if cc["confusing"] else ""))
        if c["flags"]:
            md.append(f"- **Flags:** {', '.join(c['flags'])}")
        if c["reject_reasons"]:
            md.append(f"- **Rejected:** {'; '.join(c['reject_reasons'])}")
        md.append("")
    (rd / "long_cuts.md").write_text("\n".join(md), encoding="utf-8")
    print("wrote", rd / "long_cuts.md")


if __name__ == "__main__":
    main()
