"""Streamlit UI: upload a show -> run -> ranked promos an editor can act on."""
import io
import json
import os
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from promo_finder.assemble import clip_text
from promo_finder.pipeline import Run

ROOT = Path(__file__).parent
st.set_page_config(page_title="Promo Finder", page_icon="🎬", layout="wide")
st.title("🎬 Promo Finder for microdramas")
st.caption("Reads a timestamped screenplay and proposes ranked 20-60 s promo clips: hook in the first 3 s, "
           "ends on a cliffhanger, understandable to a stranger. An editor approves; the tool does the first pass.")

with st.sidebar:
    st.header("Settings")
    mode = st.radio("Engine", ["AI (LLM)", "Keyword baseline (no AI)"], index=0)
    import yaml
    cfg = yaml.safe_load((ROOT / "models.yaml").read_text(encoding="utf-8"))
    profile = st.selectbox("Model profile (models.yaml)", list(cfg["profiles"]),
                           index=list(cfg["profiles"]).index(cfg["default_profile"]))
    st.json(cfg["profiles"][profile], expanded=False)
    for env in ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"]:
        try:
            secret = st.secrets.get(env, "")
        except Exception:
            secret = ""
        v = st.text_input(env, value="", type="password",
                          help="Bring your own key. Stored only in this session." + (" (a server key is configured)" if secret else ""))
        if v or secret:
            os.environ[env] = v or secret
    max_eps = st.number_input("Episodes to process (0 = all)", 0, 500, 0)
    judge_top = st.slider("Shortlist size for the judge", 10, 60, 40)
    cold_top = st.slider("Clips given the stranger test", 0, 30, 15)
    use_cache = st.checkbox("Reuse cached model replies", True)

src = st.radio("Input", ["Upload a show (.zip of episode .txt files)", "Demo show (synthetic, 3 episodes)"], horizontal=True)
data = None
if src.startswith("Upload"):
    up = st.file_uploader("Show zip", type=["zip"])
    if up:
        data = up.getvalue()
else:
    data = str(ROOT / "sample_input" / "demo_show")

if st.button("Find promos", type="primary", disabled=data is None):
    work = Path(tempfile.mkdtemp(prefix="promo_"))
    out = work / "outputs"
    llm = None
    if mode.startswith("AI"):
        from promo_finder.llm import LLM
        llm = LLM(ROOT / "models.yaml", profile, cache_dir=Path(tempfile.gettempdir()) / "promo_llm_cache", use_cache=use_cache)
    bar, status = st.progress(0.0, "Starting"), st.empty()
    logs = []

    def log(s):
        logs.append(s); status.code("\n".join(logs[-8:]))

    def progress(stage, i, n):
        bar.progress(min(1.0, (i + 1) / max(n, 1)), f"{stage}: {i + 1}/{n}")

    try:
        run = Run(data if isinstance(data, str) else data, out, llm=llm,
                  mode="llm" if llm else "heuristic", judge_top=judge_top, cold_top=cold_top,
                  max_eps=max_eps or None, log=log, progress=progress)
        summary = run.run()
        st.session_state["result"] = {"out": str(out), "summary": summary,
                                      "episodes": run.episodes}
    except Exception as e:
        st.error(f"Run failed: {e}")
    bar.empty()

res = st.session_state.get("result")
if res:
    out, summary = Path(res["out"]), res["summary"]
    ranked = json.loads((out / "03_promos_ranked.json").read_text(encoding="utf-8"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Episodes", summary["episodes"])
    c2.metric("Candidates found", summary["candidates_total"])
    c3.metric("Passed rules", summary["candidates_valid"])
    c4.metric("Runtime", f"{summary['runtime_s']:.0f}s")
    if summary.get("errors"):
        st.warning(f"{len(summary['errors'])} model errors (fell back to keyword engine where needed). See run_log.txt.")

    df = pd.read_csv(out / "promos_ranked.csv")
    st.subheader("Ranked promos (post #1 first)")
    st.dataframe(df[["rank", "title", "segments", "duration_s", "hook", "cliffhanger", "why", "score", "flags"]],
                 width="stretch", hide_index=True)

    st.subheader("Review the top picks")
    for p in ranked[:10]:
        segs = " + ".join(f"E{s['episode']} {s['start_tc']}-{s['end_tc']}" for s in p["segments"])
        with st.expander(f"#{p['rank']}  {p.get('title')}  |  {segs}  |  {p['duration']:.0f}s  |  score {p.get('score')}"):
            st.markdown(f"**Hook (+{p.get('hook_offset', 0):.1f}s):** {p.get('hook')}  \n"
                        f"**Cliffhanger:** {p.get('cliffhanger')}  \n**Why:** {p.get('why')}  \n"
                        + (f"**Why post here:** {p['rank_reason']}  \n" if p.get("rank_reason") else "")
                        + (f"**Stranger understood:** {p['cold']['what_is_happening']} "
                           f"(clarity {p['cold']['clarity']}/5, keep watching {p['cold']['keep_watching']}/5)" if p.get("cold") else ""))
            if p.get("judge"):
                j = p["judge"]
                st.caption(f"Judge: hook {j['hook']} · cliff {j['cliffhanger']} · standalone {j['standalone']} · "
                           f"trope {j['trope']} · visual {j['visual']} — {j.get('critique', '')}")
            if p.get("flags"):
                st.caption("Flags: " + ", ".join(p["flags"]))
            st.code(clip_text(res["episodes"], p), language=None)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in out.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(out))
    d1, d2, d3 = st.columns(3)
    d1.download_button("Ranked promos (CSV)", (out / "promos_ranked.csv").read_bytes(), "promos_ranked.csv")
    d2.download_button("Edit decision list (CSV)", (out / "edit_decision_list.csv").read_bytes(), "edit_decision_list.csv")
    d3.download_button("All raw outputs (zip)", buf.getvalue(), f"promo_outputs_{time.strftime('%H%M')}.zip")
    with st.expander("Run summary"):
        st.json(summary)
