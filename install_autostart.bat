@echo off
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo @echo off > "%STARTUP_FOLDER%\start_polymarket_bot.bat"
echo powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0start_bot.ps1" >> "%STARTUP_FOLDER%\start_polymarket_bot.bat"

echo Installing Polymarket Bot Auto-Start...
echo Done! The bot will now start automatically when you log in.
pause
