@echo off
setlocal
chcp 65001 >nul
call "%~dp0run_live_pipeline.cmd" -NoReport %*
set PIPELINE_EXIT=%ERRORLEVEL%
if not "%PIPELINE_EXIT%"=="0" (
  echo Live pipeline failed before verification.
  endlocal & exit /b %PIPELINE_EXIT%
)
call "%~dp0verify_latest_run.cmd"
set VERIFY_EXIT=%ERRORLEVEL%
endlocal & exit /b %VERIFY_EXIT%
