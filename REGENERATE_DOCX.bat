@echo off
chcp 65001 >nul
title Regenerate Word Document
echo ============================================
echo   Regenerate Word Document From Markdown
echo ============================================
echo.
echo   Paste the path to a .md file when asked,
echo   or drag the .md file onto this .bat file.
echo.

:: Change to the directory of this batch file (drag-and-drop does not set it)
cd /d "%~dp0"

:: python-docx is the only thing this tool needs
py -c "import docx" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    py -m pip install -r code\requirements.txt --quiet
)

py code\reformat.py "%~1"

echo.
echo ============================================
echo   Finished.
echo ============================================
pause
