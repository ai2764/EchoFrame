@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_app.ps1" %*
exit /b %ERRORLEVEL%

