@echo off
echo Starting RINEX-ADAPTER...

REM Check if running from dist (exe mode) or source (python mode)
if exist "%~dp0RINEX-Adapter.exe" (
    start "" "%~dp0RINEX-Adapter.exe"
    exit /b
)

REM Fallback: run from Python source
if exist "%~dp0adapter_gui.py" (
    python "%~dp0adapter_gui.py"
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to start. Make sure Python 3.8+ is installed.
        echo Install dependencies: pip install -r requirements.txt
        pause
    )
) else (
    echo ERROR: Neither RINEX-Adapter.exe nor adapter_gui.py found.
    echo Please run this from the RINEX-Adapter directory.
    pause
)
