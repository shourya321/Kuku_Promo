# Promo Finder: microdrama promo clips from a screenplay

Built for Kuku's AI Generalist assignment (Problem 1, "Find the Promos").

The tool reads a show's timestamped screenplays. It proposes **ranked 20–60 s promo clips** that open on a hook in the first 3 s, end on a cliffhanger and make sense to a stranger. For each clip it gives the episode, the segment timestamps, the hook, the cliffhanger, why it works and why to post it in that position. An editor reviews the list; the tool does the first pass.

```
episodes (.txt) ─► PARSER (code) ─► MINER (cheap LLM, 1 call/episode, answers in block IDs only)
                                        │
                                        ▼
                 ASSEMBLER + RULES (code): IDs → timestamps, snap to shot boundaries, no mid-line cuts,
                 hook ≤ 3 s, 20–60 s, de-duplicate, ≤40% episode-endings in the shortlist
                   │  failed on timing? ──► REPAIR: miner re-asked ONCE with the exact reason
                   │                        ("needs +4.2 s, extend to B041"); cold-open fix only as last resort
         MONTAGE (LLM: stitches standout moments across episodes) ─┤
                                        ▼
                 JUDGE (LLM, rubric 1–5) on a shortlist
                 COLD VIEWER (LLM sees ONLY the clip: "what's happening? keep watching?")
                 CAPTIONER (LLM: ≤12-word context caption + ≤6-word ad hook text; stranger test re-run with it)
                 RANKER (LLM, 3 calls in different orders → mean position + position-bias numbers)
                 FINAL-LIST POLICY (code): top 10 has ≤3 episode-endings, ≤2 per episode, ≥4 trope families
                                        ▼
        promos_ranked.csv / .md · edit_decision_list.csv · raw model replies · run_summary.json
        → editor approves / rejects in the app (decisions.csv)
```

**See a pick play:** [docs/demo_animatic.mp4](docs/demo_animatic.mp4) is a silent 9:16 animatic of the top promo from the synthetic demo show. Every line appears at its real time inside the cut, with the hook bar for the first 3 s, the ad hook text, a CUT flash at segment joins and an end card. Make your own with `python tools/render_animatic.py outputs/<run> outputs/animatics --top 5`, or with the "Render animatic" button in the app.

## v2: what changed, measured (not claimed)

All numbers come from real runs on Kuku's 50-episode show (content stays local). Model-judged scores are **directional**: n = 10 clips per group, scored by an LLM.

| | v1 | v2 |
|---|---|---|
| valid candidates | 107 / 111 | 109 / 110 |
| rejected as too short | 3 | 0 (26 timing failures sent back to the miner: 20 fixed by it, 6 by the cold-open fallback) |
| ranked promos repeating footage (cold-open fix) | 6 / 40 | 2 / 40 |
| hard rules met by ranked promos | 40 / 40 | 40 / 40 |
| top 10 ending on an episode's final beat | 5 / 10 | 3 / 10 |
| trope families in top 10 | not measured | 5 |
| blind judge score /100, v1 vs v2 top 10 **in one pool**, Gemini judge | 68.5 | **72.8** (keyword 65.6, random 52.3) |
| same pool, **cross-family judge** (gpt-oss-120b via Groq) | 64.8 | **59.1 (worse)** (keyword 66.3, random 50.4) |
| agreement between the two judges (40 clips) | | Spearman 0.28; same order on 60% of clip pairs |
| same pool, **third rater**, blind sheet (Claude Opus 5.5: an AI rater, **not a human**) | **75.8** | 68.3 (keyword 72.5, random 44.2) |
| hook / standalone / cliffhanger (same pool) | 3.0 / 2.9 / 4.4 | 3.6 / 3.5 / **3.8 (worse)** |
| ranker agreement across prompt orders (Spearman) | 0.685 (2 orders) | 0.601 same pair; 0.48 mean over 3 orders (**worse**) |
| stranger test with vs without the context caption (same 15 clips) | | clarity 4.27 vs 4.33, keep-watching 3.93 vs 3.93, clips with a confusing point 5 vs 7 |

