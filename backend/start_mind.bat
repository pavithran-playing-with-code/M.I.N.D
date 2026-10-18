@echo off
rem Double-click this file to start M.I.N.D (no need to type any commands)
cd /d "%~dp0"
rem Runs in the background (no window); what it prints goes to mind.log
start "" venv\Scripts\pythonw.exe main.py
