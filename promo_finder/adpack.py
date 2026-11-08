"""Ad pack for top promos: 3 A/B post captions, 5 hashtags, a CTA, platform + length, viewer question.

One model call per promo (role "captioner"). Drafts for a human marketer; nothing here predicts
performance (only an ad test does). Used by tools/ad_pack.py and the app.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .assemble import clip_text


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


def ad_pack_for(p: dict, episodes: dict, llm) -> dict:
    user = (f"TITLE: {p.get('title')}\nLENGTH: {p['duration']:.0f}s\nHOOK: {p.get('hook')}\n"
            f"CLIFFHANGER: {p.get('cliffhanger')}\nON-SCREEN CAPTION: {p.get('context_caption', '')}\n\n"
            f"CLIP SCRIPT:\n{clip_text(episodes, p, with_rel_time=False)}")
    obj, meta = llm.json("captioner", SYSTEM, user, AdPack, temperature=0.5, tag=f"adpack_{p['id']}")
    return {"rank": p.get("rank"), "id": p["id"], "title": p.get("title"), **obj.model_dump(),
            "model": meta["model"], "cached": bool(meta.get("cached"))}


def to_markdown(packs: list[dict]) -> str:
    md = [f"# Ad pack: top {len(packs)} promos", ""]
    for pack in packs:
        md += [f"## #{pack['rank']} {pack.get('title')} ({pack['id']})",
               *[f"- Caption {'ABC'[i]}: {c}" for i, c in enumerate(pack['post_captions'])],
               f"- Hashtags: {' '.join(pack['hashtags'])}", f"- CTA: {pack['cta']}",
               f"- Platform: {pack['platform']} · length {pack['recommended_length_s']}s",
               f"- Viewer is left asking: {pack['viewer_question']}", ""]
    return "\n".join(md)
