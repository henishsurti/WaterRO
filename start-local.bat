@echo off
setlocal
cd /d "%~dp0"
set PORT=8799
where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher ^(py^) was not found.
  echo You can still open index.html directly in your browser.
  pause
  exit /b 1
)
start "AquaFlow Browser" cmd /c "timeout /t 1 /nobreak >nul & start http://127.0.0.1:%PORT%/"
echo AquaFlow is running at http://127.0.0.1:%PORT%/
echo Close this window to stop the local server.
py -m http.server %PORT%
endlocal
