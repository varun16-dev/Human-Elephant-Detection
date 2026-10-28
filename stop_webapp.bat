@echo off
title Stop Elephant Early Warning System
color 0C
echo =====================================================================
echo    STOPPING ELEPHANT EARLY WARNING SYSTEM BACKGROUND SERVICES
echo =====================================================================
echo.

echo [*] Terminating processes running on port 5000...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host 'Stopped web server process PID:' $_.OwningProcess }"

echo [*] Terminating background detection and camera monitor processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*human_fall_detect*' -or $_.CommandLine -like '*camera_alert_monitor*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host 'Stopped process PID:' $_.ProcessId }"

echo [PASS] All background services stopped successfully.
ping 127.0.0.1 -n 3 >nul 2>&1

