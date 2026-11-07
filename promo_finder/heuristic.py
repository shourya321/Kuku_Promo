"""Keyword baseline: no AI at all.

Two jobs:
  1. A baseline to compare the LLM against (is the AI actually adding value?).
  2. An offline fallback so the tool still produces something if every API is down.

It scores each block with a small hand-written lexicon of microdrama "heat" words
and delivery tags, picks the hottest beats as hooks, and ends each clip on the most
cliffhanger-like beat 22-50 s later.
"""
from __future__ import annotations

import re

from .parser import Episode

HOOK_WORDS = {
    r"\bslap": 4, r"\bstrik": 3, r"\bpunch": 3, r"\bblood": 3, r"\bknife|\bdagger|\bblade": 3,
    r"\bpoison|\barsenic": 4, r"\bdead\b|\bdie\b|\bkill|\bmurder": 3, r"\bkiss": 2, r"\bscream": 2,
    r"\bgasp": 2, r"\bcollapse|\bfaint": 2, r"\bbetray": 3, r"\bliar\b|\blie[sd]?\b": 2,
    r"\bpregnan": 3, r"\bduke\b|\bduchess\b": 2, r"\bsecret": 2, r"\bhow dare": 3,
    r"\bmarry|\bmarrying|\bwedding|\bbride": 2, r"\bsister": 1, r"\bhumiliat|\bdisgrace|\bshame": 2,
    r"\bthrow|\bshove|\bgrab": 2, r"\bguard": 1, r"\bshocked|\bstunned": 2, r"\bdivorce": 3,
    r"\bnever\b": 1, r"\bfilth|\bwhore|\bbastard|\bbeggar|\bworthless": 3,
}
HOT_DELIVERY = r"furious|outrag|scream|shock|venom|cruel|menac|threat|gasp|sob|rage|enraged|horrif|vicious|seeth|cold|icy|mock|sneer|desperate|commanding"
CLIFF_WORDS = {r"cliffhanger": 5, r"ominous": 3, r"\bwho\b|\bwhat\b|\bwhy\b": 1, r"gasp": 2,
               r"shocked|stunned|frozen|freez": 2, r"door|enter|arriv|appear": 1, r"cut to black": 2}
RELATION = r"\bsister|\bfather|\bmother|\bhusband|\bwife|\bfianc|\bmarr|\bduke\b|\bduchess|\bson\b|\bdaughter|\bbride|\bgroom"
TROPE = r"\bmarr|\bwedding|\bbride|\bsister|\bduke\b|\bduchess|\bsecret|\bbetray|\brevenge|\bslap|\bhumiliat|\bpoison|\bheir"
VISUAL = r"slap|strik|punch|blood|knife|dagger|kiss|collapse|faint|fall|grab|shove|throw|tear|cry|weep|scream|fight"


def _score(text: str, table: dict) -> float:
    t = text.lower()
    return sum(w for pat, w in table.items() if re.search(pat, t))


def hook_score(b) -> float:
    s = _score(b.text, HOOK_WORDS)
    if b.kind == "DIALOGUE":
        if re.search(HOT_DELIVERY, b.delivery.lower()):
            s += 2
        s += 1.0 * b.text.count("!")
    if b.kind == "SFX":
        s += 1
    if b.kind == "CAMERA":
        s *= 0.5  # camera notes describe, they rarely ARE the moment
    return s


def cliff_score(b, ep: Episode) -> float:
    s = _score(b.text + " " + b.delivery, CLIFF_WORDS)
    if b.kind == "DIALOGUE" and "?" in b.text:
        s += 1.5
    if b.end >= ep.duration - 2.5:
        s += 2  # authored episode cliffhanger
    return s + 0.3 * hook_score(b)


def mine_episode(ep: Episode, k: int = 3) -> dict:
    """Produces the SAME JSON shape the LLM miner returns, so the rest of the pipeline is shared."""
    scored = sorted(((hook_score(b), b) for b in ep.blocks if b.kind != "CAMERA"), key=lambda x: -x[0])
    hooks = []
    for s, b in scored:
        if s <= 0:
            break
        if all(abs(b.start - h.start) > 20 for _, h in hooks) and b.start <= ep.duration - 22:
            hooks.append((s, b))
        if len(hooks) == k:
            break
    cands = []
    for s, h in hooks:
        ends = [b for b in ep.blocks if h.start + 22 <= b.end <= h.start + 50 and b.kind != "CAMERA"]
        if not ends:
            continue
        cb = max(ends, key=lambda b: cliff_score(b, ep))
        cands.append({
            "title": f"Ep{ep.number} beat at {int(h.start)}s",
            "segments": [{"start_block": h.id, "end_block": cb.id}],
            "hook_block": h.id, "hook": h.text[:140], "hook_type": "keyword",
            "cliffhanger_block": cb.id, "cliffhanger": cb.text[:140], "open_question": "",
            "why": f"keyword heat {s:.0f}, cliff score {cliff_score(cb, ep):.1f}",
            "trope": "", "standalone_risk": "", "spoiler_risk": "low",
            "strength": max(1, min(10, round(s))),
        })
    return {"episode_summary": ep.logline, "candidates": cands, "moments": []}


def judge_text(text: str) -> dict:
    """Rubric scores (1-5) from keywords only - the baseline 'judge'."""
    lines = text.split("\n")
    first = " ".join(l for l in lines if l.startswith("(+ 0") or l.startswith("(+ 1") or l.startswith("(+ 2"))
    last = " ".join(lines[-4:])
    t = text.lower()

    def c(x, lo=0, hi=8):
        return int(max(1, min(5, 1 + 4 * (x - lo) / (hi - lo))))
    return {
        "hook": c(_score(first, HOOK_WORDS) + first.count("!")),
        "cliffhanger": c(_score(last, CLIFF_WORDS) + last.count("?"), 0, 6),
        "standalone": c(len(set(re.findall(RELATION, t))), 0, 4),
        "trope": c(len(set(re.findall(TROPE, t))), 0, 5),
        "visual": c(len(re.findall(VISUAL, t)), 0, 6),
        "critique": "keyword baseline",
    }
