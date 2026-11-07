"""Deterministic screenplay parser.

Turns Kuku's episode .txt files into structured, timestamped blocks.
No AI here: parsing and all timing math stay in plain code so they are
exact, fast, free and testable.

Each block gets a stable ID like "E01-B023" (episode 1, block 23). The LLM
only ever refers to blocks by these IDs; code converts IDs back to times.
That way the model cannot hallucinate a timestamp.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

TS = r"\((\d+):(\d+(?:\.\d+)?)\)"
RE_TIMES = re.compile(rf"^Start:\s*{TS}\s*\|\s*End:\s*{TS}\s*$")
RE_HEADER = re.compile(r"^\*\*(.+?):\*\*\s*$")
RE_SCENE = re.compile(r"^SCENE\s+(\d+)\s*$")
RE_EP_NUM = re.compile(r"^EPISODE NUMBER:\s*Episode\s*(\d+)", re.I)

STRUCTURAL_TYPES = {"CAMERA", "ACTION", "SOUND FX", "SFX", "MUSIC", "VO", "TEXT", "TITLE"}


def to_sec(m: str, s: str) -> float:
    return int(m) * 60 + float(s)


def fmt(t: float) -> str:
    """Seconds -> mm:ss.ss (same style as the screenplay)."""
    m = int(t // 60)
    return f"{m:02d}:{t - 60 * m:05.2f}"


@dataclass
class Block:
    id: str            # E01-B023
    episode: int
    scene: int
    kind: str          # CAMERA | ACTION | DIALOGUE | SFX
    speaker: str       # for DIALOGUE, else ""
    delivery: str      # e.g. "Cold, Commanding"
    text: str
    start: float
    end: float

    def line(self, with_time: bool = True) -> str:
        """Compact one-line rendering used in prompts."""
        t = f"[{self.id.split('-')[1]} {fmt(self.start)}-{fmt(self.end)}] " if with_time else ""
        if self.kind == "DIALOGUE":
            d = f" ({self.delivery})" if self.delivery else ""
            return f"{t}{self.speaker}{d}: {self.text}"
        return f"{t}{self.kind}: {self.text}"


@dataclass
class Episode:
    number: int
    logline: str
    continuity: str
    duration: float
    blocks: list[Block] = field(default_factory=list)
    scenes: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def block(self, bid: str) -> Block | None:
        return self._index().get(bid)

    def _index(self):
        if not hasattr(self, "_idx"):
            self._idx = {b.id: b for b in self.blocks}
        return self._idx

    def to_dict(self):
        d = asdict(self)
        d.pop("_idx", None)
        return d


def _split_header(h: str) -> tuple[str, str, str]:
    """'LADY JULIANA (Confused, Breathless)' -> ('DIALOGUE','LADY JULIANA','Confused, Breathless')."""
    h = h.strip()
    upper = h.upper()
    if upper in STRUCTURAL_TYPES:
        kind = "SFX" if upper in {"SOUND FX", "SFX"} else upper
        return kind, "", ""
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", h)
    if m:
        name, deliv = m.group(1).strip(), m.group(2).strip()
        # "MATRIARCH (O.S.) (Firm)" -> name "MATRIARCH (O.S.)", delivery "Firm"
        m2 = re.match(r"^(.*\))\s*\((.*)$", h)
        if m2 and "(" in m2.group(1):
            name = m2.group(1).strip()
            deliv = m2.group(2).rstrip(")").strip()
        return "DIALOGUE", name, deliv
    return "DIALOGUE", h, ""


def parse_episode(text: str, fallback_number: int = 0) -> Episode:
    lines = text.replace("\r\n", "\n").split("\n")
    number, logline, continuity = fallback_number, "", ""
    for ln in lines[:10]:
        if m := RE_EP_NUM.match(ln):
            number = int(m.group(1))
        elif ln.startswith("EPISODE LOGLINE:"):
            logline = ln.split(":", 1)[1].strip()
        elif ln.startswith("CONTINUITY NOTES:"):
            continuity = ln.split(":", 1)[1].strip()

    ep = Episode(number=number, logline=logline, continuity=continuity, duration=0.0)
    scene_no = 0
    cur: dict | None = None
    raw: list[dict] = []

    def flush():
        nonlocal cur
        if cur and cur.get("start") is not None:
            cur["text"] = " ".join(t.strip() for t in cur["text"] if t.strip()).strip()
            raw.append(cur)
        elif cur:
            ep.warnings.append(f"Block without timestamps dropped: {cur.get('header')}")
        cur = None

    for ln in lines:
        s = ln.strip()
        if m := RE_SCENE.match(s):
            flush()
            scene_no = int(m.group(1))
            ep.scenes.append({"scene": scene_no})
            continue
        if s.startswith("Scene heading:") and ep.scenes:
            ep.scenes[-1]["heading"] = s.split(":", 1)[1].strip()
            continue
        if s.startswith("Scene start:") and ep.scenes:
            mm, ss = s.split(":", 1)[1].strip().split(":")
            ep.scenes[-1]["start"] = to_sec(mm, ss)
            continue
        if s.startswith("Scene end:") and ep.scenes:
            mm, ss = s.split(":", 1)[1].strip().split(":")
            ep.scenes[-1]["end"] = to_sec(mm, ss)
            continue
        if m := RE_HEADER.match(s):
            flush()
            cur = {"header": m.group(1), "scene": scene_no, "start": None, "end": None, "text": []}
            continue
        if cur is not None:
            if m := RE_TIMES.match(s):
                cur["start"] = to_sec(m.group(1), m.group(2))
                cur["end"] = to_sec(m.group(3), m.group(4))
            elif s.startswith("--- SCRIPT END"):
                flush()
            elif s:
                cur["text"].append(s)
    flush()

    raw.sort(key=lambda r: (r["start"], r["end"]))
    for i, r in enumerate(raw, 1):
        kind, speaker, deliv = _split_header(r["header"])
        text = r["text"].strip().strip('"').strip("“”") if kind == "DIALOGUE" else r["text"]
        if kind == "DIALOGUE":
            text = f"\"{text}\""
        b = Block(id=f"E{number:02d}-B{i:03d}", episode=number, scene=r["scene"], kind=kind,
                  speaker=speaker, delivery=deliv, text=text, start=r["start"], end=r["end"])
        if b.end < b.start:
            ep.warnings.append(f"{b.id}: end before start ({fmt(b.start)} > {fmt(b.end)})")
            b.end = b.start
        ep.blocks.append(b)

    ends = [b.end for b in ep.blocks] + [sc.get("end", 0) for sc in ep.scenes]
    ep.duration = max(ends) if ends else 0.0
    return ep


def load_show(path: str | Path | bytes) -> tuple[str, list[Episode]]:
    """Load a show from a folder of .txt files, a .zip path, or zip bytes."""
    files: list[tuple[str, str]] = []
    if isinstance(path, (bytes, bytearray)):
        zf = zipfile.ZipFile(io.BytesIO(path))
        files = [(n, zf.read(n).decode("utf-8", "replace")) for n in zf.namelist()
                 if n.lower().endswith(".txt") and not n.startswith("__MACOSX")]
    else:
        p = Path(path)
        if p.suffix.lower() == ".zip":
            return load_show(p.read_bytes())
        files = [(str(f), f.read_text(encoding="utf-8", errors="replace"))
                 for f in sorted(p.rglob("*.txt"))]
    if not files:
        raise ValueError("No .txt episode files found")

    show = Path(files[0][0]).parent.name or "show"
    eps = []
    for i, (name, txt) in enumerate(sorted(files), 1):
        m = re.search(r"episode-(\d+)", Path(name).name, re.I)
        eps.append(parse_episode(txt, fallback_number=int(m.group(1)) if m else i))
    eps.sort(key=lambda e: e.number)
    return show, eps


# ---------- timing helpers used by the assembler ----------

def dialogue_spans(ep: Episode) -> list[tuple[float, float]]:
    return [(b.start, b.end) for b in ep.blocks if b.kind == "DIALOGUE"]


def is_clean_cut(ep: Episode, t: float, tol: float = 0.05) -> bool:
    """A cut at time t is clean if no line of dialogue is mid-delivery."""
    return not any(s + tol < t < e - tol for s, e in dialogue_spans(ep))


def shot_boundaries(ep: Episode) -> list[float]:
    """Start/end times of CAMERA shots: the natural places an editor cuts."""
    pts = {0.0, round(ep.duration, 2)}
    for b in ep.blocks:
        if b.kind == "CAMERA":
            pts.add(round(b.start, 2))
            pts.add(round(b.end, 2))
    return sorted(pts)


def blocks_between(ep: Episode, start: float, end: float) -> list[Block]:
    """Blocks that start inside [start, end)."""
    return [b for b in ep.blocks if start - 1e-6 <= b.start < end - 1e-6]
