@echo off
REM Full run on Windows. Usage: run_windows.bat   (uses data\show.zip)   or   run_windows.bat "C:\path\to\show.zip"
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set INPUT=%~1
if "%INPUT%"=="" set INPUT=data\show.zip
set PYEXE=
set PYARGS=
where py >nul 2>nul && set "PYEXE=py"
if defined PYEXE set "PYARGS=-3"
if not defined PYEXE ( where python >nul 2>nul && python --version >nul 2>nul && set "PYEXE=python" )
for %%P in ("%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" "%LOCALAPPDATA%\Python\pythoncore-3.13-64\python.exe" "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "C:\Program Files\Python314\python.exe" "C:\Program Files\Python313\python.exe" "C:\Program Files\Python312\python.exe") do if exist "%%~P" if not defined PYEXE set "PYEXE=%%~P"
for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-*") do if exist "%%~D\python.exe" if not defined PYEXE set "PYEXE=%%~D\python.exe"
if not defined PYEXE ( echo Python not found. Run the python-3.13 installer, tick Add python.exe to PATH, click Install Now, then run this again. & pause & exit /b 1 )
echo Using Python: %PYEXE% %PYARGS%
"%PYEXE%" %PYARGS% --version
if not exist .venv\Scripts\python.exe ( "%PYEXE%" %PYARGS% -m venv .venv )
set VPY=.venv\Scripts\python.exe
echo Installing packages (1-2 min the first time)...
%VPY% -m pip install -q --upgrade pip
%VPY% -m pip install -q -r requirements.txt
if errorlevel 1 ( echo Package install failed - send Claude a screenshot. & pause & exit /b 1 )
if "%GEMINI_API_KEY%"=="" if exist .gemini_key set /p GEMINI_API_KEY=<.gemini_key
if "%GEMINI_API_KEY%"=="" set /p GEMINI_API_KEY=Paste your Gemini API key (right-click to paste) and press Enter: 
echo.
echo === 1/4 Smoke test on 2 episodes ===
%VPY% run.py --input "%INPUT%" --max-eps 2 --no-montage --rank-top 0 --cold-top 2 --out outputs\smoke_test
if errorlevel 1 ( echo Smoke test failed - send Claude a screenshot of the error above. & pause & exit /b 1 )
echo === 2/4 Full AI run on all episodes (about 10-15 min on free tier) ===
%VPY% run.py --input "%INPUT%" --out outputs\final_run
echo === 3/4 Keyword baseline (no AI) ===
%VPY% run.py --input "%INPUT%" --mode heuristic --out outputs\keyword_baseline
echo === 4/4 Evaluation: AI vs keyword vs random, same blind judge ===
%VPY% evaluate.py outputs\final_run --vs-baseline --human-sheet
echo.
echo DONE. Open outputs\final_run\promos_ranked.md and tell Claude.
pause
