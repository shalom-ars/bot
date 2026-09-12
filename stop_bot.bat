@echo off
echo Stopping Polymarket Bot...
wmic process where "commandline like '%%run_backend.bat%%'" call terminate >nul 2>&1
wmic process where "commandline like '%%uvicorn app.main:app%%'" call terminate >nul 2>&1
echo Bot has been stopped.
