@echo off
chcp 65001 >nul
title Aperture OS - GLaDOS (Visual UI + Voice Mode)
cd /d "%~dp0"

echo ====================================================
echo      Starting Aperture OS GLaDOS Interface...
echo      Visual UI : http://localhost:5000
echo      Voice     : GLaDOS Neural Voice
echo ====================================================

:: Check if Ollama or local LLM is responding
curl.exe -s --connect-timeout 2 http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Local LLM server at localhost:11434 is not responding.
    echo     Attempting to start Ollama in background...
    start /B ollama serve >nul 2>&1
    timeout /t 3 /nobreak >nul
)

:: Launch the agent in voice mode with visual UI enabled
python main.py --model glados:3b --voice --ui

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Agent stopped with an error code.
    pause
)
