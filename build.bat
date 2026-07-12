@echo off
REM Build script for AI Model Coder CLI standalone executable (Windows)
REM Creates a single .exe that doesn't require Python

setlocal enabledelayedexpansion

echo 🔨 AI Model Coder CLI - Standalone Build
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is required but not found
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do (
    echo ✅ Python %%i found
)
echo.

REM Create build virtual environment
echo 📦 Creating build environment...
if not exist "build-venv" (
    python -m venv build-venv
)

call build-venv\Scripts\activate.bat

REM Install dependencies
echo 📦 Installing build dependencies...
python -m pip install --upgrade pip >nul 2>&1
pip install pyinstaller anthropic python-dotenv >nul 2>&1
echo ✅ Dependencies installed
echo.

REM Create output directory
if not exist "dist" mkdir dist

REM Build executable
echo 🔨 Building standalone executable...
echo    This may take 1-2 minutes...
echo.

pyinstaller --onefile ^
    --name ai-coder ^
    --console ^
    --hidden-import=anthropic ^
    main.py

echo.
echo ✅ Build complete!
echo.

REM Check output
if exist "dist\ai-coder.exe" (
    for /F %%A in ('dir /b dist\ai-coder.exe') do (
        echo 🎉 Standalone executable created: dist\ai-coder.exe
    )
    echo.
    echo Next steps:
    echo 1. Copy 'dist\ai-coder.exe' to any location
    echo 2. Set API key: set ANTHROPIC_API_KEY=sk-ant-...
    echo 3. Run: ai-coder.exe -p "Create code"
    echo.
) else (
    echo ❌ Build failed
    pause
    exit /b 1
)

REM Cleanup
echo 🧹 Cleaning up build files...
rmdir /s /q build >nul 2>&1
del ai-coder.spec >nul 2>&1
echo ✅ Cleanup complete
echo.

echo Ready to deploy! The .exe file in dist\ is self-contained.
pause
