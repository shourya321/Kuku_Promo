"""End-to-end runs on the synthetic demo show.

1. keyword mode (no AI at all)
2. the full AI code path against tests/mock_server.py, a fake OpenAI-compatible API that
   also returns one broken JSON reply and hallucinated block ids on purpose.
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

from promo_finder.pipeline import Run

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "sample_input" / "demo_show"


def _check_outputs(out: Path, summary: dict):
    assert summary["candidates_valid"] > 0
    for f in ("promos_ranked.csv", "promos_ranked.md", "edit_decision_list.csv", "run_summary.json", "run_log.txt"):
        assert (out / f).exists(), f


def test_heuristic_run(tmp_path):
    s = Run(DEMO, tmp_path, mode="heuristic", log=lambda *a: None).run()
    _check_outputs(tmp_path, s)
    # run_log.txt starts fresh per run (it used to append)
    Run(DEMO, tmp_path, mode="heuristic", log=lambda *a: None).run()
    assert (tmp_path / "run_log.txt").read_text(encoding="utf-8").count("Show:") == 1


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_mock_llm_run(tmp_path):
    from promo_finder.llm import LLM
    port = _free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_server.py"), str(port)])
    try:
        for _ in range(50):  # wait until the fake API accepts connections
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); break
            except OSError:
                time.sleep(0.1)
        cfg = tmp_path / "mock.yaml"
        cfg.write_text((ROOT / "tests" / "models_mock.yaml").read_text().replace("8765", str(port)))
        llm = LLM(cfg, cache_dir=tmp_path / "cache", log=lambda *a: None)
        out = tmp_path / "run"
        s = Run(DEMO, out, llm=llm, mode="llm", log=lambda *a: None).run()
        _check_outputs(out, s)
        # the mock's hallucinated "B999" candidate must be rejected, never shipped
        assert s["rejected_by_reason"].get("unknown block id", 0) >= 1 or any(
            "unknown" in k for k in s["rejected_by_reason"])
    finally:
        srv.kill()


def test_parallel_mining_matches_serial(tmp_path):
    """--concurrency mines episodes in threads; merged in episode order, the result equals a serial run
    (the second run reads the first run's cached replies, so both see identical model output)."""
    import json
    from promo_finder.llm import LLM
    port = _free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_server.py"), str(port)])
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); break
            except OSError:
                time.sleep(0.1)
        cfg = tmp_path / "mock.yaml"
        cfg.write_text((ROOT / "tests" / "models_mock.yaml").read_text().replace("8765", str(port)))
        outs = {}
        for n in (3, 1):
            llm = LLM(cfg, cache_dir=tmp_path / "cache", log=lambda *a: None)
            out = tmp_path / f"run{n}"
            s = Run(DEMO, out, llm=llm, mode="llm", log=lambda *a: None, concurrency=n, montage=False).run()
            outs[n] = (json.loads((out / "02_all_candidates.json").read_text(encoding="utf-8")), s["repair_loop"])
        assert [c["id"] for c in outs[3][0]] == [c["id"] for c in outs[1][0]]
        assert [c["segments"] for c in outs[3][0]] == [c["segments"] for c in outs[1][0]]
        assert outs[3][1] == outs[1][1]
    finally:
        srv.kill()
