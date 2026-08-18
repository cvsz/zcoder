@echo off
setlocal
cd /d "%~dp0.."
python --version >nul 2>&1 || (echo ERROR: Python is required & exit /b 1)
set "BUILD_VENV=.build-venv"
if not exist "%BUILD_VENV%\Scripts\python.exe" python -m venv "%BUILD_VENV%" || exit /b 1
"%BUILD_VENV%\Scripts\python.exe" -m pip install --upgrade pip || exit /b 1
"%BUILD_VENV%\Scripts\python.exe" -m pip install -e . pyinstaller || exit /b 1
if exist build\pyinstaller rmdir /s /q build\pyinstaller
if exist dist\zcoder.exe del /q dist\zcoder.exe
"%BUILD_VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller spec\zcoder.spec || exit /b 1
if not exist dist\zcoder.exe (echo ERROR: dist\zcoder.exe was not produced & exit /b 1)
dist\zcoder.exe --version || exit /b 1
echo Built: %CD%\dist\zcoder.exe
