"""Final-list policy: plain-code rules applied AFTER the model ranking.

Why: in v1, 5 of the top 10 ended on an episode's final beat (the writers' authored cliffhanger).
Those are good clips, but a test batch of 10 near-identical "end of episode" promos teaches the
UA team little. This greedy re-rank (MMR-style: take the best clip that still keeps the list
diverse) keeps the ranker's order wherever the rules allow it.
"""
from __future__ import annotations

import re

# 9 trope families. The miner writes tropes as free text ("jilted bride / secret Duke"),
# so we map them to families with keywords. First match wins, so order matters.
TROPE_FAMILIES = [
    ("secret identity", r"secret|hidden|disguis|identity|undercover|true heir|real (father|parent)|duke"),
    ("betrayal", r"betray|cheat|affair|backstab|two-?tim"),
    ("villain exposed", r"villain|expos|scheme|plot|frame|lie|liar|truth"),
    ("revenge / comeback", r"reveng|comeback|face-?slap|payback|vengeance|turn the tables|rise"),
    ("marriage / bride", r"bride|wedding|marri|contract|engag|groom|jilt|altar"),
    ("cruel family", r"family|stepmother|mother-in-law|sister|father|matriarch|cruel|disown"),
    ("humiliation", r"humiliat|disgrace|shame|mock|insult|beggar"),
    ("danger / crime", r"poison|murder|kill|blood|knife|danger|threat|kidnap|blackmail"),
    ("romance / forbidden love", r"love|kiss|romance|forbidden|desire|crush"),
]


def trope_family(trope: str) -> str:
    t = (trope or "").lower()
    for name, pat in TROPE_FAMILIES:
        if re.search(pat, t):
            return name
    return "other"


def diversify(ranked: list[dict], k: int = 10, max_ep_end: int = 3, max_per_ep: int = 2,
              min_tropes: int = 4) -> list[dict]:
    """Greedy: walk the ranked list and take each clip unless it breaks a rule.
    Rules for the top k: <= max_ep_end clips ending on an episode's final beat, <= max_per_ep per
    episode, and >= min_tropes distinct trope families (when a slot is needed for a new family,
    only a clip from a new family can take it). Clips skipped here keep their order after the top k."""
    top, ep_end, per_ep, fams = [], 0, {}, set()
    pool = list(ranked)
    while len(top) < k and pool:
        slots_left = k - len(top)
        need_new = max(0, min_tropes - len(fams))
        pick = None
        for p in pool:
            fam = trope_family(p.get("trope", ""))
            eps = {s["episode"] for s in p["segments"]}
            if p.get("ends_on_episode_end") and ep_end >= max_ep_end:
                continue
            if any(per_ep.get(e, 0) >= max_per_ep for e in eps):
                continue
            if need_new >= slots_left and fam in fams:
                continue   # remaining slots are reserved for new trope families
            pick = p
            break
        if pick is None:          # rules cannot all be met: relax the trope rule, keep the hard ones
            pick = next((p for p in pool if not (p.get("ends_on_episode_end") and ep_end >= max_ep_end)
                         and not any(per_ep.get(s["episode"], 0) >= max_per_ep for s in p["segments"])), None)
        if pick is None:
            break
        pool.remove(pick)
        top.append(pick)
        ep_end += bool(pick.get("ends_on_episode_end"))
        for e in {s["episode"] for s in pick["segments"]}:
            per_ep[e] = per_ep.get(e, 0) + 1
        fams.add(trope_family(pick.get("trope", "")))
    for p in top:
        p["trope_family"] = trope_family(p.get("trope", ""))
    return top + pool
