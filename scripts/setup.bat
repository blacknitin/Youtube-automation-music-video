@echo off
REM ============================================================
REM SongForge - one-time setup for Windows (run:  scripts\setup.bat )
REM Installs Python deps and builds nothing else. FFmpeg/Ollama
REM instructions are printed at the end.
REM ============================================================
cd /d "%~dp0.."

echo [1/3] Creating Python virtual environment...
python -m venv backend\.venv
call backend\.venv\Scripts\activate.bat

echo [2/3] Installing Python dependencies...
python -m pip install --upgrade pip
pip install -r backend\requirements.txt

echo.
echo [3/3] Done!
echo ------------------------------------------------------------
echo Next steps:
echo   1. Install FFmpeg:            winget install Gyan.FFmpeg
echo      (or download from https://www.gyan.dev/ffmpeg/builds/ )
echo   2. For real AI lyrics, install Ollama:  https://ollama.com
echo      then run:  ollama pull llama3.1
echo   3. For AI art, install ComfyUI:         https://www.comfy.org
echo   4. Start the app:             scripts\run.bat
echo   5. Open:                      http://localhost:8000
echo ------------------------------------------------------------
pause
