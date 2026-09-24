@echo off
REM =============================================================================
REM S Testing Laboratory — create / update database tables
REM Double-click this file after PostgreSQL is running (e.g. docker compose up -d)
REM =============================================================================

setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo   S Testing Laboratory — Database table setup
echo ============================================================
echo.

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 (
        set "PY=python"
    ) else (
        echo [ERROR] Python was not found on PATH.
        pause
        exit /b 1
    )
)

echo [1/3] Checking Python...
%PY% --version
if errorlevel 1 (
    echo [ERROR] Could not run Python.
    pause
    exit /b 1
)

echo.
echo [2/3] Ensuring PostgreSQL is reachable...
docker compose ps
docker exec sls_lab_db psql -U sls_user -d sls_lab -c "SELECT 1;" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Database not ready. Starting Docker Postgres...
    docker compose up -d
    timeout /t 8 /nobreak >nul
)

echo.
echo [3/3] Creating / updating tables...
set "PYTHONPATH=%CD%;%PYTHONPATH%"
%PY% scripts/table_creation.py
if errorlevel 1 (
    echo.
    echo [ERROR] Table setup failed.
    pause
    exit /b 1
)

echo.
echo Done. For first login, run:  %PY% scripts/seed_admin.py
echo.
pause
endlocal
