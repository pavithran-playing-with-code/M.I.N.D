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
    shortcut.TargetPath = os.path.join(BACKEND, "venv", "Scripts", "pythonw.exe")  # no window
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

# ---------- The taskbar on/off button ----------
START_MENU = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs")

def start_menu_button():
    # One "M.I.N.D" button in the Start menu: click = on if it's off, off if it's on.
    # Windows doesn't let programs pin to the taskbar, so you pin it yourself:
    # Start menu -> type MIND -> right-click -> Pin to taskbar.
    import taskbar
    taskbar.make_icons()  # (the same glowing orb the button shows while M.I.N.D is on)
    icon = taskbar.ON_ICON
    shortcut = win32com.client.Dispatch("WScript.Shell").CreateShortCut(os.path.join(START_MENU, "M.I.N.D.lnk"))
    hidden_launcher(shortcut)
    shortcut.IconLocation = icon
    shortcut.Description = "Turn M.I.N.D on or off"
    shortcut.Save()
    print("Done! Press the Windows key, type MIND, right-click it and choose 'Pin to taskbar'.")

def hidden_launcher(shortcut):
    # wscript.exe + toggle_mind.vbs runs the on/off script with NO window (cmd.exe flashed a black
    # window on every click). An .exe target is also what makes it pinnable to the taskbar.
    shortcut.TargetPath = os.path.join(os.environ["WINDIR"], "System32", "wscript.exe")
    shortcut.Arguments = f'"{os.path.join(BACKEND, "toggle_mind.vbs")}"'
    shortcut.WorkingDirectory = BACKEND

def hide_button_windows():
    # Switch the existing buttons (Start menu and the one pinned to the taskbar) to the hidden launcher
    import taskbar
    for path, shortcut in taskbar.mind_buttons():
        hidden_launcher(shortcut)
        shortcut.Save()
        print("Updated", path)

if __name__ == "__main__":
    choice = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if choice == "on":
        turn_on()
    elif choice == "off":
        turn_off()
    elif choice == "button":
        start_menu_button()
    elif choice == "hide":
        hide_button_windows()
    else:
        print("Use:  python autostart.py on   or   off   or   button (Start menu on/off button)   or   hide (no black window on click)")
        print("Right now:", "ON" if os.path.exists(SHORTCUT) else "OFF")
