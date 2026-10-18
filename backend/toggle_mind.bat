@echo off
rem One button for M.I.N.D: starts it if it's off, stops it if it's on
cd /d "%~dp0"
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 goto turn_off

rem It's off: start it
venv\Scripts\python.exe main.py
if errorlevel 1 pause
goto :eof

:turn_off
rem It's on: stop it, and say so
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if ($c) { Stop-Process -Id $c[0].OwningProcess -Force }; (New-Object -ComObject SAPI.SpVoice).Speak('Mind is off') | Out-Null"
venv\Scripts\python.exe taskbar.py off
