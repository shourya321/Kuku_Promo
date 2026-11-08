"""The Streamlit app runs end to end in keyword mode (no network): input -> run -> every results tab."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from promo_finder import ui_theme as T

ROOT = Path(__file__).resolve().parents[1]


def test_app_keyword_run_renders_all_tabs():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    assert not at.exception
    at.sidebar.radio[0].set_value("Keyword baseline (no AI)")
    at.radio[0].set_value("🧪 Demo show (synthetic, 3 episodes)")
    at.run()
    at.button[0].click()          # Find promos
    at.run()
    assert not at.exception, at.exception
    assert len(at.tabs) == 6
    assert any("Bulk approve" in b.label for b in at.button)


def test_server_key_found_under_alias_in_a_section(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.secrets["api"] = {"gemini_key": "test-not-a-real-key"}      # lowercase alias inside a [section]
    at.run()
    assert not at.exception
    chips = " ".join(m.value for m in at.sidebar.markdown)
    assert "Gemini ● server" in chips and "Groq ○ none" in chips
    assert "test-not-a-real-key" not in chips                       # values are never rendered
    import os
    os.environ.pop("GEMINI_API_KEY", None)                          # the app set the server key; don't leak it to other tests


def test_typed_key_stays_in_its_session(monkeypatch):
    import os
    from promo_finder.llm import LLM
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    llm = LLM(ROOT / "models.yaml", "groq_only", cache_dir=ROOT / ".pytest_cache" / "llm", keys={"GROQ_API_KEY": "sess-key"})
    assert llm._has_key("groq") and llm._key("groq") == "sess-key"
    assert "GROQ_API_KEY" not in os.environ                         # never leaks to other sessions
    assert not LLM(ROOT / "models.yaml", "groq_only", cache_dir=ROOT / ".pytest_cache" / "llm")._has_key("groq")


def test_card_html_has_no_newlines_or_indentation():
    # Streamlit's markdown would turn indented lines into code blocks, so cards must be one line
    p = {"id": "E01-P1", "rank": 1, "title": "t <b>", "score": 72.5, "duration": 30, "hook_offset": 1.0,
         "hook": "h", "cliffhanger": "c", "flags": ["flash-forward cold open"], "trope_family": "betrayal",
         "segments": [{"episode": 1, "start": 0.0, "end": 30.0, "start_tc": "00:00.00", "end_tc": "00:30.00"}],
         "judge": {"hook": 4, "cliffhanger": 3, "standalone": 3, "trope": 4, "visual": 2}}
    html = T.card(p, {})
    assert "\n" not in html and "&lt;b&gt;" in html and "repeats footage" in html
    assert "\n" not in T.stepper(2, ai=False) and "skip" in T.stepper(2, ai=False)
