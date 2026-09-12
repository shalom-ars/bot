@echo off
echo Starting Polymarket Quant Bot MVP...

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH.
    pause
    exit /b
)

:: Check if Node is installed
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Node.js is not installed or not in PATH.
    pause
    exit /b
)

:: Start Backend
echo Starting FastAPI Backend...
start cmd /k "cd backend && call .venv\Scripts\activate && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

:: Start Frontend
echo Starting React Frontend...
start cmd /k "cd frontend && npm run dev"

echo.
echo ========================================================
echo Polymarket Quant Bot MVP (PAPER TRADING ONLY)
echo ========================================================
echo Backend API: http://127.0.0.1:8000/api/status
echo Frontend Dashboard: http://localhost:5173
echo.
echo Press any key to exit this launcher (services will keep running in separate windows)...
pause >nul
