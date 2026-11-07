"""Turn model picks (block ids) into exact, editor-ready segments.

All rules here are plain code, so they are deterministic and explainable:
  * cuts snap to camera-shot boundaries and never land mid-line
  * the hook must land within the first 3 s of the promo
  * the end gets an optional <=1.5 s reaction hold
  * total length 20-60 s: short clips get a "flash-forward cold open",
    long clips get a jump cut; anything unfixable is rejected with a reason
"""
from __future__ import annotations

import re

from .parser import Episode, fmt, is_clean_cut, shot_boundaries

MIN_LEN, MAX_LEN, HOOK_MAX, HOLD_MAX = 20.0, 60.0, 3.0, 1.5


def norm_id(ep: Episode, raw: str) -> str | None:
    m = re.search(r"B\s*0*(\d+)", str(raw), re.I)
    if not m:
        return None
    bid = f"E{ep.number:02d}-B{int(m.group(1)):03d}"
    return bid if ep.block(bid) else None


def _clean_points(ep: Episode) -> list[float]:
    """Shot boundaries + dialogue starts/ends that do not cut through a line."""
    pts = set(shot_boundaries(ep))
    for b in ep.blocks:
        if b.kind == "DIALOGUE":
            pts.add(round(b.start, 2)); pts.add(round(b.end, 2))
    return sorted(p for p in pts if is_clean_cut(ep, p))


def snap(ep: Episode, t: float, lo: float, hi: float, prefer: str = "near") -> float | None:
    """Best clean cut in [lo, hi]; prefers shot boundaries, then closeness to t."""
    shots = set(shot_boundaries(ep))
    cands = [p for p in _clean_points(ep) if lo - 1e-6 <= p <= hi + 1e-6]
    if not cands:
        return None
    return min(cands, key=lambda p: (p not in shots, abs(p - t)))


