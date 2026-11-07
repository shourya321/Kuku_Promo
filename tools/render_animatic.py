"""CLI wrapper: python tools/render_animatic.py <run_dir> <out_dir> [--top 5]. Code lives in promo_finder/animatic.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from promo_finder.animatic import main

if __name__ == "__main__":
    main()
