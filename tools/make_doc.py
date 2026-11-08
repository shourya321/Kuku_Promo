"""Builds the 2-page solution PDF from a finished run's real output files.

  python tools/make_doc.py outputs/final outputs/keyword_baseline solution.pdf
"""
import html
import json
import sys
from pathlib import Path

run, base, out_pdf = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
ranked = json.loads((run / "03_promos_ranked.json").read_text(encoding="utf-8"))
summ = json.loads((run / "run_summary.json").read_text(encoding="utf-8"))
ev = json.loads((run / "eval_metrics.json").read_text(encoding="utf-8")) if (run / "eval_metrics.json").exists() else {}
NOTES = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")) if len(sys.argv) > 4 else {}

e = html.escape


def cut(t, n):
    t = str(t or "")
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def segs(p):
    return " + ".join(f"E{s['episode']} {s['start_tc'][:-3]}–{s['end_tc'][:-3]}" for s in p["segments"])


rows = ""
for p in ranked[:6]:
    rows += (f"<tr><td class=n>{p['rank']}</td><td><b>{e(p.get('title', ''))}</b><br><span class=mut>{segs(p)} · {p['duration']:.0f}s</span></td>"
             f"<td>{e(cut(p.get('hook', ''), 110))}</td><td>{e(cut(p.get('cliffhanger', ''), 110))}</td>"
             f"<td>{e(cut(p.get('rank_reason') or p.get('why', ''), 150))}</td></tr>")

stats = summ.get("llm_stats", {})
tok_in, tok_out, calls = stats.get("prompt_tokens", 0), stats.get("completion_tokens", 0), stats.get("calls", 0)
comp = ev.get("blind_comparison_same_judge", {})
comp_rows = ""
groups = {k: v for k, v in comp.items() if not k.startswith("_")}   # skip "_ordering..." flags
for name, v in sorted(groups.items(), key=lambda kv: -(kv[1].get("overall_score_0_100") or 0)):
    comp_rows += (f"<tr><td>{e(name)}</td><td>{v.get('hook')}</td><td>{v.get('cliffhanger')}</td><td>{v.get('standalone')}</td>"
                  f"<td>{v.get('stranger_clarity')}</td><td>{v.get('stranger_keep_watching')}</td><td><b>{v.get('overall_score_0_100')}</b></td></tr>")

N = NOTES
doc = f"""<!doctype html><html><head><meta charset=utf-8><style>
@page {{ size: A4; margin: 11mm 12mm; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 8.6pt; line-height: 1.34; color: #1a1a1a; margin: 0; }}
h1 {{ font-size: 15pt; margin: 0 0 1px; }} h2 {{ font-size: 10pt; margin: 7px 0 3px; color: #8a1c1c; border-bottom: 1px solid #e5d5d5; padding-bottom: 1px; }}
p {{ margin: 2px 0 4px; }} ul {{ margin: 2px 0 4px; padding-left: 15px; }} li {{ margin: 1px 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 3px 0 4px; }} td, th {{ border: 1px solid #ddd; padding: 2.5px 4px; vertical-align: top; text-align: left; }}
th {{ background: #f6eeee; font-weight: 600; }} .n {{ text-align: center; font-weight: 700; }} .mut {{ color: #666; font-size: 7.6pt; }}
.sub {{ color: #555; margin-bottom: 5px; }} .flow {{ font-family: Consolas, monospace; font-size: 7.6pt; background: #faf7f7; border: 1px solid #eee; padding: 4px 6px; white-space: pre; line-height: 1.3; }}
.two {{ display: flex; gap: 10px; }} .two > div {{ flex: 1; }} .pb {{ page-break-before: always; }} b.k {{ color: #8a1c1c; }}
</style></head><body>
<h1>Promo Finder: an AI first pass for microdrama promos</h1>
<div class=sub>Kuku AI Generalist · Problem 1 · {e(N.get('author', ''))} · Prototype: {e(N.get('link', ''))}{' · Code: ' + e(N['repo']) if N.get('repo') else ''}</div>

<h2>1. The problem and why it matters</h2>
{N.get('problem', '')}

<h2>2. Approach: code does the exact work, AI does the judgement</h2>
<div class=flow>{e(N.get('flow', ''))}</div>
{N.get('approach', '')}

<h2>3. Results on "{e(summ['show'])}" ({summ['episodes']} episodes, real run)</h2>
<p>{N.get('results_intro', '')}</p>
<table><tr><th>#</th><th>Promo (segments, length)</th><th>Hook (first 3 s)</th><th>Cliffhanger (cut point)</th><th>Why post it here</th></tr>{rows}</table>
<p class=mut>Full list ({len(ranked)} ranked promos with scores, stranger-test answers and flags), the edit decision list and every raw model reply are in the outputs folder.</p>

<div class=pb></div>
<h2>4. Quality check: does it actually pick well?</h2>
{N.get('quality_intro', '')}
<table><tr><th>Blind, same judge (1–5)</th><th>Hook</th><th>Cliffhanger</th><th>Standalone</th><th>Stranger clarity</th><th>Stranger keep-watching</th><th>Score /100</th></tr>{comp_rows}</table>
{N.get('quality', '')}
<h2>5. Where it picks badly (honest failures)</h2>
{N.get('failures', '')}

<h2>6. Scale, cost and the human in the loop</h2>
{N.get('scale', '')}
<p class=mut>{N.get('run_line') or f"This run: {calls} model calls, {tok_in:,} input + {tok_out:,} output tokens."}</p>
<h2>7. What I would do next / with paid APIs</h2>
{N.get('next', '')}
</body></html>"""

html_path = out_pdf.with_suffix(".html")
html_path.write_text(doc, encoding="utf-8")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page()
        pg.goto(html_path.resolve().as_uri()); pg.pdf(path=str(out_pdf), format="A4", print_background=True)
        b.close()
except ImportError:   # no playwright: print with Microsoft Edge (preinstalled on Windows 10/11)
    import subprocess
    edge = next(p for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"] if Path(p).exists())
    subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out_pdf.resolve()}", html_path.resolve().as_uri()], check=True, timeout=120)
print("wrote", out_pdf)
