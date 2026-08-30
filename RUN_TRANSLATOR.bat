@echo off
title Modular Translator CLI
echo ============================================
echo   Modular Translator CLI Launcher
echo ============================================
echo.

:: Change to the directory of this batch file
cd /d "%~dp0"

:: Check if .env exists
if not exist ".env" (
    echo [ERROR] .env file not found! 
    echo Please ensure the .env file is in the same folder as this batch file.
    pause
    exit /b
)

:: Check for dependencies
echo [1/2] Ensuring dependencies are installed...
py -m pip install -r code\requirements.txt --quiet

:: Run the program
echo [2/2] Starting translation system...
py code\main.py

echo.
echo ============================================
echo   Program finished.
echo ============================================
pause
