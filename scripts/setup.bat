@echo off
setlocal
python "%~dp0install.py" setup %*
exit /b %errorlevel%
