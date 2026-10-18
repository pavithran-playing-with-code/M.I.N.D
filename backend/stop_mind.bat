@echo off
rem Double-click this file to stop M.I.N.D
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if ($c) { Stop-Process -Id $c[0].OwningProcess -Force; Write-Host 'M.I.N.D is off. See you!' } else { Write-Host 'M.I.N.D was not running.' }"
timeout /t 2 >nul
