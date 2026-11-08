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


def test_card_html_has_no_newlines_or_indentation():
    # Streamlit's markdown would turn indented lines into code blocks, so cards must be one line
    p = {"id": "E01-P1", "rank": 1, "title": "t <b>", "score": 72.5, "duration": 30, "hook_offset": 1.0,
         "hook": "h", "cliffhanger": "c", "flags": ["flash-forward cold open"], "trope_family": "betrayal",
         "segments": [{"episode": 1, "start": 0.0, "end": 30.0, "start_tc": "00:00.00", "end_tc": "00:30.00"}],
         "judge": {"hook": 4, "cliffhanger": 3, "standalone": 3, "trope": 4, "visual": 2}}
    html = T.card(p, {})
    assert "\n" not in html and "&lt;b&gt;" in html and "repeats footage" in html
    assert "\n" not in T.stepper(2, ai=False) and "skip" in T.stepper(2, ai=False)
