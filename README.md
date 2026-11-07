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
| blind judge score /100, v1 vs v2 top 10 **in one pool** | 68.5 | **72.8** (keyword 65.6, random 52.3) |
| hook / standalone / cliffhanger (same pool) | 3.0 / 2.9 / 4.4 | 3.6 / 3.5 / **3.8 (worse)** |
| ranker agreement across prompt orders (Spearman) | 0.685 (2 orders) | 0.601 same pair; 0.48 mean over 3 orders (**worse**) |
| stranger test with vs without the context caption (same 15 clips) | | clarity 4.27 vs 4.33, keep-watching 3.93 vs 3.93, clips with a confusing point 5 vs 7 |

**Honest reading.**
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
python evaluate.py outputs/<run> --vs-baseline --human-sheet
python evaluate.py outputs/<run> --vs-baseline --judges gemini:gemini-flash-lite-latest,groq:llama-3.3-70b-versatile
                                                       # several judges score the same blind clips + agreement stats
streamlit run app.py                                   # UI: run, review, approve/reject, download decisions.csv
```
Try it without Kuku's data: `python run.py --input sample_input/demo_show` (a 3-episode synthetic show written for this repo).

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

## Known limitations (honest)
* Every model-judged number is one LLM's opinion on n = 10 clips. Real performance is only knowable from an A/B test of the clips as ads.
* All roles ran on one model family (Gemini Flash-Lite, free tier). A cross-family judge is supported (`--judges`) but needs a Groq key.
* The ranker is order-sensitive (Spearman 0.48 across 3 prompt orders), so treat its order as a suggestion for the editor.
* The context caption has not shown a measurable clarity gain yet.
* Text only: no video, so visual quality (acting, framing) is judged from the script's descriptions.
