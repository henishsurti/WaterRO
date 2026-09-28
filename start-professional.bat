@echo off
cd /d "%~dp0"
if not exist backend\.venv python -m venv backend\.venv
call backend\.venv\Scripts\activate.bat
python -m pip install -r backend\requirements.txt
cd backend
python run.py
pause
