"""Build ONE blind pool with v1's top 10, v2's top 10 and the same keyword/random clips.

Why: the judge scores clips in batches, and the same clip scores differently next to different
neighbours (we measured ~6 points of drift on identical keyword/random clips). Comparing v1 and v2
fairly therefore needs both in the same pool, judged in the same calls.

  python tools/make_h2h_pool.py <v1 eval_comparison_clips.json> <v2 eval_comparison_clips.json> <out.json>
then
  python evaluate.py <run> --vs-baseline --reuse-pool <out.json>
"""
import json
import random
import sys

v1 = json.load(open(sys.argv[1], encoding="utf-8"))
v2 = json.load(open(sys.argv[2], encoding="utf-8"))
pool = [dict(p, id=p["id"].replace("AI-", "V1-")) for p in v1 if p["id"].startswith("AI-")]
pool += [dict(p, id=p["id"].replace("AI-", "V2-")) for p in v2 if p["id"].startswith("AI-")]
pool += [p for p in v2 if not p["id"].startswith("AI-")]          # identical KW/RND clips in v1 and v2
for p in pool:
    p.pop("judge", None); p.pop("judges", None)
random.Random(5).shuffle(pool)   # blind: ids carry no order
json.dump(pool, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(pool)} clips -> {sys.argv[3]}")
