' The taskbar M.I.N.D button: runs button.py with NO window (single click = HUD, double click = on/off).
' (The button points at wscript.exe with this file; see autostart.py button. The name stays toggle_mind.vbs
' so pinned buttons keep working and taskbar.py still finds them.)
Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
shell.Run """" & folder & "\venv\Scripts\pythonw.exe"" """ & folder & "\button.py""", 0, False