**Honest reading.**
* **The headline gain depends on the judge.** Gemini (the miner's own family) ranks v2 > v1 > keyword > random. A judge from a different family (gpt-oss-120b) ranks keyword ≥ v1 > v2 > random, and the two judges barely agree (ρ 0.28). The one conclusion both support is that every system beats random clips. Whether the AI beats a good keyword heuristic, and whether v2 beats v1, stays **unproven** until humans rate the clips or they run as ads. This is the self-grading risk the cross-family check was built to catch.
* **A third rater did not settle it.** Claude Opus 5.5 filled the blind rating sheet with the system labels hidden. It is a third model family, **not a human**. Its order was v1 75.8 > keyword 72.5 > v2 68.3 > random 44.2. It agrees more with Gemini (ρ 0.50) than with gpt-oss (ρ 0.32), and "would post" came out keyword 10/10, v2 9/10, v1 8/10, random 3/10. All three raters put random last. On everything else they disagree, and two of the three rank v2 below v1. Human ratings are still needed; the same sheet works for them (`tools/blind_sheet.py`). This rater also penalised clips that repeat footage (3 of v1's, 1 of v2's), which supports v2's cold-open fix.
* The repair loop works: fewer clumsy cold opens and no timing rejections.
* The diversity rules cost some cliffhanger strength, because authored episode endings are the strongest cliffhangers.
* The caption did not raise the stranger's scores. It only reduced named confusions, so it is offered as an editor aid.
* The ranker is strongly order-sensitive (position bias), so averaging 3 orders matters and its order should not be over-trusted.
* We also found that the judge's absolute scores shift about 6 points depending on which clips share a batch. Only same-pool comparisons are valid, which is why v1 and v2 were re-judged together.

**What is code and what is AI.** Parsing, every timestamp, cut-point snapping, length/hook rules, de-duplication and quotas are plain code: exact, free and testable. The models only make judgement calls (what's a hook, is it a cliffhanger, would a stranger get it), and they answer in block IDs (`B023`), never timestamps. A model therefore cannot invent a timestamp: an unknown ID is rejected and logged.

## Run it

**Windows (one click):**
```
run_windows.bat "C:\path\to\show.zip"
```

**Any OS:**
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...            # free key: https://aistudio.google.com/apikey   (Windows: set GEMINI_API_KEY=...)
python run.py --input path/to/show.zip                 # AI run (profile from models.yaml)
python run.py --input path/to/show.zip --max-eps 3     # quick smoke test
python run.py --input path/to/show.zip --mode heuristic   # no AI, keyword baseline
python run.py --input path/to/show.zip --concurrency 8    # paid key: mine episodes in parallel (rpm limits still apply)
python evaluate.py outputs/<run> --vs-baseline --human-sheet
python evaluate.py outputs/<run> --vs-baseline --judges gemini:gemini-flash-lite-latest,groq:openai/gpt-oss-120b
                                                       # several judges score the same blind clips + agreement stats
streamlit run app.py                                   # UI: run, explore, compare, review, long cuts, ad pack, export
python tools/blind_sheet.py make outputs/h2h_pool.json outputs/<run> outputs/sheet    # blind sheet for raters
python tools/blind_sheet.py score ratings.csv outputs/sheet --rater "name" --judged outputs/<run>/eval_comparison_clips.json
```
Try it without Kuku's data: `python run.py --input sample_input/demo_show` (a 3-episode synthetic show written for this repo).

**A new show in a different format.** `python -m promo_finder.validate <show>` is a free format check that also runs before every pipeline run and in the app. It reports episodes, blocks, timestamp style (`mm:ss.ff` or `hh:mm:ss.ff`), CRLF files, timestamp anomalies, missing CAMERA blocks and unparseable lines. `sample_input/revenge_show` is a second synthetic show in another genre (modern billionaire revenge, 4 episodes). It was written with quirks the parser did not originally handle: CRLF line endings, `hh:mm:ss.ff` timestamps, title-case headers, `Ep_01.txt` file names and an episode with no CAMERA blocks. After a parser fix for `hh:mm:ss`, the full AI pipeline ran on it: 4 ranked promos, all 4 passed the hook, length and clean-cut rules, and 1 timing failure was repaired by the miner.

## The app
`streamlit run app.py` (live: https://kukupromo.streamlit.app) is a dark, neon "control deck":
* **Sidebar:** engine (AI or keyword), model profile, key status (server key, your own key, or none; keys are never shown) and tuning.
* **Input and launch:** a free format check shown as chips, then an estimate of model calls before you press Find promos. **Open a saved run** re-opens a finished run from a zip of its output folder (no model calls), to share results with an editor or to show a full-show run without waiting for it.
* **During the run:** a live pipeline stepper (parse → mine + repair → rules → blind judge → stranger test → captions → rank ×3 → final list) and a log terminal.
* **Results** (headline numbers, then six tabs):
  * **Leaderboard:** promo cards with a score ring, hook / cliffhanger / caption, a timeline of where each cut sits in its episode, judge bars and the stranger's read. Search, minimum score, trope-family filter, sort, and a switch to hide flagged picks. Each card opens to the script, critique and a 9:16 animatic render.
  * **Show map:** charts of where the promos sit across episodes, the candidate funnel, a trope-family donut, a judge heatmap and rejection reasons.
  * **Compare:** two promos side by side, with a dimension-by-dimension chart.
  * **Review:** approve or reject with a reason and note, bulk-approve above a score, then download decisions.csv.
  * **Studio:** build long cuts and write an ad pack on demand.
  * **Export:** CSV, EDL, Markdown, long-cut EDL, ad pack, the zip of every output, and the run log.

`tests/test_app.py` runs the app headless in keyword mode on every push. Presentation code lives in `promo_finder/ui_theme.py`, and the pipeline is unchanged by it.

## Long cuts (90 s – 3 min) for paid UA
`python tools/long_cut.py outputs/<run>` writes `long_cuts.md`, `long_cuts.json` and `long_cuts_edl.csv`. Episodes are about 2 minutes, so a 90–180 s ad has to span episodes. Rather than asking a model for new timestamps, the tool **chains promos that already passed every rule**:
* One model call picks 2–6 approved promos that tell one arc.
* Code then rejects unknown ids, wrong story order, any repeated or rewound footage, and lengths outside 90–180 s, and re-checks every cut.
* Each long cut inherits the hook-in-3-s and clean-cut guarantees of its parts. Whether a stranger can follow the jumps is measured with the same stranger test.

On Kuku's show this took 4 calls and produced 3 long cuts (145–162 s), all of which passed the checks. Stranger test: clarity 4.0 and keep-watching 4.33, against 4.33 and 3.93 for the 15 short promos (n = 3, directional).

Honest notes:
* The first version let a "cold open" promo into a chain, which repeated 4.7 s of footage. The repeated-footage check now catches this, and cold-open promos are left out of the list the model sees.
* Two of the three cuts sell late-show reveals, so check them for spoilers before posting. Spoiler risk is not checked by code.
* The model's own stated runtime was wrong once (it said 141 s; the cut was 161 s). Code measures the real length.

## Swap the model
Edit one line in `models.yaml`, or pick another profile: `--profile gemini_groq | groq_only | local_ollama | kuku_api`. Any OpenAI-compatible endpoint works. Each role (miner, judge, cold_viewer, captioner, ranker, montage) can use a different model and can have a fallback chain. A rate-limited model (429) with a fallback behind it is abandoned after 2 attempts, so a throttled free tier does not stall the run.

## Outputs (`outputs/<run>/`)
| file | what |
|---|---|
| `promos_ranked.md` / `.csv` | ranked promos: segments, hook, cliffhanger, why, judge scores, stranger test, flags |
| `edit_decision_list.csv` | one row per segment, ready for an editor |
| `rejected_candidates.csv` | everything the rules threw out, with the reason |
| `01_mined_raw.json`, `02_all_candidates.json`, `03_promos_ranked.json` | full intermediate data |
| `../llm_cache/*.json` | every model request + raw reply, unedited |
| `run_summary.json`, `run_log.txt`, `eval_report.md` | stats, token usage, errors, evaluation |

## Confidentiality
Kuku's input pack is never committed (`.gitignore` excludes `data/`, `outputs/`, `*.zip`). The app takes the show as an upload at runtime. Note: free-tier Gemini may use prompts to improve Google's products. Production should use a paid/no-training endpoint or the `local_ollama` profile.

## Tests
`python -m pytest -q` (also runs on every push via GitHub Actions) covers:
* parser on the demo show: block counts, timestamps, speaker/delivery split, CRLF
* assembler rules: hook ≤ 3 s, 20–60 s, no mid-line cuts, unknown IDs rejected, cold-open fallback, precise repair hints
* judge ID normalisation, the final-list policy, the agreement statistics and the LLM cache
* a keyword run, plus the full AI code path against `tests/mock_server.py`, a fake API that returns broken JSON and hallucinated block IDs on purpose
* `--concurrency`: parallel mining gives the same candidates and repair counts as a serial run (against the mock API; not yet timed on a paid key)
* long-cut rules: too short, wrong order, unknown id, reused clip and repeated footage are each rejected

## Known limitations (honest)
* Every model-judged number is one LLM's opinion on n = 10 clips. Real performance is only knowable from an A/B test of the clips as ads.
* The pipeline runs on one model family (Gemini Flash-Lite, free tier). A cross-family judge (`--judges`, gpt-oss-120b) disagrees with it on which system is best (see above).
* The ranker is order-sensitive (Spearman 0.48 across 3 prompt orders), so treat its order as a suggestion for the editor.
* The context caption has not shown a measurable clarity gain yet. It sometimes breaks its 12-word limit (flagged by code) and can invent a relationship the clip doesn't show, so an editor must check it.
* Text only: no video, so visual quality (acting, framing) is judged from the script's descriptions.
* `--concurrency` is only tested against the mock API. On the free Gemini tier it gives no speed-up, because the rpm pacing in `models.yaml` still serialises calls.
