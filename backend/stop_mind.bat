@echo off
rem Double-click this file to stop M.I.N.D
cd /d "%~dp0"
if exist mind.pid (for /f %%p in (mind.pid) do taskkill /PID %%p /T /F >nul 2>&1) & del mind.pid >nul 2>&1
venv\Scripts\python.exe taskbar.py off
echo M.I.N.D is off. See you!
timeout /t 2 >nul
