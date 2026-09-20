@echo off
REM SongForge - start the app (run:  scripts\run.bat )
cd /d "%~dp0..\backend"
call .venv\Scripts\activate.bat
set DATA_DIR=%~dp0..\backend\data
echo.
echo   SongForge starting on  http://localhost:8000
echo   (leave this window open; press Ctrl+C to stop)
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
