"""Streamlit UI: upload a show -> run -> ranked promos an editor can act on.

Tabs after a run: Leaderboard (filter/sort promo cards), Show map (charts), Compare (two promos side by
side), Review (approve/reject, bulk actions, decisions.csv), Studio (long cuts + ad pack on demand) and
Export. Presentation lives in promo_finder/ui_theme.py; pipeline logic is unchanged.
"""
import io
import json
import os
import tempfile
import time
import zipfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import yaml

from promo_finder import ui_theme as T
from promo_finder.assemble import clip_text
from promo_finder.pipeline import Run
from promo_finder.saved_run import load_saved_run

ROOT = Path(__file__).parent
# USD per 1M tokens (input, output). Approximate paid list prices; check the provider's page before quoting.
PRICE_PER_M = {"gemini-flash-lite-latest": (0.10, 0.40), "openai/gpt-oss-120b": (0.15, 0.75),
               "openai/gpt-oss-20b": (0.075, 0.30), "llama-3.3-70b-versatile": (0.59, 0.79)}
KEYS = {"GEMINI_API_KEY": "Gemini", "GROQ_API_KEY": "Groq", "OPENROUTER_API_KEY": "OpenRouter"}
# Secret names people commonly use for the same key (matched case-insensitively, also inside [sections]).
ALIASES = {"GEMINI_API_KEY": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY", "GOOGLE_GENAI_API_KEY", "GEMINI"],
           "GROQ_API_KEY": ["GROQ_API_KEY", "GROQ_KEY", "GROQ"],
           "OPENROUTER_API_KEY": ["OPENROUTER_API_KEY", "OPENROUTER_KEY", "OPENROUTER"]}


def server_secrets() -> tuple[dict[str, str], str]:
    """Every string secret as {UPPERCASE NAME: value}, flattened across [sections]; plus an error note.
    Values never leave the server; only names are ever shown (in the key help, when nothing matched)."""
    flat = {}

    def walk(d):
        for k, v in d.items():
            if isinstance(v, str):
                flat.setdefault(str(k).strip().upper(), v.strip().strip('"').strip())
            elif hasattr(v, "items"):
                walk(v)
    try:
        walk(st.secrets)
    except Exception as e:      # no secrets file, or a TOML syntax error in it
        return flat, type(e).__name__
    return flat, ""
CACHE = Path(tempfile.gettempdir()) / "promo_llm_cache"

st.set_page_config(page_title="Promo Finder", page_icon="🎬", layout="wide", initial_sidebar_state="auto")
st.markdown(T.CSS, unsafe_allow_html=True)
cfg = yaml.safe_load((ROOT / "models.yaml").read_text(encoding="utf-8"))

