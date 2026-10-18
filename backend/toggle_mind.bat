@echo off
rem One button for M.I.N.D: starts it if it's off, stops it if it's on
cd /d "%~dp0"
rem 0 = off, 1 = on, 2 = started less than 15 seconds ago (a double-click: ignore the second click)
powershell -NoProfile -Command "$f = 'mind.pid'; if (-not (Test-Path $f)) { exit 0 }; $p = Get-Process -Id (Get-Content $f) -ErrorAction SilentlyContinue; if (-not $p) { exit 0 }; if (((Get-Date) - (Get-Item $f).LastWriteTime).TotalSeconds -lt 15) { exit 2 }; exit 1"
if errorlevel 2 goto :eof
if errorlevel 1 goto turn_off

rem It's off: start it
start "" venv\Scripts\pythonw.exe main.py
goto :eof

:turn_off
rem It's on: stop it (and its helper process), and say so
for /f %%p in (mind.pid) do taskkill /PID %%p /T /F >nul 2>&1
del mind.pid >nul 2>&1
venv\Scripts\python.exe taskbar.py off
powershell -NoProfile -Command "(New-Object -ComObject SAPI.SpVoice).Speak('Mind is off') | Out-Null"
