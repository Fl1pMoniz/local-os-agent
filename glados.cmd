@echo off
setlocal
chcp 65001 >nul
title Aperture Science - GLaDOS Terminal

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

:: Check if web/ui is requested as first argument
if /I "%~1"=="web" (
    "%PYTHON_EXE%" "%SCRIPT_DIR%\main.py" --model glados:3b --web
    exit /b %ERRORLEVEL%
)
if /I "%~1"=="ui" (
    "%PYTHON_EXE%" "%SCRIPT_DIR%\main.py" --model glados:3b --web
    exit /b %ERRORLEVEL%
)

:: Check if --voice or --ui or --web is explicitly passed
echo "%*" | findstr /I /C:"--voice" /C:"-v" /C:"--ui" /C:"--web" >nul
if %ERRORLEVEL% EQU 0 (
    "%PYTHON_EXE%" "%SCRIPT_DIR%\main.py" --model glados:3b %*
) else (
    "%PYTHON_EXE%" "%SCRIPT_DIR%\main.py" --model glados:3b --cli %*
)

