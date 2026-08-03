@echo off
setlocal
chcp 65001 >nul
python -m alpha_cycle.live_verify_cli %*
set EXIT_CODE=%ERRORLEVEL%
endlocal & exit /b %EXIT_CODE%
