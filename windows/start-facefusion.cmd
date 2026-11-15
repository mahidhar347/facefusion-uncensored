@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Create the .venv and install FaceFusion first. See README.md.
    pause
    exit /b 1
)
set "GRADIO_SERVER_NAME=127.0.0.1"
".venv\Scripts\python.exe" facefusion.py run --open-browser %*
