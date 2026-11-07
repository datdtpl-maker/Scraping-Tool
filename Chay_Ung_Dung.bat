@echo off
chcp 65001 > nul
title Derm Keyword Hunter - Gemini Flash App
cd /d "%~dp0"

echo ========================================================
echo    Derm Keyword Hunter - AI Gemini Flash & SQLite
echo ========================================================
echo Dang khoi chay ung dung Desktop...
start pythonw gui_app.py
exit
