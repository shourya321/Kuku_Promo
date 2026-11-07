@echo off
REM Re-run after a network drop: reuses cached model replies, so only missing calls are made.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set VPY=.venv\Scripts\python.exe
if "%GEMINI_API_KEY%"=="" if exist .gemini_key set /p GEMINI_API_KEY=<.gemini_key
echo === 1/3 AI run (cached episodes reused) ===
%VPY% run.py --input data\show.zip --out outputs\final
echo === 2/3 Keyword baseline ===
%VPY% run.py --input data\show.zip --mode heuristic --out outputs\keyword_baseline
echo === 3/3 Evaluation ===
%VPY% evaluate.py outputs\final --vs-baseline --human-sheet
echo DONE. Tell Claude.
pause
