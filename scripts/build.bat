@echo off
setlocal
cd /d "%~dp0.."

python --version >nul 2>&1 || (echo ERROR: Python is required & exit /b 1)
set "BUILD_VENV=.build-venv"
if not exist "%BUILD_VENV%\Scripts\python.exe" python -m venv "%BUILD_VENV%"
"%BUILD_VENV%\Scripts\python.exe" -m pip install --upgrade pip || exit /b 1
"%BUILD_VENV%\Scripts\python.exe" -m pip install -e . pyinstaller || exit /b 1
if exist build\pyinstaller rmdir /s /q build\pyinstaller
if exist dist\ai-coder.exe del /q dist\ai-coder.exe
"%BUILD_VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller spec\ai-coder.spec || exit /b 1
if not exist dist\ai-coder.exe (echo ERROR: dist\ai-coder.exe was not produced & exit /b 1)
dist\ai-coder.exe --version || exit /b 1
echo Built: %CD%\dist\ai-coder.exe
