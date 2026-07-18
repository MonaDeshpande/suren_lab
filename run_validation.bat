@echo off
REM =============================================================================
REM S Testing Laboratory — generate validation Word pack (URS, Risk, IQ/OQ/PQ, SOP)
REM Double-click this file, or run from Command Prompt:
REM   run_validation.bat
REM =============================================================================

setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo   S Testing Laboratory
echo   Validation Document Generator
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

echo [1/3] Checking Python...
%PY% --version
if errorlevel 1 (
    echo [ERROR] Could not run Python.
    pause
    exit /b 1
)

echo.
echo [2/3] Ensuring dependencies are installed...
%PY% -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [WARN] pip install reported a problem. Continuing anyway...
)

echo.
echo [3/3] Generating validation Word documents...
echo.

set "PYTHONPATH=%CD%;%PYTHONPATH%"

%PY% -m validation.generate_all
set "RC=%ERRORLEVEL%"

echo.
if %RC% neq 0 (
    echo [FAIL] Validation document generation failed ^(exit code %RC%^).
) else (
    echo [OK] Documents written under docs\validation\generated\
)

echo.
pause
exit /b %RC%
endlocal
