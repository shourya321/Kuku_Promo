"""Render a silent 1080x1920 "animatic" MP4 for each top promo: the script played back in real time.

  python tools/render_animatic.py <run_dir> <out_dir> [--top 5]      (also used by the app's "Render animatic" button)

Why: reviewers (and editors) feel the pacing of a promo far better by watching it than by reading
timestamps. No footage is needed: every dialogue line appears at its real start/end inside the cut.

What is on screen:
  * top bar for the first 3 s: the hook (proves the hook lands inside 3 s)
  * the AD HOOK TEXT overlay (if the captioner wrote one) and the context caption
  * dialogue as large subtitles, ACTION/SFX lines in smaller italics, timed to the script
  * a short "CUT" flash where segments join, and an end card
How: Pillow draws one PNG per "state" (whenever any text changes); ffmpeg's concat demuxer holds each PNG
for its exact duration. ffmpeg comes from the imageio-ffmpeg package (pip install imageio-ffmpeg).
"""
import argparse
import json
import subprocess
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG, FG, ACCENT, MUTED = (14, 14, 18), (245, 245, 245), (230, 57, 70), (170, 170, 180)
CUT_FLASH, END_CARD = 0.25, 2.5


def font(size, style=""):
    """Arial on Windows, DejaVu on Linux, else Pillow's built-in font."""
    names = {"": ["arial.ttf", "DejaVuSans.ttf"], "b": ["arialbd.ttf", "DejaVuSans-Bold.ttf"],
             "i": ["ariali.ttf", "DejaVuSans-Oblique.ttf"]}[style]
    for n in names:
        for d in ["C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/", ""]:
            try:
                return ImageFont.truetype(d + n, size)
            except OSError:
                pass
    return ImageFont.load_default()


F_SUB, F_SPK, F_ACT, F_BAR, F_SMALL = font(64, "b"), font(40, "b"), font(42, "i"), font(46, "b"), font(34)


def timeline(promo, episodes):
    """Blocks of every segment on one promo clock: (t_start, t_end, kind, speaker, text). Plus the cut times."""
    events, cuts, offset = [], [], 0.0
    for i, s in enumerate(promo["segments"]):
        if i:
            cuts.append(offset)
        for b in episodes[str(s["episode"])]["blocks"]:
            if s["start"] - 1e-6 <= b["start"] < s["end"] - 1e-6 and b["kind"] in ("DIALOGUE", "ACTION", "SFX"):
                a = offset + b["start"] - s["start"]
                z = offset + min(b["end"], s["end"]) - s["start"]
                events.append((a, max(z, a + 0.4), b["kind"], b["speaker"], b["text"].strip('"')))
        offset += s["end"] - s["start"]
    return events, cuts, offset


def wrap(draw, text, f, width):
    """Greedy word wrap to a pixel width."""
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur); cur = w
    return lines + [cur] if cur else lines


def centered(draw, y, lines, f, fill, gap=12):
    for ln in lines:
        x = (W - draw.textlength(ln, font=f)) / 2
        draw.text((x, y), ln, font=f, fill=fill)
        y += f.size + gap
    return y


def frame(promo, t, events, cuts, dur, path, end_card=False, cut=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    if end_card:
        y = centered(d, 760, wrap(d, promo.get("ad_hook_text") or promo.get("title", ""), F_SUB, 900), F_SUB, FG)
        centered(d, y + 60, ["Watch the full episode on Kuku TV"], F_BAR, ACCENT)
        img.save(path); return
    if cut:
        d.rectangle([0, 0, W, H], fill=(245, 245, 245))
        centered(d, 900, ["CUT"], F_SUB, BG)
        img.save(path); return
    if t < 3.0:   # hook bar: proves the hook lands within the first 3 seconds
        d.rectangle([0, 0, W, 230], fill=ACCENT)
        centered(d, 40, wrap(d, "HOOK: " + textwrap.shorten(promo.get("hook", ""), 90), F_BAR, 1000)[:3], F_BAR, FG, 6)
    elif promo.get("ad_hook_text"):
        d.rectangle([60, 120, W - 60, 230], fill=(40, 40, 48))
        centered(d, 148, [promo["ad_hook_text"].upper()], F_BAR, FG)
    if promo.get("context_caption") and t < 6.0:
        centered(d, 300, wrap(d, promo["context_caption"], F_SMALL, 940), F_SMALL, MUTED)
    now = [e for e in events if e[0] <= t < e[1]]
    y = 760
    for a, z, kind, spk, text in now[-2:]:
        if kind == "DIALOGUE":
            y = centered(d, y, [spk], F_SPK, ACCENT, 8)
            y = centered(d, y, wrap(d, text, F_SUB, 960)[:5], F_SUB, FG) + 40
        else:
            y = centered(d, y, wrap(d, f"[{text}]", F_ACT, 960)[:4], F_ACT, MUTED) + 40
    # progress bar + clock
    d.rectangle([0, H - 24, int(W * min(1, t / dur)), H], fill=ACCENT)
    d.text((40, H - 90), f"{t:4.1f}s / {dur:.0f}s", font=F_SMALL, fill=MUTED)
    img.save(path)


def render(promo, episodes, out_mp4, ffmpeg):
    events, cuts, dur = timeline(promo, episodes)
    # every moment the screen changes: block starts/ends, the 3 s mark, the caption mark, cuts
    marks = sorted({0.0, 3.0, 6.0, dur, *cuts, *[e[0] for e in events], *[e[1] for e in events]})
    marks = [m for m in marks if 0 <= m <= dur]
    tmp = Path(tempfile.mkdtemp(prefix="anim_"))
    lines = []
    k = 0
    for a, b in zip(marks, marks[1:]):
        if b - a < 0.02:
            continue
        cut_here = any(abs(a - c) < 1e-3 for c in cuts)
        if cut_here:  # a short flash at a segment join, so the viewer sees where the editor cuts
            p = tmp / f"f{k:04d}.png"; frame(promo, a, events, cuts, dur, p, cut=True)
            lines += [f"file '{p.as_posix()}'", f"duration {min(CUT_FLASH, b - a):.3f}"]; k += 1
            a += min(CUT_FLASH, b - a)
            if b - a < 0.02:
                continue
        p = tmp / f"f{k:04d}.png"; frame(promo, (a + b) / 2, events, cuts, dur, p)
        lines += [f"file '{p.as_posix()}'", f"duration {b - a:.3f}"]; k += 1
    p = tmp / "end.png"; frame(promo, dur, events, cuts, dur, p, end_card=True)
    lines += [f"file '{p.as_posix()}'", f"duration {END_CARD}", f"file '{p.as_posix()}'"]  # last file listed twice (ffmpeg quirk)
    (tmp / "list.txt").write_text("\n".join(lines), encoding="utf-8")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-movflags", "+faststart", str(out_mp4)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir"); ap.add_argument("out_dir"); ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    rd, od = Path(a.run_dir), Path(a.out_dir)
    od.mkdir(parents=True, exist_ok=True)
    ranked = json.loads((rd / "03_promos_ranked.json").read_text(encoding="utf-8"))
    episodes = json.loads((rd / "00_episodes_parsed.json").read_text(encoding="utf-8"))
    for p in ranked[:a.top]:
        out = od / f"promo_{p['rank']:02d}_{p['id']}.mp4"
        render(p, episodes, out, ffmpeg)
        print("wrote", out)


if __name__ == "__main__":
    main()
