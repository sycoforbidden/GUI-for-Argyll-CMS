@echo off
REM ArgyllCMS Profiling GUI launcher
REM Install PySide6 first: pip install PySide6

cd /d "%~dp0"
python main.py %*
if errorlevel 1 (
    echo.
    echo If you see import errors, install dependencies:
    echo   pip install PySide6
    echo.
    pause
)
