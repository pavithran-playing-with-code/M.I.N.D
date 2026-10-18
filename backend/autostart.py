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

# ---------- Desktop icons: "M.I.N.D ON" and "M.I.N.D OFF" ----------
def make_icon(path, color):
    # A little glowing orb, like the HUD's
    from PIL import Image, ImageDraw
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 248, 248), fill=(3, 7, 13, 255))
    draw.ellipse((30, 30, 226, 226), outline=color, width=14)
    draw.ellipse((88, 88, 168, 168), fill=color)
    img.save(path, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])

START_MENU = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs")

def start_menu_button():
    # One "M.I.N.D" button in the Start menu: click = on if it's off, off if it's on.
    # Windows doesn't let programs pin to the taskbar, so you pin it yourself:
    # Start menu -> type MIND -> right-click -> Pin to taskbar.
    icon = os.path.join(BACKEND, "icons", "mind.ico")
    os.makedirs(os.path.dirname(icon), exist_ok=True)
    make_icon(icon, (62, 224, 255, 255))
    shortcut = win32com.client.Dispatch("WScript.Shell").CreateShortCut(os.path.join(START_MENU, "M.I.N.D.lnk"))
    # Pointing at cmd.exe (not the .bat itself) is what makes it pinnable to the taskbar
    shortcut.TargetPath = os.path.join(os.environ["WINDIR"], "System32", "cmd.exe")
    shortcut.Arguments = f'/c "{os.path.join(BACKEND, "toggle_mind.bat")}"'
    shortcut.WorkingDirectory = BACKEND
    shortcut.WindowStyle = MINIMIZED
    shortcut.IconLocation = icon
    shortcut.Description = "Turn M.I.N.D on or off"
    shortcut.Save()
    print("Done! Press the Windows key, type MIND, right-click it and choose 'Pin to taskbar'.")

if __name__ == "__main__":
    choice = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if choice == "on":
        turn_on()
    elif choice == "off":
        turn_off()
    elif choice == "button":
        start_menu_button()
    else:
        print("Use:  python autostart.py on   or   off   or   button (Start menu on/off button)")
        print("Right now:", "ON" if os.path.exists(SHORTCUT) else "OFF")
