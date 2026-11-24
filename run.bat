@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    start "" py -3 run.py
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    start "" python run.py
    exit /b 0
)

echo.
echo Python 3.10+ was not found.
echo Install Python from https://www.python.org/downloads/
echo and enable "Add python.exe to PATH".
echo.
pause
exit /b 1
