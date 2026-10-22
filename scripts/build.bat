@echo off
setlocal
python "%~dp0install.py" build %*
exit /b %errorlevel%
