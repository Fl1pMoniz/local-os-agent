@echo off
chcp 65001 >nul
title Aperture Science - GLaDOS CLI Console
cd /d "%~dp0"

echo ====================================================
echo   APERTURE SCIENCE COMPUTER-AIDED ENRICHMENT CENTER
echo       GLaDOS Text-Only CLI Terminal Interface
echo ====================================================

:: Check if Ollama or local LLM is responding
curl.exe -s --connect-timeout 2 http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Local LLM server at localhost:11434 is not responding.
    echo     Attempting to start Ollama in background...
    start /B ollama serve >nul 2>&1
    ping 127.0.0.1 -n 3 >nul
)

:: Launch the agent in pure CLI text-only mode
python main.py --model glados:3b --cli

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] CLI console closed with an error code.
    pause
)

