@echo off
setlocal
cd /d "%~dp0.."
python --version >nul 2>&1 || (echo ERROR: Python 3.9+ is required & exit /b 1)
set "VENV=venv"
if not exist "%VENV%\Scripts\python.exe" python -m venv "%VENV%" || exit /b 1
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip || exit /b 1
"%VENV%\Scripts\python.exe" -m pip install -e . || exit /b 1
if not exist .env copy .env.example .env >nul
"%VENV%\Scripts\python.exe" main.py --version || exit /b 1
echo Setup complete. Activate with: %VENV%\Scripts\activate.bat
