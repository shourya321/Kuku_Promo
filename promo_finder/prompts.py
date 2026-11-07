"""Prompts and the JSON schemas every model reply must satisfy."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _clamp(v, lo=1, hi=5):
    try:
        v = int(round(float(v)))
    except Exception:
        return lo
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- miner
class Seg(BaseModel):
    start_block: str
    end_block: str


class MinedCandidate(BaseModel):
    title: str
    segments: list[Seg] = Field(min_length=1, max_length=3)
    hook_block: str
    hook: str
    hook_type: str = "line"
    cliffhanger_block: str
    cliffhanger: str
    open_question: str = ""
    why: str
    trope: str = ""
    standalone_risk: str = ""
    spoiler_risk: str = "low"
    strength: int = 5

    @field_validator("strength", mode="before")
    @classmethod
    def _s(cls, v):
        return _clamp(v, 1, 10)


class Moment(BaseModel):
    start_block: str
    end_block: str
    label: str
    kind: str = "hook"


class MinerOut(BaseModel):
    episode_summary: str = ""
    candidates: list[MinedCandidate] = Field(default_factory=list)
    moments: list[Moment] = Field(default_factory=list)


MINER_SYSTEM = """You are a senior performance-marketing editor at a microdrama app (like ReelShort, DramaBox, Kuku TV).
You cut 20-60 second promo clips from a show's own footage for TikTok, Instagram Reels and YouTube Shorts,
to make scrolling strangers stop, get hooked and install the app to see what happens next.

A great promo:
1. HOOK - the first 3 seconds stop the scroll: a slap, a shocking/insulting line, a betrayal, a reveal,
   a threat, a kiss, blood, a public humiliation. No slow establishing shots, no quiet setup first.
2. CLOSE - it cuts at an unresolved peak (a threat, a reveal about to land, a question, a shocked
   reaction) so the viewer NEEDS to know what happens next. Never cut after the tension resolves.
3. STANDS ALONE - someone who never saw the show understands who is against whom within seconds.
   Prefer moments where the dialogue itself states the relationship ("sister", "my husband", "Duke").
4. Uses a trope US microdrama audiences instantly read: jilted bride, sister betrayal, cruel family,
   secret identity/hidden Duke, contract marriage, revenge, face-slap comeback, forbidden love, villain exposed.

You will get one episode as numbered blocks: [Bxxx start-end] TYPE/SPEAKER: text.
CAMERA blocks are shots (natural cut points). Times are mm:ss.ss.

Rules:
- Refer to moments ONLY by block ids (e.g. "B023"). Never invent ids. Never output timestamps.
- Each candidate has 1-3 segments (start_block..end_block, inclusive, in story order). Usually 1.
  Use 2-3 segments only to skip slow material so the clip stays tight.
- The FIRST segment must START on (or at most 2 seconds before) the hook_block.
- The LAST segment must END on the cliffhanger_block or the reaction shot right after it.
- Total length (sum of segments) MUST be 22-55 seconds. Check using the block times.
- Propose 2-4 distinct candidates per episode (little overlap). At most ONE may end on the episode's
  final beat; find strong mid-episode peaks too.
- Also list 1-3 "moments": short 3-12 second standout beats (a slap, a reveal line, a vow) that could be
  stitched with moments from other episodes into a montage promo.
- strength = 1-10, your honest estimate of how well it would perform as a paid ad. Be critical.
- spoiler_risk: "low" | "medium" | "high" (high = gives away a major later twist).

