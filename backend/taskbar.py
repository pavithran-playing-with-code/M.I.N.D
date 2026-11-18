# Taskbar: shows whether M.I.N.D is on or off on its pinned taskbar button
# (glowing cyan orb = on, grey orb = off). Run "python taskbar.py on|off" to set it by hand.
import os
import sys
import glob
import ctypes
import win32com.client

BACKEND = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(BACKEND, "icons")
ON_ICON = os.path.join(ICONS, "mind_on.ico")
OFF_ICON = os.path.join(ICONS, "mind_off.ico")
PLACES = [  # where M.I.N.D's button lives: the taskbar pin and the Start menu
    os.path.join(os.environ["APPDATA"], r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"),
    os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs"),
]

# M.I.N.D's app ID: on the pinned/Start menu shortcut AND on the HUD window, so Windows shows the open HUD
# INSIDE the M.I.N.D taskbar icon (hover = its preview, click = show / minimize it, like WhatsApp)
APP_ID = "VVP.MIND"

def give_app_id():
    # Puts the app ID on every M.I.N.D shortcut that doesn't have it yet (a re-made button gets it too).
    # The taskbar only notices on a pinned button after it's pinned again (or Explorer restarts).
    from win32com.propsys import propsys, pscon
    import pythoncom
    for path, _ in mind_buttons():
        try:
            store = propsys.SHGetPropertyStoreFromParsingName(path, None, 2)  # 2 = read and write
            if store.GetValue(pscon.PKEY_AppUserModel_ID).GetValue() != APP_ID:
                store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
                store.Commit()
        except Exception as e:
            print("Couldn't give the M.I.N.D button its app ID:", e)

def make_icons():
    # The on (glowing) and off (dark) button icons: M.I.N.D's one icon (icons.py)
    import icons
    icons.ensure()

def mind_buttons():
    # Every shortcut that runs toggle_mind.bat
    shell = win32com.client.Dispatch("WScript.Shell")
    for folder in PLACES:
        for path in glob.glob(os.path.join(folder, "*.lnk")):
            shortcut = shell.CreateShortCut(path)
            if "toggle_mind" in shortcut.Arguments:
                yield path, shortcut

def show(on):
    try:
        make_icons()
        give_app_id()
        icon = ON_ICON if on else OFF_ICON
        for path, shortcut in mind_buttons():
            if shortcut.IconLocation.split(",")[0] != icon:
                shortcut.IconLocation = icon
                shortcut.Save()
        # Tell Windows the icons changed, so the taskbar redraws them
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception as e:
        print("Couldn't update the taskbar icon:", e)

if __name__ == "__main__":
    on = len(sys.argv) > 1 and sys.argv[1].lower() == "on"
    show(on)
    if not on:
        import hud
        hud.close_hud()  # M.I.N.D was turned off: close its HUD window too
