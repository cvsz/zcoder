@echo off
REM Compatibility launcher; canonical setup script lives in scripts\setup.bat.
call "%~dp0scripts\setup.bat" %*
exit /b %errorlevel%
