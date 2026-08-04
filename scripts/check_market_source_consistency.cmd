@echo off
setlocal
chcp 65001 >nul
python -m alpha_cycle.market_consistency_cli %*
set EXIT_CODE=%ERRORLEVEL%
endlocal & exit /b %EXIT_CODE%
