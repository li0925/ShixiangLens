@echo off
cd /d "%~dp0"
if not exist ".venv-latest\Scripts\pythonw.exe" (
  echo Please install dependencies in .venv-latest first. See README.md.
  pause
  exit /b 1
)
start "" ".venv-latest\Scripts\pythonw.exe" "%~dp0main.py"
