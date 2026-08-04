@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_alpha_cycle_module.ps1" -Module "alpha_cycle.market_consistency_cli" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_alpha_cycle_module.ps1" -Module "alpha_cycle.market_consistency_diagnostics_cli"
)
endlocal & exit /b %EXIT_CODE%
