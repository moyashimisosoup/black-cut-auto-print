@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
echo.
echo APP-033 Black Cut Print - Safe EXE Update
echo ==========================================
echo Close the Black Cut Print app, including its tray icon, before updating.
echo Do not run the existing app during replacement.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply_update.ps1" -ExistingExe "%~1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo Update failed or was cancelled. Original EXE should remain intact.
) else (
  echo Finished. Please start the updated EXE manually.
)
echo.
pause
exit /b %RESULT%
