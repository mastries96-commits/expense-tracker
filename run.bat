@echo off
echo ================================================
echo   Expense Tracker
echo   Dashboard: http://localhost:5000
echo   Telegram bot: active (polling)
echo ================================================
echo.

cd /d "%~dp0"
python run.py
pause
