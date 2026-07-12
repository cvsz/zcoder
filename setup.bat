@echo off
REM Setup script for AI Model Coder CLI (Windows)

setlocal enabledelayedexpansion

echo 🚀 AI Model Coder CLI Setup
echo ================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do (
    echo ✅ Python %%i found
)
echo.

REM Create virtual environment
echo 📦 Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    echo ✅ Virtual environment created
) else (
    echo ℹ️  Virtual environment already exists
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo 📦 Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1
echo ✅ pip upgraded

REM Install dependencies
echo 📦 Installing dependencies...
pip install -r requirements.txt
echo ✅ Dependencies installed
echo.

REM Setup .env file
if not exist ".env" (
    echo 🔑 Setting up environment file...
    copy .env.example .env
    echo ✅ Created .env file
    echo.
    echo ⚠️  Please edit .env and add your Anthropic API key:
    echo    ANTHROPIC_API_KEY=sk-ant-your-key-here
) else (
    echo ℹ️  .env file already exists
)

echo.
echo ================================
echo ✅ Setup complete!
echo.
echo To get started:
echo 1. Edit .env and add your API key
echo 2. Run: venv\Scripts\activate
echo 3. Try: python main.py -p "Hello world"
echo.
echo For more examples: python main.py -h
echo.
pause