def _merge(segs):
    segs = sorted(segs, key=lambda s: s[0])
    out = []
    for s, e in segs:
        if out and s <= out[-1][1] + 0.5:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def assemble(ep: Episode, cand: dict, allow_flash: bool = True) -> dict:
    """cand has block-id fields from the miner. Returns a promo dict with status ok/rejected.

    allow_flash=False skips the "flash-forward cold open" fix (it repeats footage and looks clumsy),
    so the pipeline can first ask the miner for a cleaner fix and use the cold open only as a last resort."""
    p = dict(cand)
    p.setdefault("flags", [])
    p["reject_reasons"] = []
    p["episode"] = ep.number

    def reject(msg):
        p["reject_reasons"].append(msg)

    hook_id = norm_id(ep, cand.get("hook_block", ""))
    cliff_id = norm_id(ep, cand.get("cliffhanger_block", ""))
    raw_segs = []
    for s in cand.get("segments", []):
        a, b = norm_id(ep, s.get("start_block")), norm_id(ep, s.get("end_block"))
        if not a or not b:
            reject(f"unknown block id in segment {s}")
            continue
        ba, bb = ep.block(a), ep.block(b)
        start, end = min(ba.start, bb.start), max(ba.end, bb.end)
        raw_segs.append((start, end))
    if not hook_id:
        reject(f"unknown hook block {cand.get('hook_block')}")
    if not cliff_id:
        reject(f"unknown cliffhanger block {cand.get('cliffhanger_block')}")
    if p["reject_reasons"] or not raw_segs:
        if not raw_segs:
            reject("no valid segments")
        p["status"] = "rejected"
        return p

    hook_t = ep.block(hook_id).start
    cliff_end = ep.block(cliff_id).end
    p["hook_block"], p["cliffhanger_block"] = hook_id, cliff_id

    segs = _merge(raw_segs)
    # --- start: hook must be within the first 3 s
    s0, e0 = segs[0]
    if hook_t < s0 or hook_t > e0:
        s0 = hook_t
        p["flags"].append("start moved to hook")
    if hook_t - s0 > HOOK_MAX:
        p["flags"].append(f"trimmed {hook_t - s0 - 0.5:.1f}s of slow open")
        s0 = hook_t - 0.5
    new_s0 = snap(ep, s0, max(0.0, hook_t - HOOK_MAX), hook_t)
    segs[0] = (new_s0 if new_s0 is not None else hook_t, e0)

    # --- end: finish on the cliffhanger + optional reaction hold
    sl, el = segs[-1]
    target_end = max(el, cliff_end) if cliff_end >= sl else el
    new_el = snap(ep, target_end + HOLD_MAX / 2, target_end, min(ep.duration, target_end + HOLD_MAX))
    if new_el is None:  # must extend past an overlapping line
        new_el = snap(ep, target_end, target_end, min(ep.duration, target_end + 6))
    if new_el is None:
        reject(f"no clean cut near the end ({fmt(target_end)})")
        new_el = target_end
    segs[-1] = (segs[-1][0], new_el)

    # --- inner boundaries of multi-segment cuts
    fixed = []
    for i, (s, e) in enumerate(segs):
        if i > 0:
            s = snap(ep, s, s - 1.5, s + 1.5) or s
        if i < len(segs) - 1:
            e = snap(ep, e, e - 1.5, e + 1.5) or e
        fixed.append((s, e))
    segs = _merge(fixed)

    dur = sum(e - s for s, e in segs)

    # --- too short: flash-forward cold open (hook beat first, then the build-up from earlier)
    if dur < MIN_LEN and allow_flash:
        a_end = snap(ep, hook_t + 4, hook_t + 2.5, hook_t + 6.5)
        need = MIN_LEN - dur + 1.0
        if a_end:
            need += 0  # the cold-open beat is extra length too
            lenA = a_end - segs[0][0]
            back = max(0.0, need - lenA)
            new_start = snap(ep, segs[0][0] - back, max(0.0, segs[0][0] - back - 4), segs[0][0] - back) \
                if back > 0 else segs[0][0]
            if new_start is not None and segs[0][0] - back >= -0.01:
                segs = [(segs[0][0], a_end), (new_start, segs[0][1])] + segs[1:]
                p["flags"].append("flash-forward cold open")
        dur = sum(e - s for s, e in segs)
    if dur < MIN_LEN:
        reject(f"too short ({dur:.1f}s)")

    # --- too long: keep the hook stretch + the run-up to the cliffhanger (one jump cut)
    if dur > MAX_LEN:
        if dur > 2 * MAX_LEN or len(segs) > 2:
            reject(f"too long ({dur:.1f}s)")
        else:
            s_first = segs[0][0]
            head_end = snap(ep, s_first + 18, s_first + 12, s_first + 24)
            tail_len = MAX_LEN - 2 - ((head_end or s_first + 18) - s_first)
            tail_start = snap(ep, segs[-1][1] - tail_len, segs[-1][1] - tail_len, segs[-1][1] - tail_len + 8)
            if head_end and tail_start and tail_start > head_end:
                segs = [(s_first, head_end), (tail_start, segs[-1][1])]
                p["flags"].append("auto-compressed (jump cut)")
            else:
                reject(f"too long ({dur:.1f}s)")
        dur = sum(e - s for s, e in segs)

    # --- final hard checks
    for s, e in segs:
        for t in (s, e):
            if not is_clean_cut(ep, t):
                reject(f"cut at {fmt(t)} lands mid-line")
    hook_offset = hook_t - segs[0][0]
    if hook_offset > HOOK_MAX + 0.01 or hook_offset < -0.01:
        reject(f"hook at {hook_offset:.1f}s, not in first 3s")
    if not (MIN_LEN - 0.01 <= dur <= MAX_LEN + 0.01) and not any("too" in r for r in p["reject_reasons"]):
        reject(f"length {dur:.1f}s outside 20-60s")

    p["segments"] = [{"episode": ep.number, "start": round(s, 2), "end": round(e, 2),
                      "start_tc": fmt(s), "end_tc": fmt(e)} for s, e in segs]
    p["duration"] = round(dur, 2)
    p["hook_offset"] = round(hook_offset, 2)
    p["ends_on_episode_end"] = segs[-1][1] >= ep.duration - 2.5
    if p["ends_on_episode_end"]:
        p["flags"].append("ends on episode's final beat")
    p["status"] = "rejected" if p["reject_reasons"] else "ok"
    return p


