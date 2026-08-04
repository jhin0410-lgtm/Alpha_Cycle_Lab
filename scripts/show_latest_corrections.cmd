@echo off
setlocal
chcp 65001 >nul
for %%I in ("%~dp0..") do set "REPOSITORY_ROOT=%%~fI"
pushd "%REPOSITORY_ROOT%" >nul || exit /b 2
if defined PYTHONPATH (
    set "PYTHONPATH=%REPOSITORY_ROOT%\src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%REPOSITORY_ROOT%\src"
)
python -m alpha_cycle.correction_lineage_cli %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
endlocal & exit /b %EXIT_CODE%
