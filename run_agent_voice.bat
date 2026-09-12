@echo off
chcp 65001 >nul
title Local OS Agent (Voice Mode)
cd /d "%~dp0"

echo ====================================================
echo      Starting Local OS Agent in Voice Mode...
echo      Voice: Elegant British Female (Sonia)
echo ====================================================

:: Check if Ollama or local LLM is responding
curl.exe -s --connect-timeout 2 http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Local LLM server at localhost:11434 is not responding.
    echo     Attempting to start Ollama in background...
    start /B ollama serve >nul 2>&1
    timeout /t 3 /nobreak >nul
)

:: Launch the agent directly in voice interactive mode
python main.py --model llama3.1:latest --voice

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Agent stopped with an error code.
    pause
)
