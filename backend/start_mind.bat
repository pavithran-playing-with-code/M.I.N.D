@echo off
rem Double-click this file to start M.I.N.D (no need to type any commands)
cd /d "%~dp0"
venv\Scripts\python.exe main.py
rem Keep the window open only if something went wrong, so you can read the error
if errorlevel 1 pause
