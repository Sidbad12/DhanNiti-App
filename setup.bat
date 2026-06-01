@echo off
rem setup.bat — DhanNiti Launcher

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo python is not installed or not in PATH.
    pause
    exit /b 1
)

python setup.py
pause
