@echo off
setlocal

REM Проверяем, существует ли папка виртуального окружения
IF NOT EXIST "%~dp0.venv" (
    echo.
    echo Virtual environment not found.
    echo Performing first-time setup...
    echo.

    REM Ищем python в системном PATH
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo ERROR: Python is not found in your system PATH.
        echo Please install Python from python.org and make sure it is added to PATH.
        pause
        exit /b
    )

    echo Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b
    )

    echo Installing dependencies...
    call "%~dp0.venv\Scripts\activate.bat"
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies from requirements.txt.
        pause
        exit /b
    )
    
    echo.
    echo Setup complete. Launching application...
    echo.
)

REM Запускаем приложение без консольного окна
echo Launching Video Editor...
start "Video Editor" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"

endlocal