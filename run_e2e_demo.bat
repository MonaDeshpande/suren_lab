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

echo [1/3] Rebuilding food report template from DK Brothers reference...
%PY% scripts/build_food_test_report_template.py
if errorlevel 1 (
    echo [ERROR] Template build failed.
    pause
    exit /b 1
)

echo.
echo [2/3] Generating CTR, protocol, and final report downloads...
set "PYTHONPATH=%CD%;%PYTHONPATH%"
%PY% scripts/generate_e2e_downloads.py
if errorlevel 1 (
    echo [ERROR] E2E generation failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Done.
echo      Output folder: downloads\e2e_demo\
echo      - 01_water_abc_foods\
echo      - 02_micro_xyz_caterers\
echo      - 03_food_nutrihealth\
echo      - 04_food_dk_jaggery\
echo.
pause
endlocal
