@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Bot-nagaduvalnyk
venv\Scripts\python.exe bot.py
echo.
echo ======================================
echo  Bot zupynyvsya. Dyvy prychynu vyshche
echo  abo u faili bot.log
echo ======================================
pause
