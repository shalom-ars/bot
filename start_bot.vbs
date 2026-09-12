Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c " & Chr(34) & "C:\Users\AR\.gemini\antigravity\scratch\polymarket-bot\run_backend.bat" & Chr(34), 0
Set WshShell = Nothing
