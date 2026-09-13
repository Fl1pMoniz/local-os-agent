@echo off
setlocal
chcp 65001 >nul
title Aperture Science - GLaDOS Web Console

set "SCRIPT_DIR=c:\Users\fiui2\OneDrive\Documentos\PROJETOSPROGRAM\local-os-agent"
set "PYTHON_EXE=python"
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    set "PYTHON_EXE=C:\Python314\python.exe"
)

:: Check if local LLM server is responding at localhost:11434
curl.exe -s --connect-timeout 2 http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Local LLM server at localhost:11434 is not responding.
    echo     Attempting to start Ollama in background...
    start /B ollama serve >nul 2>&1
    ping 127.0.0.1 -n 3 >nul
)

echo [*] Launching Aperture Science GLaDOS ASCII Web Console...
echo [*] Opening browser at http://127.0.0.1:5000...
"%PYTHON_EXE%" "%SCRIPT_DIR%\main.py" --model glados:3b --web %*

