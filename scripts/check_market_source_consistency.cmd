@echo off
setlocal
chcp 65001 >nul
rem Inner assessment remains -Module "alpha_cycle.market_consistency_runner_cli" behind the integrity boundary.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_alpha_cycle_module.ps1" -Module "alpha_cycle.market_consistency_integrity_runner_cli" %*
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
