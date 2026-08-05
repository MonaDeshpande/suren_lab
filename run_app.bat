@echo off
REM =============================================================================
REM S Testing Laboratory — launch Customer Test Request app
REM Double-click this file, or run from Command Prompt:
REM   run_app.bat
REM =============================================================================

setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo   S Testing Laboratory
echo   Customer Test Request App
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
)

echo.
echo [4/4] Starting Streamlit (multi-user — LAN enabled)...
set "APP_PORT=8510"
echo      This PC:  http://localhost:%APP_PORT%
echo      Do NOT use 0.0.0.0 in the browser — use localhost above.
for /f "delims=" %%I in ('%PY% -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2^>nul') do (
    echo      Other PCs: http://%%I:%APP_PORT%
)
echo      Sidebar: Home / Reception / Analyst / Reviewer / Admin
echo      DB: 127.0.0.1:5433  user=sls_user
echo      Press Ctrl+C to stop.
echo.

netstat -ano | findstr ":%APP_PORT%" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo.
    echo [INFO] S_LAB is already running on port %APP_PORT%.
    echo        Open:  http://localhost:%APP_PORT%
    echo        To restart: run stop_app.bat, then run_app.bat again.
    echo.
    pause
    exit /b 0
)

REM Make sure imports resolve from project root
set "PYTHONPATH=%CD%;%PYTHONPATH%"

REM .streamlit/config.toml sets address=0.0.0.0 for multi-machine access
%PY% -m streamlit run app.py --server.headless false

echo.
echo App stopped.
pause
endlocal
