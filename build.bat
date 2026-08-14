@echo off
REM Compatibility launcher; canonical build script lives in scripts\build.bat.
call "%~dp0scripts\build.bat" %*
exit /b %errorlevel%
