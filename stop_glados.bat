@echo off
chcp 65001 >nul
title Aperture OS - Stop GLaDOS
cd /d "%~dp0"

echo ====================================================
echo      Stopping any running GLaDOS instances...
echo ====================================================

powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Stopped GLaDOS process PID: ' + $_.ProcessId) }"

echo Done. All GLaDOS instances have been cleanly stopped.
ping 127.0.0.1 -n 2 >nul