FIXABLE = ("too short", "too long", "hook at", "length")


def repair_hint(ep: Episode, p: dict) -> str | None:
    """A precise, block-level instruction for the miner to fix a rejected candidate, or None if the
    failure is not a timing problem (e.g. a hallucinated block id: re-asking would not help)."""
    reasons = p.get("reject_reasons", [])
    if not reasons or not all(any(r.startswith(f) for f in FIXABLE) for r in reasons) or not p.get("segments"):
        return None
    dur, end = p["duration"], p["segments"][-1]["end"]
    hook = p.get("hook_block", "?").split("-")[-1]
    if dur < MIN_LEN:
        need = 22.0 - dur   # aim a little above the 20 s floor
        after = [b for b in ep.blocks if b.end >= end + need and is_clean_cut(ep, b.end)]
        target = (f"at or after {after[0].id.split('-')[1]} (ends {fmt(after[0].end)})" if after
                  else "later (the episode ends soon: consider adding a second segment)")
        return (f"too short ({dur:.1f}s): needs +{need:.1f}s. Extend the end to a clean cut {target}, "
                f"or add an earlier segment, while keeping the hook {hook} in the first 3 s.")
    if dur > MAX_LEN:
        return (f"too long ({dur:.1f}s): cut {dur - 55:.1f}s. End earlier, or use 2 segments to skip slow material, "
                f"keeping hook {hook} first and the cliffhanger last.")
    return f"{reasons[0]}: the first segment must start on (or <=2 s before) the hook block {hook}."


def intervals(p: dict) -> list[tuple[int, float, float]]:
    return [(s["episode"], s["start"], s["end"]) for s in p["segments"]]


def overlap_ratio(a: dict, b: dict) -> float:
    """Temporal IoU of two promos (same episode segments only)."""
    inter = 0.0
    for ea, sa, xa in intervals(a):
        for eb, sb, xb in intervals(b):
            if ea == eb:
                inter += max(0.0, min(xa, xb) - max(sa, sb))
    union = a["duration"] + b["duration"] - inter
    return inter / union if union > 0 else 0.0


def dedupe(promos: list[dict], key="strength", thr=0.5) -> list[dict]:
    """Drop a promo that overlaps >thr with a better one; returns kept list (others marked)."""
    kept = []
    for p in sorted(promos, key=lambda x: -float(x.get(key) or 0)):
        dup = next((k for k in kept if overlap_ratio(p, k) > thr), None)
        if dup:
            p["status"] = "duplicate"
            p["reject_reasons"].append(f"overlaps {overlap_ratio(p, dup):.0%} with {dup['id']}")
        else:
            kept.append(p)
    return kept


def clip_text(episodes: dict, p: dict, with_rel_time=True, kinds=("CAMERA", "ACTION", "DIALOGUE", "SFX")) -> str:
    """What is on screen in this promo, in order, with time relative to the promo start."""
    out, offset = [], 0.0
    for i, s in enumerate(p["segments"]):
        ep = episodes[s["episode"]]
        if len(p["segments"]) > 1:
            out.append(f"--- cut {i + 1} (episode {s['episode']}) ---")
        for b in ep.blocks:
            if s["start"] - 1e-6 <= b.start < s["end"] - 1e-6 and b.kind in kinds:
                rel = offset + b.start - s["start"]
                line = b.line(with_time=False)
                out.append(f"(+{rel:4.1f}s) {line}" if with_rel_time else line)
        offset += s["end"] - s["start"]
    return "\n".join(out)
