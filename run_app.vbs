Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "pythonw app.py" & Chr(34), 0
Set WshShell = Nothing
