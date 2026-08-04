@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0resolve_project_python.ps1" -Diagnostic
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo Diagnostic report: %~dp0..\data\private\diagnostics\project_python_resolution.json
exit /b %EXIT_CODE%
