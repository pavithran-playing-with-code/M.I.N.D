# Autostart: make M.I.N.D start by itself when you log in to Windows.
# Run from the backend folder (with the venv active):
#   python autostart.py on    -> start with Windows
#   python autostart.py off   -> stop starting with Windows
# It just puts a shortcut in Windows' Startup folder (open it with Win+R, then shell:startup).
import os
import sys
import win32com.client

BACKEND = os.path.dirname(os.path.abspath(__file__))
STARTUP = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
SHORTCUT = os.path.join(STARTUP, "M.I.N.D.lnk")
MINIMIZED = 7  # start the window minimized, so it doesn't pop up in your face

def turn_on():
    shortcut = win32com.client.Dispatch("WScript.Shell").CreateShortCut(SHORTCUT)
    shortcut.TargetPath = os.path.join(BACKEND, "venv", "Scripts", "python.exe")
    shortcut.Arguments = "main.py"
    shortcut.WorkingDirectory = BACKEND
    shortcut.WindowStyle = MINIMIZED
    shortcut.Description = "Start M.I.N.D"
    shortcut.Save()
    print("Done! M.I.N.D will start by itself when you log in to Windows.")

def turn_off():
    if os.path.exists(SHORTCUT):
        os.remove(SHORTCUT)
        print("Done! M.I.N.D won't start with Windows anymore.")
    else:
        print("M.I.N.D wasn't set to start with Windows.")

if __name__ == "__main__":
    choice = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if choice == "on":
        turn_on()
    elif choice == "off":
        turn_off()
    else:
        print("Use:  python autostart.py on   or   python autostart.py off")
        print("Right now:", "ON" if os.path.exists(SHORTCUT) else "OFF")
