# Promo Finder: microdrama promo clips from a screenplay

Built for Kuku's AI Generalist assignment (Problem 1, "Find the Promos").

The tool reads a show's timestamped screenplays. It proposes **ranked 20–60 s promo clips** that open on a hook in the first 3 s, end on a cliffhanger and make sense to a stranger. For each clip it gives the episode, the segment timestamps, the hook, the cliffhanger, why it works and why to post it in that position. An editor reviews the list; the tool does the first pass.

```
episodes (.txt) ─► PARSER (code) ─► MINER (cheap LLM, 1 call/episode, answers in block IDs only)
                                        │
                                        ▼
                 ASSEMBLER + RULES (code): IDs → timestamps, snap to shot boundaries, no mid-line cuts,
                 hook ≤ 3 s, 20–60 s (auto cold-open / jump-cut fixes), de-duplicate, ≤40% episode-endings
                                        │
         MONTAGE (LLM: stitches standout moments across episodes) ─┤
                                        ▼
                 JUDGE (stronger/different LLM, rubric 1–5) on a shortlist
                 COLD VIEWER (LLM sees ONLY the clip: "what's happening? keep watching?")
                 RANKER (LLM, run twice in opposite orders → position-bias check)
                                        ▼
        promos_ranked.csv / .md · edit_decision_list.csv · raw model replies · run_summary.json
```

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
streamlit run app.py                                   # UI
```
Try it without Kuku's data: `python run.py --input sample_input/demo_show` (a 3-episode synthetic show written for this repo).

## Swap the model
Edit one line in `models.yaml`, or pick another profile: `--profile gemini_groq | groq_only | local_ollama | kuku_api`. Any OpenAI-compatible endpoint works. Each role (miner, judge, cold_viewer, ranker, montage) can use a different model and can have a fallback chain.

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
`python tests/mock_server.py &` then `python run.py --input sample_input/demo_show --config tests/models_mock.yaml` runs the full AI code path against a fake API. It covers invalid JSON repair, hallucinated block IDs and fallbacks, all without network access.
