@echo off
chcp 65001 >nul
title Aperture OS - GLaDOS (Voice Mode)
cd /d "%~dp0"

echo ====================================================
echo      Starting Aperture OS GLaDOS Voice Mode...
echo      Voice: GLaDOS (Synthetic, Coldly Polite)
echo ====================================================

:: Check if Ollama or local LLM is responding
curl.exe -s --connect-timeout 2 http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Local LLM server at localhost:11434 is not responding.
    echo     Attempting to start Ollama in background...
    start /B ollama serve >nul 2>&1
    ping 127.0.0.1 -n 3 >nul
)

:: Launch the agent in voice mode with the GLaDOS 3B model
python main.py --model glados:3b --voice

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Agent stopped with an error code.
    pause
)

