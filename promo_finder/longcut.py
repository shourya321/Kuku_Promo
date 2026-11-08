"""Long cuts (90 s - 3 min) for paid user acquisition.

Microdrama UA also runs longer "story" ads. Episodes here are about 2 minutes, so a 90-180 s ad has to
span episodes. Instead of asking a model for new timestamps, a long cut CHAINS promos that already
passed every rule (hook in the first 3 s, clean cuts, cliffhanger end), in story order:

    model (1 call): picks 2-6 valid promo ids that tell one arc, first = strongest hook, last = cliffhanger
    code: unknown ids rejected, story order + no overlap enforced, total 90-180 s, every cut re-checked

So the long cut inherits the hook-first and clean-cut guarantees of its parts. What it cannot guarantee
is that the jumps between parts are followable; the stranger test measures that.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .parser import Episode, fmt, is_clean_cut

LONG_MIN, LONG_MAX = 90.0, 180.0


class LongPick(BaseModel):
    title: str
    clip_ids: list[str] = Field(min_length=2, max_length=6)
    hook: str
    cliffhanger: str
    why: str


class LongOut(BaseModel):
    cuts: list[LongPick] = Field(default_factory=list)


LONG_SYSTEM = """You edit LONG paid-acquisition ads (90 seconds to 3 minutes) for a microdrama app.
You get a list of short promo clips that are already cut and approved (each opens on a hook and ends on a
cliffhanger). Chain 2-6 of them, in STORY ORDER, into one long ad that a stranger can follow as one arc:
- the FIRST clip must have the most scroll-stopping hook of the chain
- the chain should build (setup -> escalation -> turn) and the LAST clip must end on an unresolved cliffhanger
- prefer clips from consecutive or nearby episodes about the same conflict, so the jumps are easy to follow
- the sum of the clip lengths MUST be 90-180 seconds (check the lengths given)
- no spoilers of the show's biggest late twist unless the arc needs it
Use ONLY the clip ids given, in story order (episode order). Propose up to 4 different long cuts.
Return ONLY JSON: {"cuts": [{"title": "...", "clip_ids": ["E01-P2", "E02-P1"], "hook": "...", "cliffhanger": "...", "why": "..."}]}"""


def listing(promos: list[dict]) -> str:
    rows = []
    for p in sorted(promos, key=lambda x: (x["episode"], x["segments"][0]["start"])):
        rows.append(f"{p['id']} | episode {p['episode']} | {p['duration']:.0f}s | {p.get('trope', '')} | "
                    f"HOOK: {p.get('hook', '')} | CLIFF: {p.get('cliffhanger', '')}")
    return "\n".join(rows)


def build(pick: dict, by_id: dict[str, dict], episodes: dict[int, Episode], cid: str) -> dict:
    """Turn a model pick into a long cut, or reject it with reasons. All checks are code."""
    reasons, flags, clips = [], [], []
    for raw in pick["clip_ids"]:
        k = str(raw).strip().upper()
        p = by_id.get(k)
        if p is None:
            reasons.append(f"unknown or invalid clip id {raw}")
        elif any(c["id"] == k for c in clips):
            reasons.append(f"clip {k} used twice")
        else:
            clips.append(p)
    for a, b in zip(clips, clips[1:]):
        if (b["episode"], b["segments"][0]["start"]) < (a["episode"], a["segments"][0]["start"]):
            reasons.append(f"{b['id']} comes before {a['id']} in the story")
    segs = [dict(s) for c in clips for s in c["segments"]]
    # Every segment must play strictly forward in story time: no repeated footage, no flash-forwards.
    # (Checked per segment, not per clip: a "cold open" promo jumps back inside itself.)
    for x, y in zip(segs, segs[1:]):
        if y["episode"] == x["episode"] and y["start"] < x["end"] - 0.01:
            reasons.append(f"repeats or rewinds footage at E{y['episode']:02d} {y['start_tc']}")
            break
    merged = []
    for s in segs:                       # join parts that touch, so the EDL has no 0-second jump cuts
        if merged and merged[-1]["episode"] == s["episode"] and 0 <= s["start"] - merged[-1]["end"] <= 0.5:
            merged[-1]["end"], merged[-1]["end_tc"] = s["end"], s["end_tc"]
        else:
            merged.append(s)
    for s in merged:
        for t in (s["start"], s["end"]):
            if not is_clean_cut(episodes[s["episode"]], t):
                reasons.append(f"cut at E{s['episode']:02d} {fmt(t)} lands mid-line")
    dur = round(sum(s["end"] - s["start"] for s in merged), 2)
    if clips and not (LONG_MIN - 0.01 <= dur <= LONG_MAX + 0.01):
        reasons.append(f"length {dur:.0f}s outside 90-180s")
    if len(clips) < 2:
        reasons.append("needs at least 2 valid clips")
    eps = sorted({c["episode"] for c in clips})
    if eps:
        flags.append(f"spans episodes {eps[0]}-{eps[-1]} ({len(eps)} used)")
        gaps = [b - a for a, b in zip(eps, eps[1:]) if b - a > 1]
        if gaps:
            flags.append(f"skips {sum(g - 1 for g in gaps)} episode(s) between parts")
    return {"id": cid, "title": pick.get("title"), "hook": pick.get("hook"), "cliffhanger": pick.get("cliffhanger"),
            "why": pick.get("why"), "parts": [c["id"] for c in clips], "segments": merged, "duration": dur,
            "hook_offset": clips[0]["hook_offset"] if clips else None, "episode": None,
            "flags": flags, "reject_reasons": reasons, "status": "rejected" if reasons else "ok"}
