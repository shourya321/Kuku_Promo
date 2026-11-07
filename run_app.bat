@echo off
REM Opens the Promo Finder app in your browser (http://localhost:8501)
cd /d "%~dp0"
set PYTHONUTF8=1
if exist .gemini_key set /p GEMINI_API_KEY=<.gemini_key
.venv\Scripts\python.exe -m streamlit run app.py --server.headless false
pause
