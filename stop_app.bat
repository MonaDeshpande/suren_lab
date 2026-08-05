@echo off
REM =============================================================================
REM S Testing Laboratory — stop Customer Test Request app (Streamlit on 8510)
REM Double-click this file, or run from Command Prompt:
REM   stop_app.bat
REM Leaves Docker Postgres running for tests / next launch.
REM =============================================================================

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "APP_PORT=8510"

echo.
echo ============================================================
echo   S Testing Laboratory
echo   Stop Customer Test Request App
echo ============================================================
echo.

set "FOUND=0"

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%APP_PORT%" ^| findstr "LISTENING"') do (
    set "FOUND=1"
    echo Stopping process on port %APP_PORT% ^(PID %%P^)...
    taskkill /PID %%P /F >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Could not stop PID %%P.
    ) else (
        echo [OK] Stopped PID %%P.
    )
)

if "!FOUND!"=="0" (
    echo [INFO] No process listening on port %APP_PORT%. App is not running.
) else (
    echo.
    echo [OK] Streamlit app stopped.
    echo      Postgres on port 5433 was left running.
)

echo.
pause
endlocal
