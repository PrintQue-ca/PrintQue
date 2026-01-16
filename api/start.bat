@echo off
echo Starting PrintQue API...

REM Check if venv exists
if not exist ".venv" (
    echo Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Start the Flask app
python app.py
