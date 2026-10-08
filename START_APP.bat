@echo off
REM OpsPulse AI - start on Windows (double-click)
cd /d "%~dp0"
if not exist .venv (
  echo First run: creating Python environment...
  py -3.12 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\streamlit run app.py
pause
