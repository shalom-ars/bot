@echo off
cd /d "%~dp0backend"
echo [%date% %time%] Startup sequence initiated >> bot_daemon.log

:: Attempt to create a lock file with exclusive write access
9>bot.lock (
    echo [%date% %time%] Acquired process lock >> bot_daemon.log

    :loop
    echo [%date% %time%] Starting backend (includes frontend via FastAPI) >> bot_daemon.log
    set SAAS_SECRET_KEY=09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7
    .venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000 >> bot_daemon.log 2>&1
    echo [%date% %time%] Process crashed or stopped. Restarting in 5s... >> bot_daemon.log
    ping 127.0.0.1 -n 6 >nul
    goto loop
) || (
    echo [%date% %time%] ERROR: Another instance is already running. Exiting. >> bot_daemon.log
    exit /b 1
)