# ------------------------------------------------------------------ sidebar: control deck
with st.sidebar:
    st.markdown('<div class="pf-section">⚙ CONTROL DECK</div>', unsafe_allow_html=True)
    mode = st.radio("Engine", ["AI (LLM)", "Keyword baseline (no AI)"], index=0,
                    help="Keyword baseline = no model calls at all; useful as a free comparison.")
    profiles = list(cfg["profiles"])
    profile = st.selectbox("Model profile", profiles, index=profiles.index(cfg["default_profile"]),
                           help="Which model does which job (models.yaml). gemini_groq puts a different model family on the judge.")
    with st.expander("Model map for this profile"):
        st.json(cfg["profiles"][profile], expanded=True)
    st.markdown('<div class="pf-section">🔑 KEYS</div>', unsafe_allow_html=True)
    key_state, session_keys = {}, {}
    secrets, secrets_err = server_secrets()
    for env, name in KEYS.items():
        secret = next((secrets[a] for a in ALIASES[env] if secrets.get(a)), "")
        if secret and not os.environ.get(env):
            os.environ[env] = secret          # the server's own key: the same for every visitor
        v = st.text_input(f"{name} key", value="", type="password", key=f"key_{env}",
                          help="Bring your own key: used only for runs in this browser session, never stored." +
                               (" A server key is already configured." if secret else ""))
        if v:
            session_keys[env] = v.strip()     # this session only: passed to its own LLM client, not os.environ
        key_state[name] = "yours" if v else "server" if secret else "env" if os.environ.get(env) else ""
    st.markdown("".join(T.chip(f"{n} ● {s}", "ok") if s else T.chip(f"{n} ○ none") for n, s in key_state.items()),
                unsafe_allow_html=True)
    if not any(key_state.values()):
        with st.expander("No server key found: why?"):
            st.caption("The app looks for secrets named " + ", ".join(ALIASES["GEMINI_API_KEY"][:3]) + " (Gemini) and "
                       + ", ".join(ALIASES["GROQ_API_KEY"][:2]) + " (Groq), in any [section], any letter case.")
            st.caption(f"Secrets file: {'not readable (' + secrets_err + ')' if secrets_err else 'readable'}; "
                       f"secret names found: {', '.join(sorted(secrets)) or 'none'}.")
    st.markdown('<div class="pf-section">🎛 TUNING</div>', unsafe_allow_html=True)
    max_eps = st.number_input("Episodes to process (0 = all)", 0, 500, 0)
    judge_top = st.slider("Shortlist size for the judge", 10, 60, 40)
    cold_top = st.slider("Clips given the stranger test", 0, 30, 15)
    use_cache = st.toggle("Reuse cached model replies", True, help="Same prompt → same reply from disk, free.")

ai = mode.startswith("AI")
chips = [T.chip("engine: " + ("AI" if ai else "keyword"), "cyan"), T.chip("profile: " + profile)]
chips += [T.chip(f"{n} key ✓", "ok") for n, s in key_state.items() if s]
if ai and not any(key_state.values()):
    chips.append(T.chip("no API key: AI steps will fall back to keywords", "warn"))
st.markdown(T.hero("".join(chips)), unsafe_allow_html=True)

# ------------------------------------------------------------------ input
st.markdown('<div class="pf-section">01 · INPUT</div>', unsafe_allow_html=True)
src = st.radio("Input", ["📤 Upload a show (.zip of episode .txt files)", "🧪 Demo show (synthetic, 3 episodes)",
                         "💼 Second demo: billionaire revenge (4 episodes, other file format)",
                         "📂 Open a saved run (.zip of a run's output folder)"],
               horizontal=True, label_visibility="collapsed")
data = None
saved_mode = src.startswith("📂")
if saved_mode:
    st.caption("Re-open a finished run without re-running it: zip an `outputs/<run>` folder, or use "
               "\"All raw outputs (zip)\" from the Export tab of an earlier run.")
    up = st.file_uploader("Saved run zip", type=["zip"], label_visibility="collapsed", key="saved_zip")
    if up and st.session_state.get("saved_id") != up.file_id:
        try:
            st.session_state["result"] = load_saved_run(up.getvalue(), profile)
            st.session_state["saved_id"] = up.file_id
            for k in ("longcuts", "adpack"):
                st.session_state.pop(k, None)
            st.toast("📂 Saved run loaded")
        except Exception as e:
            st.error(f"Could not open this zip as a saved run: {e}")
elif src.startswith("📤"):
    up = st.file_uploader("Show zip", type=["zip"], label_visibility="collapsed")
    if up:
        data = up.getvalue()
elif src.startswith("🧪"):
    data = str(ROOT / "sample_input" / "demo_show")
else:
    data = str(ROOT / "sample_input" / "revenge_show")

