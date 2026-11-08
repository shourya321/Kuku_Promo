"""Re-open a finished run from a zip of its output folder (no model calls).

Used by the app's "Open a saved run" input: share a run with an editor, or show a full-show result in a
demo without re-running it. Returns the same dict the app stores after a fresh run.
"""
from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

from .parser import Block, Episode

NEEDED = ("run_summary.json", "02_all_candidates.json", "00_episodes_parsed.json", "promos_ranked.csv",
          "edit_decision_list.csv", "promos_ranked.md", "run_log.txt")


def load_saved_run(blob: bytes, profile: str) -> dict:
    d = Path(tempfile.mkdtemp(prefix="saved_"))
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for m in z.infolist():                       # never write outside the temp folder
            parts = m.filename.replace("\\", "/").split("/")
            if m.filename.startswith(("/", "\\")) or ".." in parts or ":" in parts[0]:
                continue
            z.extract(m, d)
    hits = sorted(d.rglob("03_promos_ranked.json"), key=lambda p: len(p.parts))
    if not hits:
        raise ValueError("no 03_promos_ranked.json inside: zip an outputs/<run> folder, or use the Export tab's zip")
    run_dir = hits[0].parent
    missing = [n for n in NEEDED if not (run_dir / n).exists()]
    if missing:
        raise ValueError("missing " + ", ".join(missing))
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    raw = json.loads((run_dir / "00_episodes_parsed.json").read_text(encoding="utf-8"))
    episodes = {int(k): Episode(**{**e, "blocks": [Block(**b) for b in e["blocks"]]}) for k, e in raw.items()}
    return {"out": str(run_dir), "summary": summary, "episodes": episodes, "ai": summary.get("mode") == "llm",
            "profile": profile, "saved": True}
