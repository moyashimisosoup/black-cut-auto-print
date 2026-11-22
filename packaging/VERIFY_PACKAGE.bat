@echo off
setlocal
chcp 65001 >nul
echo APP-033 update bundle integrity check (no install)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply_update.ps1" -CheckPackageOnly
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (echo PACKAGE OK - no EXE has been replaced.) else (echo PACKAGE CHECK FAILED - do not update. Re-extract ZIP into a fresh empty folder.)
pause
exit /b %RESULT%
