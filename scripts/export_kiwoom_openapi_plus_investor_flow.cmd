@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0export_kiwoom_openapi_plus_investor_flow.ps1" %*
exit /b %ERRORLEVEL%
