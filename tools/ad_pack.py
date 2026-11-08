"""Ad pack for the top promos of a run: one model call per promo.

  python tools/ad_pack.py <run_dir> [--top 5]      -> <run_dir>/ad_pack.json and ad_pack.md

For each promo: 3 post captions (to A/B test), 5 hashtags, a CTA, a recommended platform + length,
and the single question the viewer is left with. Uses the "captioner" role in models.yaml.
These are drafts for a human marketer; nothing here predicts performance (only the ad test does).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from promo_finder.adpack import ad_pack_for, to_markdown   # noqa: E402
from promo_finder.llm import LLM                            # noqa: E402
from promo_finder.parser import Block, Episode              # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir"); ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--config", default="models.yaml"); ap.add_argument("--profile")
    a = ap.parse_args()
    rd = Path(a.run_dir)
    ranked = json.loads((rd / "03_promos_ranked.json").read_text(encoding="utf-8"))
    raw = json.loads((rd / "00_episodes_parsed.json").read_text(encoding="utf-8"))
    episodes = {int(k): Episode(**{**d, "blocks": [Block(**b) for b in d["blocks"]]}) for k, d in raw.items()}
    llm = LLM(a.config, a.profile, cache_dir=rd.parent / "llm_cache")
    packs = []
    for p in ranked[:a.top]:
        packs.append(ad_pack_for(p, episodes, llm))
        print("ad pack", p["id"], "[cached]" if packs[-1]["cached"] else "")
    (rd / "ad_pack.json").write_text(json.dumps(packs, ensure_ascii=False, indent=1), encoding="utf-8")
    (rd / "ad_pack.md").write_text(to_markdown(packs), encoding="utf-8")
    print("wrote", rd / "ad_pack.md")


if __name__ == "__main__":
    main()
