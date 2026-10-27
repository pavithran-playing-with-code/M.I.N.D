' Runs toggle_mind.bat with NO window: the taskbar button used to flash a black command window.
' (The taskbar M.I.N.D button points at wscript.exe with this file; see autostart.py button.)
' The full path is needed: on this PC cmd doesn't look in the current folder for scripts.
Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
shell.Run "cmd /c """ & folder & "\toggle_mind.bat""", 0, False
