@echo off
REM Risk of Rain 2 Pool Optimizer - Web Interface Launcher

echo ================================================================
echo Risk of Rain 2 Pool Optimizer - Starting Web Interface
echo ================================================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please set up the virtual environment first.
    pause
    exit /b 1
)

REM Check if item data exists
if not exist "data\items.csv" (
    echo WARNING: Item data not found!
    echo Downloading item data from wiki...
    echo.
    .venv\Scripts\python.exe main.py export
    echo.
)

REM Start the web server
echo Starting Flask web server...
echo.
echo ^> Open http://localhost:5000 in your browser
echo ^> Press Ctrl+C to stop the server
echo.
echo ================================================================
echo.

.venv\Scripts\python.exe app.py

pause
