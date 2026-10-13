@echo off
title VisionSwipe AI WebApp
cd /d "%~dp0"

echo =======================================================
echo          Starting VisionSwipe AI WebApp...
echo =======================================================
echo.
echo Opening browser at http://localhost:5000 ...
start "" "http://localhost:5000"
echo.
echo Running Python application (Press Ctrl+C to stop)...
.\venv\Scripts\python.exe app.py
pause
