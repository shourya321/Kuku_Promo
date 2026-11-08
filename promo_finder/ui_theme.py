"""Look and feel for the Streamlit app: one stylesheet + small HTML builders.

Everything here is presentation only (no pipeline logic). HTML strings are built WITHOUT newlines or
indentation, because Streamlit's markdown renderer would turn indented lines into code blocks.
"""
from __future__ import annotations

import html

E = html.escape

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
:root{--pf-bg:#070912;--pf-panel:rgba(17,22,42,.72);--pf-panel2:rgba(24,30,56,.85);--pf-line:rgba(124,92,255,.28);
--pf-violet:#7C5CFF;--pf-cyan:#22D3EE;--pf-pink:#F472B6;--pf-green:#34D399;--pf-amber:#FBBF24;--pf-red:#F87171;
--pf-text:#E6E9F5;--pf-mut:#8A93B2;}
html,body,[data-testid="stAppViewContainer"]{font-family:'Space Grotesk',system-ui,sans-serif;}
[data-testid="stAppViewContainer"]{background:
 radial-gradient(1200px 600px at 10% -10%,rgba(124,92,255,.18),transparent 60%),
 radial-gradient(900px 500px at 100% 0%,rgba(34,211,238,.12),transparent 60%),
 linear-gradient(rgba(124,92,255,.045) 1px,transparent 1px) 0 0/44px 44px,
 linear-gradient(90deg,rgba(124,92,255,.045) 1px,transparent 1px) 0 0/44px 44px,
 var(--pf-bg);}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0B0F1F,#0A0D1A);border-right:1px solid var(--pf-line);}
.block-container{padding-top:2.2rem;max-width:1320px;}
code,pre,.pf-mono{font-family:'JetBrains Mono',ui-monospace,monospace!important;}
/* buttons */
.stButton>button,.stDownloadButton>button{border-radius:12px;border:1px solid var(--pf-line);background:rgba(124,92,255,.08);
 color:var(--pf-text);transition:all .18s ease;font-weight:600;letter-spacing:.2px;}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:var(--pf-cyan);box-shadow:0 0 0 1px rgba(34,211,238,.35),0 0 22px rgba(34,211,238,.25);transform:translateY(-1px);color:#fff;}
.stButton>button[kind="primary"],[data-testid="stBaseButton-primary"]{background:linear-gradient(100deg,#7C5CFF,#22D3EE);border:0;color:#05060c!important;
 box-shadow:0 8px 30px rgba(124,92,255,.35);}
.stButton>button[kind="primary"]:hover,[data-testid="stBaseButton-primary"]:hover{filter:brightness(1.08);box-shadow:0 10px 36px rgba(34,211,238,.45);}
/* tabs */
.stTabs [role="tablist"]{gap:6px;border-bottom:1px solid var(--pf-line);flex-wrap:wrap;}
.stTabs [role="tab"]{background:rgba(124,92,255,.06);border:1px solid var(--pf-line);border-bottom:0;border-radius:12px 12px 0 0;padding:8px 16px;transition:all .15s;}
.stTabs [role="tab"]:hover{background:rgba(34,211,238,.10);}
.stTabs [role="tab"][aria-selected="true"]{background:linear-gradient(180deg,rgba(124,92,255,.32),rgba(34,211,238,.08));color:#fff;box-shadow:0 -6px 22px rgba(124,92,255,.25);}
[data-testid="stExpander"]{border:1px solid var(--pf-line);border-radius:14px;background:rgba(10,14,28,.55);}
/* hero */
.pf-hero{position:relative;overflow:hidden;border:1px solid var(--pf-line);border-radius:22px;padding:28px 30px 22px;
 background:linear-gradient(135deg,rgba(124,92,255,.16),rgba(34,211,238,.06) 55%,rgba(244,114,182,.08));margin-bottom:18px;}
.pf-hero:after{content:"";position:absolute;left:-30%;top:0;width:30%;height:100%;
 background:linear-gradient(90deg,transparent,rgba(255,255,255,.06),transparent);animation:pf-scan 6s linear infinite;}
@keyframes pf-scan{to{left:130%;}}
.pf-eyebrow{font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.22em;color:var(--pf-cyan);display:flex;align-items:center;gap:8px;}
.pf-dot{width:8px;height:8px;border-radius:50%;background:var(--pf-green);box-shadow:0 0 10px var(--pf-green);animation:pf-pulse 1.8s infinite;}
@keyframes pf-pulse{0%,100%{opacity:1;}50%{opacity:.35;}}
.pf-title{font-size:clamp(2.1rem,4.4vw,3.4rem);font-weight:700;margin:.25rem 0 .2rem;line-height:1.05;
 background:linear-gradient(90deg,#fff,#C9BEFF 30%,#22D3EE 60%,#F472B6 90%);background-size:200% auto;
 -webkit-background-clip:text;background-clip:text;color:transparent;animation:pf-shine 8s linear infinite;}
@keyframes pf-shine{to{background-position:200% center;}}
.pf-sub{color:var(--pf-mut);max-width:820px;font-size:1.02rem;margin:0 0 .8rem;}
.pf-chips{display:flex;flex-wrap:wrap;gap:7px;margin:.35rem 0;}
.pf-chip{font-family:'JetBrains Mono',monospace;font-size:.72rem;padding:4px 10px;border-radius:999px;border:1px solid var(--pf-line);
 background:rgba(124,92,255,.10);color:#D8D3FF;white-space:nowrap;}
.pf-chip.ok{border-color:rgba(52,211,153,.45);background:rgba(52,211,153,.10);color:#A7F3D0;}
.pf-chip.warn{border-color:rgba(251,191,36,.45);background:rgba(251,191,36,.10);color:#FDE68A;}
.pf-chip.bad{border-color:rgba(248,113,113,.45);background:rgba(248,113,113,.10);color:#FECACA;}
.pf-chip.cyan{border-color:rgba(34,211,238,.45);background:rgba(34,211,238,.10);color:#A5F3FC;}
.pf-section{font-family:'JetBrains Mono',monospace;font-size:.78rem;letter-spacing:.2em;color:var(--pf-cyan);margin:18px 0 8px;}
/* stepper */
.pf-steps{display:flex;gap:0;align-items:center;flex-wrap:wrap;padding:14px 16px;border:1px solid var(--pf-line);border-radius:16px;background:var(--pf-panel);}
.pf-step{display:flex;align-items:center;gap:8px;font-size:.82rem;color:var(--pf-mut);}
.pf-node{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;font-size:.72rem;font-family:'JetBrains Mono',monospace;
 border:1px solid var(--pf-line);background:rgba(255,255,255,.03);}
.pf-step.done{color:#C7F9E5;} .pf-step.done .pf-node{background:var(--pf-green);color:#05140e;border-color:var(--pf-green);}
.pf-step.active{color:#fff;} .pf-step.active .pf-node{background:linear-gradient(135deg,#7C5CFF,#22D3EE);color:#05060c;border:0;
 box-shadow:0 0 0 4px rgba(34,211,238,.18),0 0 18px rgba(34,211,238,.55);animation:pf-pulse 1.2s infinite;}
.pf-link{flex:1;min-width:10px;max-width:40px;height:2px;margin:0 6px;background:var(--pf-line);}
.pf-steps{flex-wrap:nowrap;overflow-x:auto;} .pf-step{white-space:nowrap;font-size:.78rem;}
.pf-step.skip{opacity:.4;} .pf-step.skip .pf-node{border-style:dashed;}
.pf-link.done{background:linear-gradient(90deg,var(--pf-green),var(--pf-cyan));}
.pf-term{font-family:'JetBrains Mono',monospace;font-size:.76rem;line-height:1.55;color:#9EF0C4;background:#04060D;border:1px solid rgba(52,211,153,.25);
 border-radius:12px;padding:10px 14px;max-height:190px;overflow:auto;white-space:pre-wrap;}
/* kpis */
.pf-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:12px;margin:6px 0 14px;}
.pf-kpi{border:1px solid var(--pf-line);border-radius:16px;padding:14px 16px;background:var(--pf-panel);position:relative;overflow:hidden;}
.pf-kpi:before{content:"";position:absolute;inset:0 0 auto 0;height:2px;background:linear-gradient(90deg,var(--pf-violet),var(--pf-cyan));}
.pf-kpi .l{font-family:'JetBrains Mono',monospace;font-size:.68rem;letter-spacing:.16em;color:var(--pf-mut);text-transform:uppercase;}
.pf-kpi .v{font-size:1.8rem;font-weight:700;color:#fff;line-height:1.2;}
.pf-kpi .s{font-size:.78rem;color:var(--pf-mut);}
/* promo cards */
.pf-card{border:1px solid var(--pf-line);border-radius:18px;padding:16px 18px 14px;background:var(--pf-panel);
 box-shadow:0 0 0 1px rgba(255,255,255,.02) inset,0 12px 40px rgba(0,0,0,.25);margin-bottom:8px;transition:border-color .2s,box-shadow .2s;}
.pf-card:hover{border-color:rgba(34,211,238,.55);box-shadow:0 0 28px rgba(34,211,238,.15);}
.pf-card-head{display:flex;gap:12px;align-items:center;}
.pf-rank{font-family:'JetBrains Mono',monospace;font-weight:600;font-size:.95rem;color:#05060c;background:linear-gradient(135deg,#C9BEFF,#22D3EE);
 border-radius:10px;padding:4px 9px;}
.pf-card-title{flex:1;font-weight:600;font-size:1.06rem;color:#fff;line-height:1.25;}
.pf-card-sub{font-family:'JetBrains Mono',monospace;font-size:.7rem;color:var(--pf-mut);font-weight:400;margin-top:2px;}
.pf-ring{--p:0;--c:#7C5CFF;width:58px;height:58px;border-radius:50%;display:grid;place-items:center;flex:none;
 background:conic-gradient(var(--c) calc(var(--p)*1%),rgba(255,255,255,.07) 0);}
.pf-ring span{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;background:#0B1022;font-weight:700;color:#fff;font-size:.95rem;}
.pf-beat{font-size:.88rem;color:#D7DBEC;margin:6px 0;line-height:1.4;}
.pf-beat b{font-family:'JetBrains Mono',monospace;font-size:.66rem;letter-spacing:.14em;padding:2px 7px;border-radius:6px;margin-right:7px;
 background:rgba(34,211,238,.14);color:#A5F3FC;}
.pf-beat.cliff b{background:rgba(244,114,182,.15);color:#FBCFE8;}
.pf-beat.cap b{background:rgba(251,191,36,.14);color:#FDE68A;}
.pf-tl{margin:8px 0 4px;}
.pf-tl-row{display:flex;align-items:center;gap:8px;margin:3px 0;}
.pf-tl-ep{font-family:'JetBrains Mono',monospace;font-size:.68rem;color:var(--pf-mut);width:34px;}
.pf-tl-track{position:relative;flex:1;height:9px;border-radius:6px;background:rgba(255,255,255,.06);overflow:hidden;}
.pf-tl-seg{position:absolute;top:0;height:100%;border-radius:6px;background:linear-gradient(90deg,#7C5CFF,#22D3EE);box-shadow:0 0 10px rgba(34,211,238,.6);}
.pf-dims{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:8px;}
.pf-dim .n{font-family:'JetBrains Mono',monospace;font-size:.62rem;letter-spacing:.1em;color:var(--pf-mut);text-transform:uppercase;}
.pf-dim .b{height:6px;border-radius:4px;background:rgba(255,255,255,.07);margin-top:3px;overflow:hidden;}
.pf-dim .b i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,#7C5CFF,#22D3EE);}
.pf-stranger{font-size:.8rem;color:var(--pf-mut);margin-top:8px;border-top:1px dashed var(--pf-line);padding-top:7px;}
.pf-foot{color:var(--pf-mut);font-size:.78rem;text-align:center;margin:28px 0 8px;font-family:'JetBrains Mono',monospace;}
@media (prefers-reduced-motion: reduce){.pf-hero:after,.pf-title,.pf-dot,.pf-step.active .pf-node{animation:none!important;}}
@media (max-width:640px){.pf-dims{grid-template-columns:repeat(3,1fr);} .pf-hero{padding:20px 18px;}}
</style>
"""

STAGES = [("parse", "Parse"), ("mine", "Mine + repair"), ("rules", "Rules"), ("judge", "Blind judge"),
          ("cold", "Stranger test"), ("captions", "Captions"), ("rank", "Rank ×3"), ("final", "Final list")]


def chip(text, kind=""):
    return f'<span class="pf-chip {kind}">{E(str(text))}</span>'


def hero(chips_html: str) -> str:
    return ('<div class="pf-hero"><div class="pf-eyebrow"><span class="pf-dot"></span>AI FIRST-PASS EDITOR · MICRODRAMA PROMOS</div>'
            '<div class="pf-title">Promo Finder</div>'
            '<p class="pf-sub">Reads a timestamped screenplay and surfaces ranked 20–60 s promos: a hook in the first 3 s, '
            'a cut on an unresolved cliffhanger, and a clip a stranger can follow. You approve; it does the first pass.</p>'
            f'<div class="pf-chips">{chips_html}</div></div>')


AI_ONLY = {"cold", "captions", "rank"}   # skipped by the keyword engine


def stepper(active: int, done_all: bool = False, ai: bool = True) -> str:
    out = ['<div class="pf-steps">']
    for i, (key, label) in enumerate(STAGES):
        state = "done" if done_all or i < active else "active" if i == active else ""
        if not ai and key in AI_ONLY:
            state = "skip"
        mark = {"done": "✓", "skip": "–"}.get(state, str(i + 1))
        if i:
            out.append(f'<div class="pf-link {"done" if done_all or i <= active else ""}"></div>')
        out.append(f'<div class="pf-step {state}"><div class="pf-node">{mark}</div>{E(label)}</div>')
    out.append("</div>")
    return "".join(out)


def terminal(lines: list[str]) -> str:
    return f'<div class="pf-term">{E(chr(10).join(lines[-10:])) or "waiting…"}</div>'


def kpis(items: list[tuple[str, str, str]]) -> str:
    return '<div class="pf-kpis">' + "".join(
        f'<div class="pf-kpi"><div class="l">{E(l)}</div><div class="v">{E(v)}</div><div class="s">{E(s)}</div></div>'
        for l, v, s in items) + "</div>"


def score_color(s: float) -> str:
    return "#34D399" if s >= 75 else "#22D3EE" if s >= 65 else "#7C5CFF" if s >= 55 else "#FBBF24"


def seg_label(p: dict) -> str:
    return " + ".join(f"E{s['episode']:02d} {s['start_tc']}–{s['end_tc']}" for s in p["segments"])


def timeline(p: dict, episodes: dict) -> str:
    rows, by_ep = [], {}
    for s in p["segments"]:
        by_ep.setdefault(s["episode"], []).append(s)
    for ep, segs in by_ep.items():
        dur = max(getattr(episodes.get(ep), "duration", 0) or 0, max(s["end"] for s in segs), 1)
        bars = "".join(f'<div class="pf-tl-seg" style="left:{100 * s["start"] / dur:.2f}%;width:{max(0.8, 100 * (s["end"] - s["start"]) / dur):.2f}%"></div>'
                       for s in segs)
        rows.append(f'<div class="pf-tl-row"><div class="pf-tl-ep">E{ep:02d}</div><div class="pf-tl-track">{bars}</div></div>')
    return f'<div class="pf-tl">{"".join(rows)}</div>'


FLAG_KIND = [("cold open", "warn", "repeats footage"), ("compressed", "warn", "jump cut"),
             ("final beat", "", "episode ending"), ("over word limit", "warn", "caption too long"),
             ("repaired", "ok", "repaired by miner"), ("montage", "cyan", "montage")]


def card(p: dict, episodes: dict, rank_label: str | None = None) -> str:
    j, c = p.get("judge") or {}, p.get("cold") or {}
    sc = None if p.get("score") is None else float(p["score"])
    ring = ("" if sc is None else
            f'<div class="pf-ring" style="--p:{sc:.0f};--c:{score_color(sc)}"><span>{sc:.0f}</span></div>')
    chips = [chip(f"⏱ {p['duration']:.0f}s", "cyan"), chip(f"hook +{p.get('hook_offset', 0):.1f}s")]
    if p.get("trope_family"):
        chips.append(chip(p["trope_family"]))
    seen = set()
    for f in p.get("flags", []):
        for key, kind, label in FLAG_KIND:
            if key in f and label not in seen:
                chips.append(chip(label, kind)); seen.add(label)
    dims = "".join(f'<div class="pf-dim"><div class="n">{n} {j.get(k, "–")}</div><div class="b"><i style="width:{20 * (j.get(k) or 0)}%"></i></div></div>'
                   for k, n in (("hook", "hook"), ("cliffhanger", "cliff"), ("standalone", "alone"), ("trope", "trope"), ("visual", "visual")))
    cap = (f'<div class="pf-beat cap"><b>CAPTION</b>{E(p["context_caption"])}</div>' if p.get("context_caption") else "")
    stranger = (f'<div class="pf-stranger">🧍 Stranger: “{E(c.get("what_is_happening", ""))}” · clarity {c.get("clarity")}/5 · '
                f'keep watching {c.get("keep_watching")}/5</div>' if c else "")
    return (f'<div class="pf-card"><div class="pf-card-head"><div class="pf-rank">{E(rank_label or "#" + str(p.get("rank", "")))}</div>'
            f'<div class="pf-card-title">{E(p.get("title") or p["id"])}<div class="pf-card-sub">{E(p["id"])} · {E(seg_label(p))}</div></div>'
            f'{ring}</div>'
            f'<div class="pf-chips">{"".join(chips)}</div>'
            f'<div class="pf-beat"><b>HOOK</b>{E(str(p.get("hook") or ""))}</div>'
            f'<div class="pf-beat cliff"><b>CLIFF</b>{E(str(p.get("cliffhanger") or ""))}</div>{cap}'
            f'{timeline(p, episodes)}{"<div class=pf-dims>" + dims + "</div>" if j else ""}{stranger}</div>')
