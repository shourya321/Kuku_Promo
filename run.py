"""Command line entry point.

  python run.py --input path/to/show.zip                      # AI run, default profile (Gemini)
  python run.py --input show_folder --profile gemini_groq     # different models
  python run.py --input show.zip --mode heuristic             # no AI: keyword baseline
  python run.py --input show.zip --max-eps 3                  # quick smoke test
"""
import argparse
import json
import sys
import time
from pathlib import Path

from promo_finder.pipeline import Run


def main():
    ap = argparse.ArgumentParser(description="Find promo clips in a microdrama screenplay")
    ap.add_argument("--input", required=True, help="folder of episode .txt files or a .zip")
    ap.add_argument("--out", default=None, help="output folder (default outputs/<mode>_<time>)")
    ap.add_argument("--mode", choices=["llm", "heuristic"], default="llm")
    ap.add_argument("--profile", default=None, help="profile in models.yaml")
    ap.add_argument("--config", default="models.yaml")
    ap.add_argument("--no-cache", action="store_true", help="ignore cached model replies")
    ap.add_argument("--max-eps", type=int, default=None)
    ap.add_argument("--judge-top", type=int, default=40)
    ap.add_argument("--cold-top", type=int, default=15)
    ap.add_argument("--rank-top", type=int, default=12)
    ap.add_argument("--no-montage", action="store_true")
    a = ap.parse_args()

    out = a.out or f"outputs/{a.mode}_{time.strftime('%Y%m%d_%H%M%S')}"
    llm = None
    if a.mode == "llm":
        from promo_finder.llm import LLM
        llm = LLM(a.config, a.profile, cache_dir=Path(out).parent / "llm_cache", use_cache=not a.no_cache)
    run = Run(a.input, out, llm=llm, mode=a.mode, judge_top=a.judge_top, cold_top=a.cold_top,
              rank_top=a.rank_top, max_eps=a.max_eps, montage=not a.no_montage)
    s = run.run()
    print(json.dumps({k: s[k] for k in ("candidates_total", "candidates_valid", "ranked", "rejected_by_reason",
                                        "ranker_order_consistency_spearman", "runtime_s")}, indent=2))
    if llm:
        print("LLM usage:", json.dumps(llm.stats["by_model"], indent=2))
    print(f"\nOpen {out}/promos_ranked.md (readable) or promos_ranked.csv (spreadsheet).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