v = None
if data is not None:   # free format check before any model call
    from promo_finder.validate import validate
    vpath = data
    if isinstance(data, bytes):
        vpath = Path(tempfile.mkdtemp()) / "upload.zip"; vpath.write_bytes(data)
    v = validate(vpath)
    fc = [T.chip(f"{v.get('episodes_found', 0)} episodes", "ok" if v.get("ok") else "bad"),
          T.chip(f"{v.get('blocks_total', 0)} timed blocks", "cyan"),
          T.chip(f"timestamps {', '.join(v.get('timestamp_styles') or []) or '?'}")]
    if v.get("crlf_files"):
        fc.append(T.chip(f"{v['crlf_files']} CRLF files (handled)"))
    fc += [T.chip(p, "warn" if v.get("ok") else "bad") for p in v.get("problems", [])[:6]]
    st.markdown(f'<div class="pf-chips">{"".join(fc)}</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------ launch
go = False
if not saved_mode:
    st.markdown('<div class="pf-section">02 · LAUNCH</div>', unsafe_allow_html=True)
    n_eps = min(v.get("episodes_found", 0), max_eps or 10**6) if v else 0
    est = (n_eps + 1 + -(-judge_top // 8) + 3 * cold_top + 3) if ai else 0   # miner + montage + judge + cold/caption/re-test + rank
    lc1, lc2 = st.columns([1.3, 2])
    go = lc1.button("🚀  Find promos", type="primary", disabled=data is None or (v is not None and not v.get("ok")),
                    width="stretch")
    if v is None:
        lc2.markdown(f'<div class="pf-chips">{T.chip("choose an input to see the call estimate")}</div>', unsafe_allow_html=True)
    else:
        lc2.markdown(f'<div class="pf-chips">{T.chip(f"≈ {est} model calls (estimate, before cache)" if ai else "0 model calls · free", "cyan")}'
                     f'{T.chip("repair calls extra, only when a pick fails a timing rule") if ai else ""}</div>', unsafe_allow_html=True)

if go:
    work = Path(tempfile.mkdtemp(prefix="promo_"))
    out = work / "outputs"
    llm = None
    if ai:
        from promo_finder.llm import LLM
        llm = LLM(ROOT / "models.yaml", profile, cache_dir=CACHE, use_cache=use_cache, keys=session_keys)
    steps_box, bar, term = st.empty(), st.progress(0.0, "Starting"), st.empty()
    state = {"stage": 0, "logs": []}
    stage_of = {"mine": 1, "judge": 3, "cold viewer": 4, "captions": 5}

    def show():
        steps_box.markdown(T.stepper(state["stage"], ai=ai), unsafe_allow_html=True)
        term.markdown(T.terminal(state["logs"]), unsafe_allow_html=True)

    def log(s):
        state["logs"].append(s)
        if "candidates:" in s:
            state["stage"] = max(state["stage"], 3)
        elif s.split("] ", 1)[-1].startswith("captions:"):
            state["stage"] = max(state["stage"], 6)
        show()

    def progress(stage, i, n):
        state["stage"] = max(state["stage"], stage_of.get(stage, state["stage"]))
        bar.progress(min(1.0, (i + 1) / max(n, 1)), f"{stage}: {i + 1}/{n}")
        show()

    show()
    try:
        run = Run(data, out, llm=llm, mode="llm" if llm else "heuristic", judge_top=judge_top, cold_top=cold_top,
                  max_eps=max_eps or None, log=log, progress=progress)
        summary = run.run()
        st.session_state["result"] = {"out": str(out), "summary": summary, "episodes": run.episodes,
                                      "ai": bool(llm), "profile": profile}
        for k in ("longcuts", "adpack"):
            st.session_state.pop(k, None)
        steps_box.markdown(T.stepper(len(T.STAGES), done_all=True, ai=ai), unsafe_allow_html=True)
        st.toast(f"✨ {summary['ranked']} promos ranked in {summary['runtime_s']:.0f}s")
    except Exception as e:
        st.error(f"Run failed: {e}")
    bar.empty()

res = st.session_state.get("result")
if not res:
    st.markdown('<div class="pf-foot">Pick an input and press Find promos. The demo shows run in seconds.</div>',
                unsafe_allow_html=True)
    st.stop()

# ------------------------------------------------------------------ results
out, summary, episodes = Path(res["out"]), res["summary"], res["episodes"]
ranked = json.loads((out / "03_promos_ranked.json").read_text(encoding="utf-8"))
cands = json.loads((out / "02_all_candidates.json").read_text(encoding="utf-8"))
by_id = {p["id"]: p for p in ranked}
usage = (summary.get("llm_stats") or {}).get("by_model") or {}
cost = sum(PRICE_PER_M.get(m.split(":", 1)[-1], (0.10, 0.40))[0] * u["in"] / 1e6
           + PRICE_PER_M.get(m.split(":", 1)[-1], (0.10, 0.40))[1] * u["out"] / 1e6 for m, u in usage.items())
calls = sum(u["calls"] for u in usage.values())
top_score = max([p.get("score") or 0 for p in ranked] or [0])
st.markdown('<div class="pf-section">03 · RESULTS</div>', unsafe_allow_html=True)
if res.get("saved"):
    st.markdown('<div class="pf-chips">' + T.chip("📂 saved run: opened from its output files, nothing re-run", "cyan")
                + T.chip(f"originally run with: {summary.get('mode')}") + "</div>", unsafe_allow_html=True)
st.markdown(T.kpis([
    ("Episodes", str(summary["episodes"]), summary["show"][:28]),
    ("Candidates", str(summary["candidates_total"]), "proposed by the miner" if res["ai"] else "keyword engine"),
    ("Passed rules", str(summary["candidates_valid"]), f"{100 * summary['candidates_valid'] / max(1, summary['candidates_total']):.0f}% · hook ≤3 s, 20–60 s, clean cuts"),
    ("Ranked", str(summary["ranked"]), f"top score {top_score:.0f}/100"),
    ("Model calls", str(calls), f"≈ ${cost:.4f} at paid list prices" if usage else "cache or keyword: $0"),
    ("Runtime", f"{summary['runtime_s']:.0f}s", f"repairs {summary.get('repair_loop', {}).get('fixed_by_miner', 0)} by miner"),
]), unsafe_allow_html=True)
if summary.get("errors"):
    st.warning(f"{len(summary['errors'])} model errors (fell back to the keyword engine where needed). See the Export tab for the run log.")

tabs = st.tabs(["🏆 Leaderboard", "🗺 Show map", "⚔ Compare", "✅ Review", "🧬 Studio", "📦 Export"])

# ---------- Leaderboard
with tabs[0]:
    f1, f2, f3, f4 = st.columns([2, 1.2, 1.6, 1.2])
    q = f1.text_input("🔎 Search", placeholder="title, hook, cliffhanger, trope…")
    min_score = f2.slider("Min score", 0, 100, 0)
    fams = sorted({p.get("trope_family") or "other" for p in ranked})
    pick_fams = f3.multiselect("Trope families", fams, placeholder="All")
    sort = f4.selectbox("Sort by", ["Rank", "Score", "Hook", "Cliffhanger", "Keep watching", "Shortest"])
    g1, g2 = st.columns([1, 3])
    clean_only = g1.toggle("Hide flagged picks", False, help="Hide picks that repeat footage, use a jump cut or break the caption limit")
    show_n = g2.select_slider("Cards shown", options=[6, 10, 20, 40, 100], value=10)

    def keep(p):
        hay = " ".join(str(p.get(k, "")) for k in ("title", "hook", "cliffhanger", "trope", "why")).lower()
        if q and q.lower() not in hay:
            return False
        if (p.get("score") or 0) < min_score or (pick_fams and (p.get("trope_family") or "other") not in pick_fams):
            return False
        return not (clean_only and any(k in f for f in p.get("flags", []) for k in ("cold open", "compressed", "word limit")))

    keyf = {"Rank": lambda p: p["rank"], "Score": lambda p: -(p.get("score") or 0),
            "Hook": lambda p: -(p.get("judge") or {}).get("hook", 0), "Cliffhanger": lambda p: -(p.get("judge") or {}).get("cliffhanger", 0),
            "Keep watching": lambda p: -(p.get("cold") or {}).get("keep_watching", 0), "Shortest": lambda p: p["duration"]}[sort]
    shown = sorted([p for p in ranked if keep(p)], key=keyf)[:show_n]
    st.caption(f"{len(shown)} shown · scores are model-judged and directional")
    cols = st.columns(2)
    for i, p in enumerate(shown):
        with cols[i % 2]:
            st.markdown(T.card(p, episodes), unsafe_allow_html=True)
            with st.expander("Script, animatic and details"):
                if p.get("ad_hook_text"):
                    st.markdown(f"**Ad hook text:** {p['ad_hook_text']}")
                st.markdown(f"**Why it works:** {p.get('why', '')}" + (f"  \n**Why post here:** {p['rank_reason']}" if p.get("rank_reason") else ""))
                if p.get("judge", {}).get("critique"):
                    st.markdown(f"**Judge's critique:** {p['judge']['critique']}")
                if p.get("flags"):
                    st.caption("Flags: " + ", ".join(p["flags"]))
                st.code(clip_text(episodes, p), language=None)
                mp4 = out / "animatics" / f"{p['id']}.mp4"
                if st.button("🎞 Render animatic (silent 9:16 preview)", key=f"a_{p['id']}") and not mp4.exists():
                    with st.spinner("Rendering…"):
                        import imageio_ffmpeg
                        from promo_finder.animatic import render
                        mp4.parent.mkdir(exist_ok=True)
                        eps = json.loads((out / "00_episodes_parsed.json").read_text(encoding="utf-8"))
                        render(p, eps, mp4, imageio_ffmpeg.get_ffmpeg_exe())
                if mp4.exists():
                    st.columns([1, 1.4])[0].video(mp4.read_bytes())

# ---------- Show map
with tabs[1]:
    rows = [{"episode": s["episode"], "start": s["start"], "end": s["end"], "rank": p["rank"], "title": p.get("title"),
             "score": p.get("score") or 0, "length_s": p["duration"]} for p in ranked for s in p["segments"]]
    if rows:
        st.markdown("**Where the promos sit in the show** · each bar is a cut (x = episode, y = seconds into it), coloured by score")
        ch = alt.Chart(pd.DataFrame(rows)).mark_bar(size=9, cornerRadius=3).encode(
            x=alt.X("episode:O", title="episode", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("start:Q", title="seconds into episode"), y2="end:Q",
            color=alt.Color("score:Q", scale=alt.Scale(scheme="plasma"), title="score"),
            tooltip=["rank", "title", "episode", "start", "end", "score", "length_s"]).properties(height=320)
        st.altair_chart(ch, width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Funnel**")
        stages = [("proposed", summary["candidates_total"]), ("passed rules", summary["candidates_valid"]),
                  ("judged + ranked", len(ranked)), ("stranger-tested", sum(1 for p in ranked if p.get("cold"))),
                  ("top 10", min(10, len(ranked)))]
        fdf = pd.DataFrame(stages, columns=["stage", "n"])
        st.altair_chart(alt.Chart(fdf).mark_bar(cornerRadiusEnd=6, color="#7C5CFF").encode(
            y=alt.Y("stage:N", sort=None, title=None), x=alt.X("n:Q", title=None), tooltip=["stage", "n"]).properties(height=210)
            + alt.Chart(fdf).mark_text(align="left", dx=4, color="#E6E9F5").encode(y=alt.Y("stage:N", sort=None), x="n:Q", text="n:Q"),
            width="stretch")
    with c2:
        st.markdown("**Trope families in the ranked list**")
        tdf = pd.Series([p.get("trope_family") or "other" for p in ranked]).value_counts().reset_index()
        tdf.columns = ["family", "n"]
        st.altair_chart(alt.Chart(tdf).mark_arc(innerRadius=55, cornerRadius=4).encode(
            theta="n:Q", color=alt.Color("family:N", scale=alt.Scale(scheme="tableau10"), title=None),
            tooltip=["family", "n"]).properties(height=230), width="stretch")
    judged = [p for p in ranked[:12] if p.get("judge")]
    if judged:
        st.markdown("**Judge heatmap, top picks** (1–5 per rubric dimension)")
        hdf = pd.DataFrame([{"promo": f"#{p['rank']} {str(p.get('title'))[:34]}", "dim": d, "value": p["judge"][k]}
                            for p in judged for k, d in (("hook", "hook"), ("cliffhanger", "cliffhanger"), ("standalone", "stands alone"),
                                                         ("trope", "trope"), ("visual", "visual"))])
        st.altair_chart(alt.Chart(hdf).mark_rect(cornerRadius=4).encode(
            x=alt.X("dim:N", title=None, sort=None, axis=alt.Axis(labelAngle=0, orient="top")),
            y=alt.Y("promo:N", title=None, sort=None, axis=alt.Axis(labelLimit=280, labelOverlap=False)),
            color=alt.Color("value:Q", scale=alt.Scale(domain=[1, 5], scheme="purpleblue"), title="score"),
            tooltip=["promo", "dim", "value"]).properties(height=32 * len(judged) + 40), width="stretch")
    rej = summary.get("rejected_by_reason") or {}
    if rej:
        st.markdown("**Why candidates were rejected**")
        st.altair_chart(alt.Chart(pd.DataFrame(list(rej.items()), columns=["reason", "n"])).mark_bar(cornerRadiusEnd=5, color="#F472B6").encode(
            y=alt.Y("reason:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)), x=alt.X("n:Q", title=None),
            tooltip=["reason", "n"]).properties(height=34 * len(rej) + 20),
            width="stretch")

# ---------- Compare
with tabs[2]:
    labels = [f"#{p['rank']} {p.get('title')}" for p in ranked]
    if len(ranked) >= 2:
        a1, a2 = st.columns(2)
        la = a1.selectbox("Promo A", labels, index=0)
        lb = a2.selectbox("Promo B", labels, index=1)
        pa, pb = ranked[labels.index(la)], ranked[labels.index(lb)]
        a1.markdown(T.card(pa, episodes), unsafe_allow_html=True)
        a2.markdown(T.card(pb, episodes), unsafe_allow_html=True)
        dims = [("hook", "hook"), ("cliffhanger", "cliffhanger"), ("standalone", "stands alone"), ("trope", "trope"), ("visual", "visual")]
        cdf = pd.DataFrame([{"promo": tag, "dim": d, "value": (p.get("judge") or {}).get(k, 0)}
                            for tag, p in (("A", pa), ("B", pb)) for k, d in dims]
                           + [{"promo": tag, "dim": "keep watching", "value": (p.get("cold") or {}).get("keep_watching", 0)}
                              for tag, p in (("A", pa), ("B", pb))])
        st.altair_chart(alt.Chart(cdf).mark_bar(cornerRadiusEnd=4).encode(
            x=alt.X("dim:N", title=None, sort=None), xOffset="promo:N", y=alt.Y("value:Q", scale=alt.Scale(domain=[0, 5]), title=None),
            color=alt.Color("promo:N", scale=alt.Scale(range=["#7C5CFF", "#22D3EE"]), title=None),
            tooltip=["promo", "dim", "value"]).properties(height=260), width="stretch")
        diff = (pa.get("score") or 0) - (pb.get("score") or 0)
        st.caption(f"Score gap A − B: {diff:+.1f} (model-judged, directional). The ranker put A at #{pa['rank']} and B at #{pb['rank']}.")
    else:
        st.info("Need at least two ranked promos to compare.")

# ---------- Review
with tabs[3]:
    decisions = st.session_state.setdefault("decisions", {})
    top = ranked[:10]
    b1, b2, b3 = st.columns([1.2, 1, 1])
    thr = b1.number_input("Approve every pick scoring at least", 0, 100, 70)
    if b2.button("⚡ Bulk approve", width="stretch"):
        for p in top:
            if (p.get("score") or 0) >= thr:
                st.session_state[f"v_{p['id']}"] = "approve"
    if b3.button("↺ Reset decisions", width="stretch"):
        for p in top:
            st.session_state[f"v_{p['id']}"] = "undecided"
    for p in top:
        k = p["id"]
        score_txt = "%.0f/100" % (p.get("score") or 0)
        st.markdown('<div class="pf-chips">' + T.chip("#" + str(p["rank"]), "cyan") + T.chip(score_txt)
                    + T.chip(T.seg_label(p)) + "</div>", unsafe_allow_html=True)
        r1, r2, r3, r4 = st.columns([2.2, 1.6, 1.3, 2])
        r1.markdown(f"**{p.get('title')}**  \n{p.get('hook')}")
        verdict = r2.radio("Decision", ["undecided", "approve", "reject"], key=f"v_{k}", horizontal=True, label_visibility="collapsed")
        reason = r3.selectbox("Reject reason", ["", "weak hook", "needs context", "spoiler", "bad cut", "other"],
                              key=f"r_{k}", disabled=verdict != "reject", label_visibility="collapsed")
        note = r4.text_input("Note", key=f"n_{k}", placeholder="note for the editor", label_visibility="collapsed")
        decisions[k] = {"rank": p["rank"], "promo_id": k, "title": p.get("title"), "segments": T.seg_label(p),
                        "decision": verdict, "reason": reason if verdict == "reject" else "", "note": note}
    vals = [d["decision"] for d in decisions.values() if d["promo_id"] in {p["id"] for p in top}]
    na, nr = vals.count("approve"), vals.count("reject")
    st.progress((na + nr) / max(1, len(top)), f"{na} approved · {nr} rejected · {len(top) - na - nr} undecided")
    st.download_button(f"⬇ Editor decisions (CSV, {na + nr} decided)", pd.DataFrame(list(decisions.values())).to_csv(index=False),
                       "decisions.csv", disabled=not decisions)

# ---------- Studio: long cuts + ad pack, on demand
with tabs[4]:
    if not res["ai"]:
        st.info("The Studio uses model calls. Run with the AI engine to use it.")
    else:
        from promo_finder.llm import LLM
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("#### 🎬 Long cuts · 90 s – 3 min")
            st.caption("1 call chains promos that already passed every rule; code checks order, repeated footage and length, "
                       "then a stranger test per cut. For paid UA.")
            if st.button("Build long cuts", key="btn_long", width="stretch"):
                from promo_finder.longcut import make_long_cuts
                with st.spinner("Chaining approved promos…"):
                    try:
                        llm = LLM(ROOT / "models.yaml", res["profile"], cache_dir=CACHE, keys=session_keys)
                        st.session_state["longcuts"] = make_long_cuts(cands, episodes, llm)
                    except Exception as e:
                        st.session_state["longcuts"] = {"cuts": [], "note": f"failed: {e}"}
            lc = st.session_state.get("longcuts")
            if lc:
                if lc.get("note"):
                    st.info(lc["note"])
                for c in lc["cuts"]:
                    tag = "✓ passed" if c["status"] == "ok" else "✗ rejected"
                    st.markdown(T.card({**c, "score": None}, episodes, rank_label=c["id"]), unsafe_allow_html=True)
                    st.caption(f"{tag} · parts: {' → '.join(c['parts'])} · " + "; ".join(c["flags"] + c["reject_reasons"]))
        with s2:
            st.markdown("#### 📣 Ad pack")
            st.caption("Per promo: 3 A/B post captions, 5 hashtags, a CTA, a platform and the viewer's open question. Drafts for a marketer.")
            n_pack = st.slider("Top N promos", 1, 10, 3, key="n_pack")
            if st.button("Write ad pack", key="btn_pack", width="stretch"):
                from promo_finder.adpack import ad_pack_for
                packs, bar2 = [], st.progress(0.0)
                llm = LLM(ROOT / "models.yaml", res["profile"], cache_dir=CACHE, keys=session_keys)
                for i, p in enumerate(ranked[:n_pack]):
                    try:
                        packs.append(ad_pack_for(p, episodes, llm))
                    except Exception as e:
                        st.warning(f"{p['id']}: {e}")
                    bar2.progress((i + 1) / n_pack, f"{i + 1}/{n_pack}")
                bar2.empty()
                st.session_state["adpack"] = packs
            for pk in st.session_state.get("adpack") or []:
                st.markdown(f'<div class="pf-card"><div class="pf-card-head"><div class="pf-rank">#{pk["rank"]}</div>'
                            f'<div class="pf-card-title">{T.E(str(pk["title"]))}<div class="pf-card-sub">{T.E(pk["platform"])} · '
                            f'{pk["recommended_length_s"]}s</div></div></div>'
                            + "".join(f'<div class="pf-beat"><b>{"ABC"[i]}</b>{T.E(c)}</div>' for i, c in enumerate(pk["post_captions"]))
                            + f'<div class="pf-beat cliff"><b>CTA</b>{T.E(pk["cta"])}</div>'
                            + f'<div class="pf-chips">{"".join(T.chip(h, "cyan") for h in pk["hashtags"])}</div>'
                            + f'<div class="pf-stranger">❓ Viewer is left asking: {T.E(pk["viewer_question"])}</div></div>',
                            unsafe_allow_html=True)

# ---------- Export
with tabs[5]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in out.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(out))
    e1, e2, e3 = st.columns(3)
    e1.download_button("⬇ Ranked promos (CSV)", (out / "promos_ranked.csv").read_bytes(), "promos_ranked.csv", width="stretch")
    e2.download_button("⬇ Edit decision list (CSV)", (out / "edit_decision_list.csv").read_bytes(), "edit_decision_list.csv", width="stretch")
    e3.download_button("⬇ All raw outputs (zip)", buf.getvalue(), f"promo_outputs_{time.strftime('%H%M')}.zip", width="stretch")
    e4, e5, e6 = st.columns(3)
    e4.download_button("⬇ Readable report (Markdown)", (out / "promos_ranked.md").read_bytes(), "promos_ranked.md", width="stretch")
    lc = st.session_state.get("longcuts") or {}
    ok_cuts = [c for c in lc.get("cuts", []) if c["status"] == "ok"]
    if ok_cuts:
        edl = pd.DataFrame([{"long_cut": c["id"], "segment": k, "episode": s["episode"], "start": s["start_tc"], "end": s["end_tc"],
                             "length_s": round(s["end"] - s["start"], 2)} for c in ok_cuts for k, s in enumerate(c["segments"], 1)])
        e5.download_button("⬇ Long-cut EDL (CSV)", edl.to_csv(index=False), "long_cuts_edl.csv", width="stretch")
    if st.session_state.get("adpack"):
        from promo_finder.adpack import to_markdown
        e6.download_button("⬇ Ad pack (Markdown)", to_markdown(st.session_state["adpack"]), "ad_pack.md", width="stretch")
    with st.expander("Run log"):
        st.code((out / "run_log.txt").read_text(encoding="utf-8"), language=None)
    with st.expander("Run summary (JSON)"):
        st.json(summary)

st.markdown('<div class="pf-foot">Code does the exact work (timestamps, cuts, rules) · models make the judgement calls · '
            'an editor approves · every model reply is logged</div>', unsafe_allow_html=True)
