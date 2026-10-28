@echo off
title Integrated IoT & Edge-AI Wildlife Warning System
color 0A

echo =====================================================================
echo    INTEGRATED IoT & EDGE-AI ACOUSTIC EARLY WARNING SYSTEM (PHASE II)
echo                     HUMAN-ELEPHANT CONFLICT MITIGATION
echo =====================================================================
echo.

cd /d "%~dp0Integrated-IoT-and-Edge-AI-Acoustic-Early-Warning-System-for-Human-Elephant-Conflict-Mitigation-main" 2>nul || cd /d "%~dp0"

echo [*] Starting Web Application Server on http://127.0.0.1:5000 ...
echo [*] Opening Dashboard in your browser...
echo.

set ELEPHANT_HEADLESS=1

start "" "http://127.0.0.1:5000"

python server.py

if errorlevel 1 (
    echo.
    echo [!] Server exited with an error. Press any key to close...
    pause >nul
)
