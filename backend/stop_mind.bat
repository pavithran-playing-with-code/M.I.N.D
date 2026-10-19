@echo off
rem Double-click this file to stop M.I.N.D (it says "Mind off" and closes itself)
cd /d "%~dp0"
if not exist mind.pid goto done
for /f %%p in (mind.pid) do set MINDPID=%%p
curl -s -m 2 -X POST http://127.0.0.1:8000/api/power_off >nul 2>&1
powershell -NoProfile -Command "Wait-Process -Id %MINDPID% -Timeout 6 -ErrorAction SilentlyContinue; if (Get-Process -Id %MINDPID% -ErrorAction SilentlyContinue) { exit 1 }; exit 0"
if errorlevel 1 (
    taskkill /PID %MINDPID% /T /F >nul 2>&1
    del mind.pid >nul 2>&1
    venv\Scripts\python.exe taskbar.py off
)
:done
echo M.I.N.D is off. See you!
timeout /t 2 >nul
