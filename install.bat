@echo off
rem M.I.N.D installer: double-click this. (It runs install.ps1; safe to run again.)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
