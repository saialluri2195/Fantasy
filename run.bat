@echo off
setlocal EnableExtensions
cd /d "%~dp0dimez_ai"
if errorlevel 1 (
    echo Could not find dimez_ai. Run this from the Fantasy repo root.
    pause
    exit /b 1
)

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python was not found. Install Python and try again.
        pause
        exit /b 1
    )
    set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Failed to create .venv
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo Failed to activate .venv
    pause
    exit /b 1
)

echo Installing dependencies...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo pip install failed
    pause
    exit /b 1
)

if not exist ".env" (
    copy /Y ".env.template" ".env" >nul
    echo Created .env from .env.template. Add ODDS_API_KEY for live odds.
)

echo Fetching live NFL odds from The Odds API...
python run_pipeline.py --stage all --force-refresh
if errorlevel 1 (
    echo Live refresh failed. Falling back to bundled fixture data.
    python run_pipeline.py --stage all --fixture data\fixtures\odds_api_nfl.json
    if errorlevel 1 (
        echo Pipeline failed
        pause
        exit /b 1
    )
)

echo.
echo Starting NFL Parlay Assister at http://127.0.0.1:8000/
echo API docs: http://127.0.0.1:8000/docs
echo Press Ctrl+C to stop.
echo.
python run_pipeline.py --stage serve
pause
endlocal
