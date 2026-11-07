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

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from promo_finder.assemble import clip_text          # noqa: E402
from promo_finder.llm import LLM                     # noqa: E402
from promo_finder.parser import Block, Episode       # noqa: E402


class AdPack(BaseModel):
    post_captions: list[str] = Field(min_length=3, max_length=3)
    hashtags: list[str] = Field(min_length=5, max_length=5)
    cta: str
    platform: str
    recommended_length_s: int
    viewer_question: str


SYSTEM = """You are a performance marketer for a microdrama app (short vertical dramas, US audience).
For the promo clip below, write an ad pack:
- post_captions: 3 DIFFERENT post captions to A/B test (each under 120 characters; one curiosity, one emotional, one direct)
- hashtags: 5 hashtags (mix broad like #dramatok with trope-specific ones)
- cta: one call to action that sends people to the app to keep watching
- platform: the best first platform (TikTok, Instagram Reels or YouTube Shorts) and why, in one short phrase
- recommended_length_s: the clip length you would post (it can be the clip's own length)
- viewer_question: the single question the viewer is left with
No spoilers beyond the clip. Return ONLY JSON with exactly these keys."""


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
    packs, md = [], [f"# Ad pack: top {a.top} promos", ""]
    for p in ranked[:a.top]:
        user = (f"TITLE: {p.get('title')}\nLENGTH: {p['duration']:.0f}s\nHOOK: {p.get('hook')}\n"
                f"CLIFFHANGER: {p.get('cliffhanger')}\nON-SCREEN CAPTION: {p.get('context_caption', '')}\n\n"
                f"CLIP SCRIPT:\n{clip_text(episodes, p, with_rel_time=False)}")
        obj, meta = llm.json("captioner", SYSTEM, user, AdPack, temperature=0.5, tag=f"adpack_{p['id']}")
        pack = {"rank": p["rank"], "id": p["id"], "title": p.get("title"), **obj.model_dump(), "model": meta["model"]}
        packs.append(pack)
        md += [f"## #{p['rank']} {p.get('title')} ({p['id']}, {p['duration']:.0f}s)",
               *[f"- Caption {'ABC'[i]}: {c}" for i, c in enumerate(pack['post_captions'])],
               f"- Hashtags: {' '.join(pack['hashtags'])}", f"- CTA: {pack['cta']}",
               f"- Platform: {pack['platform']} · length {pack['recommended_length_s']}s",
               f"- Viewer is left asking: {pack['viewer_question']}", ""]
        print("ad pack", p["id"], "[cached]" if meta.get("cached") else "")
    (rd / "ad_pack.json").write_text(json.dumps(packs, ensure_ascii=False, indent=1), encoding="utf-8")
    (rd / "ad_pack.md").write_text("\n".join(md), encoding="utf-8")
    print("wrote", rd / "ad_pack.md")


if __name__ == "__main__":
    main()
