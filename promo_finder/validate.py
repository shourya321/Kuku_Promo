"""Format check for a NEW show, run before the pipeline (free, no AI).

  python -m promo_finder.validate path/to/show.zip|folder

A new show from a different writer or tool may have small format differences. This tells you in seconds
whether the parser understood it, instead of finding out after a run of model calls.
Reports: episodes found, blocks, timestamp style and anomalies, missing CAMERA blocks, unparseable lines, CRLF.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

from .parser import load_show

RE_HEADER = re.compile(r"^\*\*(.+?):\*\*\s*$")


def _raw_files(path) -> list[tuple[str, str]]:
    p = Path(path)
    if p.suffix.lower() == ".zip":
        z = zipfile.ZipFile(io.BytesIO(p.read_bytes()))
        return [(n, z.read(n).decode("utf-8", "replace")) for n in z.namelist()
                if n.lower().endswith(".txt") and not n.startswith("__MACOSX")]
    # read bytes, not read_text(): read_text silently turns CRLF into LF and would hide it
    return [(str(f), f.read_bytes().decode("utf-8", "replace")) for f in sorted(p.rglob("*.txt"))]


def validate(path) -> dict:
    raw = _raw_files(path)
    rep = {"files": len(raw), "crlf_files": sum("\r\n" in t for _, t in raw), "timestamp_styles": {},
           "episodes": [], "problems": []}
    for _, t in raw:
        for m in re.findall(r"Start:\s*\(([\d:.]+)\)", t):
            style = "hh:mm:ss" if m.count(":") == 2 else "mm:ss"
            rep["timestamp_styles"][style] = rep["timestamp_styles"].get(style, 0) + 1
    try:
        show, eps = load_show(path)
    except Exception as e:  # nothing parseable at all
        rep["problems"].append(f"could not load: {e}")
        return rep
    rep["show"] = show
    nums = [e.number for e in eps]
    if len(set(nums)) != len(nums):
        rep["problems"].append(f"duplicate episode numbers: {sorted(n for n in nums if nums.count(n) > 1)}")
    for ep in eps:
        dlg = [b for b in ep.blocks if b.kind == "DIALOGUE"]
        cams = sum(b.kind == "CAMERA" for b in ep.blocks)
        anomalies = list(ep.warnings)
        # overlapping dialogue is legal (cross-talk) but makes clean cuts rare, so it is worth knowing
        overl = sum(1 for a, b in zip(dlg, dlg[1:]) if b.start < a.end - 0.05)
        gaps = [round(b.start - a.end, 1) for a, b in zip(ep.blocks, ep.blocks[1:]) if b.start - a.end > 10]
        if gaps:
            anomalies.append(f"{len(gaps)} gaps over 10 s with no block")
        e = {"episode": ep.number, "blocks": len(ep.blocks), "dialogue": len(dlg), "camera": cams,
             "duration_s": round(ep.duration, 1), "overlapping_dialogue": overl, "anomalies": anomalies}
        if not ep.blocks:
            rep["problems"].append(f"E{ep.number}: no timed blocks parsed")
        if cams == 0 and ep.blocks:
            rep["problems"].append(f"E{ep.number}: no CAMERA blocks, so cuts snap to dialogue gaps only")
        if not ep.logline:
            anomalies.append("no EPISODE LOGLINE line")
        rep["episodes"].append(e)
    rep["episodes_found"] = len(eps)
    rep["blocks_total"] = sum(e["blocks"] for e in rep["episodes"])
    rep["ok"] = not any("no timed blocks" in p or "could not load" in p for p in rep["problems"])
    return rep


if __name__ == "__main__":
    r = validate(sys.argv[1])
    print(json.dumps(r, indent=2, ensure_ascii=False))
    sys.exit(0 if r.get("ok") else 1)