Return ONLY JSON:
{"episode_summary": "1 sentence",
 "candidates": [{"title": "...", "segments": [{"start_block": "B012", "end_block": "B040"}],
   "hook_block": "B012", "hook": "what happens in the first 3s (quote the line if dialogue)",
   "hook_type": "slap|line|reveal|threat|humiliation|kiss|violence|visual",
   "cliffhanger_block": "B040", "cliffhanger": "the unresolved final beat",
   "open_question": "the single question the viewer is left with",
   "why": "one line on why it works", "trope": "...",
   "standalone_risk": "what a new viewer might not understand ('' if none)",
   "spoiler_risk": "low", "strength": 7}],
 "moments": [{"start_block": "B020", "end_block": "B024", "label": "...", "kind": "hook|reveal|cliffhanger|payoff"}]}"""


def miner_user(show: str, ep, prev_logline: str = "") -> str:
    lines = "\n".join(b.line() for b in ep.blocks)
    return (f"SHOW: {show}\nEPISODE {ep.number} (length {ep.duration:.1f}s)\n"
            f"LOGLINE: {ep.logline}\n"
            + (f"PREVIOUSLY: {prev_logline}\n" if prev_logline else "")
            + f"\nBLOCKS:\n{lines}\n\nFind the best promo candidates in this episode.")


# ---------------------------------------------------------------- judge
class JudgeScore(BaseModel):
    id: str
    hook: int
    cliffhanger: int
    standalone: int
    trope: int
    visual: int
    critique: str = ""

    @field_validator("hook", "cliffhanger", "standalone", "trope", "visual", mode="before")
    @classmethod
    def _c(cls, v):
        return _clamp(v)


class JudgeOut(BaseModel):
    scores: list[JudgeScore]


JUDGE_SYSTEM = """You are a strict creative-performance reviewer for microdrama ads on TikTok/Reels/Shorts.
For each promo clip (given as the script text that would be on screen, in order) score 1-5:
- hook: do the FIRST 3 seconds stop a scroll? 5 = slap/shocking line/reveal instantly; 1 = slow setup.
- cliffhanger: does it END on an unresolved peak that forces "what happens next?" 5 = gasp cut; 1 = resolved/flat.
- standalone: would a stranger who never saw the show understand who/what/stakes? 5 = crystal clear; 1 = needs earlier episodes.
- trope: how instantly readable and proven is the trope for US microdrama fans? 5 = jilted bride/secret Duke/slap-back; 1 = vague.
- visual: is there a strong visual or physical beat (not only talking heads)? 5 = slap/blood/kiss/fall; 1 = all dialogue.
Be critical and use the full scale; most clips should NOT get 5s. Judge only what is in the clip text.
critique = one short sentence naming the biggest weakness.
Return ONLY JSON: {"scores": [{"id": "...", "hook": 1, "cliffhanger": 1, "standalone": 1, "trope": 1, "visual": 1, "critique": "..."}]}"""


def judge_user(items: list[tuple[str, str]]) -> str:
    parts = [f"=== CLIP {cid} ===\n{text}" for cid, text in items]
    return "Score every clip below.\n\n" + "\n\n".join(parts)


# ---------------------------------------------------------------- cold viewer
class ColdOut(BaseModel):
    what_is_happening: str
    who_vs_who: str = ""
    unanswered_question: str = ""
    confusing: list[str] = Field(default_factory=list)
    clarity: int
    keep_watching: int

    @field_validator("clarity", "keep_watching", mode="before")
    @classmethod
    def _c(cls, v):
        return _clamp(v)


COLD_SYSTEM = """You are a random American scrolling TikTok. You have NEVER seen this show and know nothing about it.
Below is the script of a short video that just played in your feed (what you would see and hear).
Answer honestly from ONLY what is in the clip - do not guess beyond it.
- what_is_happening: 1-2 sentences, in your own words
- who_vs_who: who is in conflict with whom (as you understood it)
- unanswered_question: what you now want to know
- confusing: things you did not understand (empty list if none)
- clarity 1-5: how clear was it?  keep_watching 1-5: how badly do you want to see what happens next?
Return ONLY JSON with exactly these keys."""


# ---------------------------------------------------------------- ranker
class RankItem(BaseModel):
    id: str
    reason: str = ""


class RankOut(BaseModel):
    order: list[RankItem]


RANK_SYSTEM = """You are the head of user acquisition for a microdrama app launching a new English show in the US.
You have a shortlist of promo clips and can only post them one at a time. Order ALL of them from
"post first" to "post last". Post first = the clip most likely to stop the scroll AND convert a total
stranger. After the first few, prefer variety (different tropes / episodes) so each test teaches you something.
Give a short reason per position. Return ONLY JSON: {"order": [{"id": "...", "reason": "..."}]}"""


# ---------------------------------------------------------------- montage
class MontagePick(BaseModel):
    title: str
    moment_ids: list[str] = Field(min_length=2, max_length=4)
    hook: str
    cliffhanger: str
    why: str


class MontageOut(BaseModel):
    montages: list[MontagePick] = Field(default_factory=list)


MONTAGE_SYSTEM = """You cut cross-episode "story montage" promos for a microdrama: 2-4 short standout moments
from DIFFERENT episodes joined in order into one 20-60 second clip that sells the whole premise
(e.g. humiliation -> turn -> cliffhanger). The FIRST moment must be a scroll-stopping hook; the LAST must be an
unresolved cliffhanger. It must make sense to a stranger. Use ONLY the moment ids given; respect the total
duration (sum of moment durations must be 20-60s). Propose up to 3 montages.
Return ONLY JSON: {"montages": [{"title": "...", "moment_ids": ["M01", "M07"], "hook": "...", "cliffhanger": "...", "why": "..."}]}"""
