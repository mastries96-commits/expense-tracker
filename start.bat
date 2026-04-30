@echo off
title Expense Tracker Bot
color 0A
echo.
echo  ================================================
echo    Expense Tracker  ^|  Telegram + Live Dashboard
echo  ================================================
echo.

if not exist ".env" (
  echo  ERROR: .env file not found!
  echo.
  echo  Steps to fix:
  echo    1. Copy .env.example  to  .env
  echo    2. Open .env and paste your Telegram bot token
  echo    3. Get a token from @BotFather on Telegram
  echo.
  pause
  exit /b 1
)

echo  Starting bot server...
echo  Dashboard will open at  http://localhost:3000
echo  Press Ctrl+C to stop.
echo.

timeout /t 2 /nobreak >nul
start "" "http://localhost:3000"
node bot.js

echo.
pause
