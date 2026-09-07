@echo off
REM =============================================================================
REM S Testing Laboratory — generate E2E demo documents (CTR + protocol + reports)
REM Double-click or run: run_e2e_demo.bat
REM =============================================================================

setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo   S Testing Laboratory — E2E demo document bundle
echo ============================================================
echo.

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

echo [1/4] Checking PostgreSQL connection...
set "PYTHONPATH=%CD%;%PYTHONPATH%"
%PY% -c "from services.e2e_app_flow import prepare_app_e2e; prepare_app_e2e(); print('Database OK')"
if errorlevel 1 (
    echo [ERROR] PostgreSQL is not reachable. Start Docker: docker compose up -d
    echo         Or run offline: python scripts/generate_e2e_downloads.py --offline
    pause
    exit /b 1
)

echo.
echo [2/4] Rebuilding food report template from DK Brothers reference...
%PY% scripts/build_food_test_report_template.py
if errorlevel 1 (
    echo [ERROR] Template build failed.
    pause
    exit /b 1
)

echo.
echo [3/4] Generating CTR, protocol, and final report downloads (app flow)...
%PY% scripts/generate_e2e_downloads.py
if errorlevel 1 (
    echo [ERROR] E2E generation failed.
    pause
    exit /b 1
)

echo.
echo [4/4] Done.
echo      Output folder: downloads\e2e_demo\
echo      - 01_water_abc_foods\
echo      - 02_micro_xyz_caterers\
echo      - 03_food_nutrihealth\
echo      - 04_food_dk_jaggery\
echo.
pause
endlocal
