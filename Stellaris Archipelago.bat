@echo off
rem Stellaris x Archipelago — double-click to open the setup dashboard.
rem No terminal knowledge needed: the dashboard installs the mod and bridge,
rem builds your YAML, and runs the bridge while you play.
setlocal
cd /d "%~dp0"
title Stellaris Archipelago

py -3 --version >nul 2>&1
if %errorlevel%==0 (
    py -3 dashboard.py
    goto :done
)
python --version >nul 2>&1
if %errorlevel%==0 (
    python dashboard.py
    goto :done
)

echo.
echo  Python 3 is not installed (or not on PATH).
echo.
echo  1. The Python download page will open in your browser.
echo  2. Run the installer and TICK "Add python.exe to PATH" on the first screen.
echo  3. When it finishes, double-click this file again.
echo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:done
if not %errorlevel%==0 (
    echo.
    echo  The dashboard stopped with an error (see above).
    pause
)
