@echo off
REM Запускает видеоредактор с помощью pythonw.exe из виртуального окружения,
REM чтобы избежать появления консольного окна.

start "Video Editor" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
