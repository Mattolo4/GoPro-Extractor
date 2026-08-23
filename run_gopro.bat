@echo off
REM Insert the GoPro SD card, then double-click this file.
REM It first shows a PREVIEW (nothing is touched), then asks before moving anything.

cd /d "%~dp0"
set PY=%~dp0.venv\Scripts\python.exe

if not exist "%PY%" (
    echo Virtualenv not found. Create it once with:
    echo    python -m venv .venv
    echo    .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo ============================================
echo   PREVIEW - no file will be moved yet
echo ============================================
"%PY%" main.py --dry-run %*
if errorlevel 1 (
    echo.
    echo Preview failed - is the SD card inserted?
    pause
    exit /b 1
)

echo.
set /p OK="Move the files for real? [y/N] "
if /i not "%OK%"=="y" (
    echo Cancelled - nothing was moved.
    pause
    exit /b 0
)

echo.
echo ============================================
echo   MOVING FILES
echo ============================================
"%PY%" main.py %*

echo.
echo Done. Check the destination folder before formatting the SD card.
pause
