"""Unit tests for the deterministic parts (parser, assembler, id handling, cache).

Run:  python -m pytest -q
No network, no API keys: the LLM test patches the network call.
"""
from pathlib import Path

import pytest

from promo_finder.assemble import assemble
from promo_finder.parser import is_clean_cut, load_show, parse_episode
from promo_finder.pipeline import norm_clip_id

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "sample_input" / "demo_show"


def _ts(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def make_episode(n_lines=30, line_len=3.0, number=5):
    """Synthetic episode: a CAMERA shot then a dialogue line, alternating, back to back.
    90+ seconds long, so there is room to build 20-60 s promos anywhere in it."""
    parts = [f"EPISODE NUMBER: Episode {number}", "EPISODE LOGLINE: test", "", "SCENE 01"]
    t = 0.0
    for i in range(n_lines):
        parts += ["**CAMERA:**", f"Start: ({_ts(t)}) | End: ({_ts(t + 1)})", f"Shot {i}.", ""]
        t += 1
        parts += [f"**ANNA (Angry):**", f"Start: ({_ts(t)}) | End: ({_ts(t + line_len)})", f'"Line {i}!"', ""]
        t += line_len
    return parse_episode("\n".join(parts))


# ---------------------------------------------------------------- parser
def test_demo_show_parses():
    show, eps = load_show(DEMO)
    assert [e.number for e in eps] == [1, 2, 3]
    assert [len(e.blocks) for e in eps] == [21, 18, 16]
    assert all(e.blocks == sorted(e.blocks, key=lambda b: b.start) for e in eps)
    assert not any(e.warnings for e in eps)


def test_timestamps_and_speaker_delivery_split():
    _, eps = load_show(DEMO)
    ep3 = eps[2]
    ryan = ep3.block("E03-B002")
    assert (ryan.kind, ryan.speaker, ryan.delivery) == ("DIALOGUE", "RYAN", "Ashamed")
    assert (ryan.start, ryan.end) == (2.0, 5.0)
    sloane = next(b for b in ep3.blocks if b.delivery == "Shocked, Whispering")
    assert sloane.speaker == "SLOANE" and sloane.start == 31.8
    assert ep3.block("E03-B005").kind == "SFX"          # "SOUND FX" header -> SFX
    assert ep3.duration == pytest.approx(36.8)


def test_crlf_input_parses_the_same():
    txt = (DEMO / "episode-003-Demo.txt").read_text(encoding="utf-8")
    a, b = parse_episode(txt), parse_episode(txt.replace("\n", "\r\n"))
    assert [(x.id, x.start, x.end, x.text) for x in a.blocks] == [(x.id, x.start, x.end, x.text) for x in b.blocks]


def test_second_show_with_format_quirks():
    """CRLF, hh:mm:ss.ff timestamps, title-case headers, Ep_01.txt names, an episode without CAMERA blocks."""
    from promo_finder.validate import validate
    r = validate(ROOT / "sample_input" / "revenge_show")
    assert r["ok"] and r["episodes_found"] == 4 and r["blocks_total"] == 61
    assert r["crlf_files"] == 4 and r["timestamp_styles"] == {"hh:mm:ss": 61}
    assert any("E1: no CAMERA" in p for p in r["problems"])
    _, eps = load_show(ROOT / "sample_input" / "revenge_show")
    assert eps[0].block("E01-B011").speaker == "ELIAS" and eps[0].block("E01-B011").delivery == "Calm, Dangerous"


# ---------------------------------------------------------------- assembler
def _cand(ep, start_b, end_b, hook_b=None, cliff_b=None):
    return {"title": "t", "segments": [{"start_block": start_b, "end_block": end_b}],
            "hook_block": hook_b or start_b, "hook": "h", "cliffhanger_block": cliff_b or end_b,
            "cliffhanger": "c", "why": "w", "strength": 5}


def test_valid_clip_obeys_hard_rules():
    ep = make_episode()
    # B012 = dialogue at 22-25 s, B030 = dialogue at 58-61 s -> ~39 s clip
    p = assemble(ep, _cand(ep, "B011", "B030", hook_b="B012"))
    assert p["status"] == "ok", p["reject_reasons"]
    assert 0 <= p["hook_offset"] <= 3.0
    assert 20 <= p["duration"] <= 60
    assert all(is_clean_cut(ep, t) for s in p["segments"] for t in (s["start"], s["end"]))


def test_unknown_block_id_is_rejected():
    ep = make_episode()
    p = assemble(ep, _cand(ep, "B999", "B1000"))
    assert p["status"] == "rejected"
    assert any("unknown" in r for r in p["reject_reasons"])


def test_short_clip_gets_flash_forward_cold_open():
    ep = make_episode()
    # B040-B044 is only ~10 s, with plenty of earlier footage to borrow from
    p = assemble(ep, _cand(ep, "B040", "B044"))
    assert "flash-forward cold open" in p["flags"]
    assert p["duration"] >= 20


def test_no_cut_lands_mid_line():
    ep = make_episode(line_len=6.0)   # long lines make mid-line cuts likely if snapping were broken
    for a, b in [("B004", "B020"), ("B010", "B024"), ("B020", "B032")]:
        p = assemble(ep, _cand(ep, a, b))
        if p["status"] == "ok":
            assert all(is_clean_cut(ep, t) for s in p["segments"] for t in (s["start"], s["end"]))


# ---------------------------------------------------------------- judge id normalisation
@pytest.mark.parametrize("raw", ["CLIP E09-P1", "clip e09-p1", "id: E09-P1", "  E09-P1 ", "Clip #E09-P1"])
def test_judge_id_normalisation(raw):
    assert norm_clip_id(raw) == "E09-P1"


# ---------------------------------------------------------------- final-list policy + stats
def test_diversify_limits_episode_endings_and_repeats():
    from promo_finder.policy import diversify
    tropes = ["secret duke", "sister betrayal", "cruel family", "revenge", "wedding"]
    ranked = [{"id": f"P{i}", "segments": [{"episode": i % 8}], "episode": i % 8,
               "ends_on_episode_end": i < 8, "trope": tropes[0] if i < 10 else tropes[i % 5]} for i in range(30)]
    top = diversify(ranked)[:10]
    assert sum(p["ends_on_episode_end"] for p in top) <= 3
    assert max(sum(q["episode"] == p["episode"] for q in top) for p in top) <= 2
    assert len({p["trope_family"] for p in top}) >= 4


def test_repair_hint_is_precise():
    from promo_finder.assemble import repair_hint
    ep = make_episode()
    p = assemble(ep, _cand(ep, "B040", "B044"), allow_flash=False)
    assert p["status"] == "rejected"
    hint = repair_hint(ep, p)
    assert hint.startswith("too short") and "needs +" in hint and "B0" in hint
    assert repair_hint(ep, assemble(ep, _cand(ep, "B999", "B1000"))) is None   # bad ids are not "fixable"


def test_stats():
    from promo_finder.stats import kendall_tau, pair_agreement, spearman
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert kendall_tau(list("abcd"), list("dcba")) == -1.0
    assert pair_agreement([1, 2, 3], [1, 3, 2])["agree_pct"] == pytest.approx(66.7)


# ---------------------------------------------------------------- llm cache
def test_llm_cache_hit(tmp_path, monkeypatch):
    from promo_finder.llm import LLM
    from promo_finder.prompts import ColdOut
    cfg = tmp_path / "m.yaml"
    cfg.write_text("default_profile: p\nproviders:\n  x: {base_url: 'http://127.0.0.1:9/v1', requires_key: false}\n"
                   "profiles:\n  p:\n    default: {provider: x, model: m}\n", encoding="utf-8")
    llm = LLM(cfg, cache_dir=tmp_path / "cache", log=lambda *a: None)
    calls = []

    def fake(provider, mcfg, msgs, temperature, has_fallback=False):
        calls.append(1)
        return '{"what_is_happening": "x", "clarity": 4, "keep_watching": 5}', {"prompt_tokens": 1, "completion_tokens": 1}
    monkeypatch.setattr(llm, "_raw_call", fake)
    a, m1 = llm.json("cold_viewer", "sys", "user", ColdOut, tag="t")
    b, m2 = llm.json("cold_viewer", "sys", "user", ColdOut, tag="t")
    assert len(calls) == 1 and not m1["cached"] and m2["cached"]
    assert a == b and llm.stats["cache_hits"] == 1
