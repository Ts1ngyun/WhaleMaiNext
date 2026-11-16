@echo off
cd /d "%~dp0"
if not exist ".setup-complete" (
    powershell -NoProfile -File "%~dp0Setup.ps1"
    if errorlevel 1 exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0desktop.py"
