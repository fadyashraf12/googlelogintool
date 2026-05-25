@echo off
python main.py
if errorlevel 1 (
    echo.
    echo App crashed. Run setup.bat first if you haven't already.
    pause
)
