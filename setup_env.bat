@echo off
echo ========================================================
echo GroundTruth-RAG Setup Script
echo ========================================================
cd /d "%~dp0"

echo [1/2] Setting up Python Backend Virtual Environment...
cd backend
if not exist ".venv" (
    echo Creating virtual environment in backend\.venv ...
    python -m venv .venv
)
echo Installing backend requirements...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env
    )
)
cd ..

echo.
echo [2/2] Setting up Frontend Dependencies...
cd frontend
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env
    )
)
echo Running npm install...
call npm install
cd ..

echo.
echo ========================================================
echo Setup Complete!
echo You can now start the application:
echo   1. Run start_backend.bat  (starts backend on http://127.0.0.1:8000)
echo   2. Run start_frontend.bat (starts frontend on http://127.0.0.1:5173)
echo ========================================================
pause
