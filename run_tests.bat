@echo off
REM =============================================================================
REM S Testing Laboratory — run pytest suite
REM Double-click this file, or run from Command Prompt:
REM   run_tests.bat
REM =============================================================================

setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo   S Testing Laboratory
echo   Run Test Cases
echo ============================================================
echo.

REM --- Prefer "py" launcher, fall back to "python" ---
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 (
        set "PY=python"
    ) else (
        echo [ERROR] Python was not found on PATH.
        echo         Install Python 3 and tick "Add Python to PATH", then retry.
        echo.
        pause
        exit /b 1
    )
)

echo [1/4] Checking Python...
%PY% --version
if errorlevel 1 (
    echo [ERROR] Could not run Python.
    pause
    exit /b 1
)

echo.
echo [2/4] Ensuring dependencies are installed...
%PY% -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [WARN] pip install reported a problem. Continuing anyway...
)

echo.
echo [3/4] Checking Docker Postgres on port 5433...
docker compose ps
docker exec sls_lab_db psql -U sls_user -d sls_lab -c "SELECT 1;" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Database container not ready. Starting it...
    docker compose up -d
    timeout /t 8 /nobreak >nul
    docker exec sls_lab_db psql -U sls_user -d sls_lab -c "SELECT 1;" >nul 2>&1
)
if errorlevel 1 (
    echo [WARN] PostgreSQL not reachable on port 5433.
    echo        Integration tests will SKIP ^(no 5-sample CTR preview; 2-sample CTR still written^).
) else (
    echo [OK] PostgreSQL is ready for integration tests.
)

echo.
echo [4/4] Running pytest (excluding demo E2E; use run_e2e_demo.bat or pytest -m e2e)...
echo.

set "PYTHONPATH=%CD%;%PYTHONPATH%"

%PY% -m pytest -q -m "not e2e"
set "RC=%ERRORLEVEL%"

echo.
if %RC% neq 0 (
    echo [FAIL] Tests failed ^(exit code %RC%^).
) else (
    echo [OK] Tests finished successfully.
    echo.
    echo Document previews ^(open in Explorer^):
    echo   tests\output_preview\ctr\           — CTR PDF+DOCX ^(Reception path; 5-sample needs Postgres^)
    echo   tests\output_preview\integration\  — dummy CTR/protocol slices ^(Postgres^)
    echo   tests\output_preview\app_flow\     — full bundle per category ^(Postgres + Word/LibreOffice for protocol/final PDF^)
    if exist "tests\output_preview\ctr" (
        start "" "%CD%\tests\output_preview\ctr"
    )
)

echo.
pause
exit /b %RC%
endlocal
