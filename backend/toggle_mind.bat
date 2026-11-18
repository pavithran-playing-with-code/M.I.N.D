@echo off
rem One button for M.I.N.D: starts it if it's off, stops it if it's on
cd /d "%~dp0"
rem Is it running? (mind.pid holds its process number)
if exist mind.pid (
    for /f %%p in (mind.pid) do tasklist /FI "PID eq %%p" /FI "IMAGENAME eq pythonw.exe" /NH | find "%%p" >nul && goto turn_off
)
rem It's off: start it
start "" venv\Scripts\pythonw.exe main.py
goto :eof

:turn_off
rem It says "Mind off" and closes itself (HUD, floating reactor, taskbar icon, phone message).
rem If it doesn't answer, it's still starting up (a double-click on the button): ignore this click.
curl -s -m 2 -X POST http://127.0.0.1:8000/api/power_off >nul 2>&1
