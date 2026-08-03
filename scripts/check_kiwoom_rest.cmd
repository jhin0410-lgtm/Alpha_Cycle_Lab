@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_kiwoom_rest.ps1" %*
set EXIT_CODE=%ERRORLEVEL%
endlocal & exit /b %EXIT_CODE%
