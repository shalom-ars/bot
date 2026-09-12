$backendProcesses = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "run_backend.bat|uvicorn app.main:app" -and $_.ProcessId -ne $PID }
foreach ($p in $backendProcesses) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Host "Polymarket Bot stopped."
