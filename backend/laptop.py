# Everyday laptop things people ask for in one breath: screen brightness, screen off, sleep / shut down /
# restart, a screenshot, dark mode, a new folder, and the right page of Windows Settings.
# (Mind used to answer "I can't" to every one of these.)
import ctypes
import os
import re
import subprocess
import threading
import time

import state

HOME = os.path.expanduser("~")
STEP = 15  # "brighter" / "dimmer" = this many percent

def said(pattern):
    return bool(re.search(pattern, state.last_user_text or "", re.I))

# ---------- Brightness ----------
def brightness(action, value=None):
    import brightness as screen
    now = screen.get()
    if now is None:
        return "This screen's brightness can't be changed from here (an external monitor has its own buttons)."
    if action == "brightness":
        return f"Brightness is at {now} percent."
    try:
        asked = int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        asked = None
    if action == "brightness_set" and asked is not None:
        to = asked
    elif action == "brightness_up":
        to = now + (asked or STEP)
    else:
        to = now - (asked or STEP)
    to = max(0, min(100, to))
    screen.set(to)
    return f"Brightness is now {to} percent (it was {now})."

# ---------- Sleep, shut down, restart ----------
POWER_WORDS = {
    "sleep": r"sleep|hibernate|suspend",
    "shutdown": r"shut ?down|switch off|power off|turn off|turn it off",
    "restart": r"restart|reboot",
}
DELAY = 30  # seconds before a shut down / restart really happens ("Mind, cancel that" stops it)

def run_quietly(command):
    subprocess.run(command, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True, timeout=15)

def go_to_sleep():
    time.sleep(6)  # (time for Mind to say it first)
    ctypes.windll.powrprof.SetSuspendState(0, 0, 0)

def power(action):
    # Only when THEIR OWN words ask for it (a guess by the brain must never turn the laptop off),
    # and never when they're talking about Mind itself ("restart yourself", "turn yourself off")
    if said(r"yourself|your ?self") and not said(r"laptop|computer|pc|system"):
        return "Not done: that sounds like it's about Mind itself, not the laptop (restart_mind / end_talk)."
    if not said(POWER_WORDS[action]):
        return f"Not done: only when they clearly ask to {action} the laptop."
    if action == "sleep":
        threading.Thread(target=go_to_sleep, daemon=True).start()
        return "Going to sleep in a few seconds. Say just that, briefly."
    run_quietly(["shutdown", "/s" if action == "shutdown" else "/r", "/t", str(DELAY)])
    doing = "Shutting down" if action == "shutdown" else "Restarting"
    return (f"{doing} in {DELAY} seconds. Tell them that, and that 'Mind, cancel that' stops it "
            "(unsaved work should be saved now).")

def cancel_power():
    run_quietly(["shutdown", "/a"])
    return "Cancelled: the laptop stays on."

# ---------- Dark / light mode ----------
def colour_mode(dark):
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                         0, winreg.KEY_SET_VALUE)
    for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 0 if dark else 1)
    winreg.CloseKey(key)
    # Tell open apps the colours changed
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 2000, None)
    return f"Windows is in {'dark' if dark else 'light'} mode now."

# ---------- Screenshot ----------
def screenshot(where=""):
    import chores
    picture, _ = chores.grab("window" if str(where).lower() in ("window", "this window", "app") else "screen")
    folder = os.path.join(place("pictures") or os.path.join(HOME, "Pictures"), "Screenshots")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, time.strftime("Mind %Y-%m-%d %H.%M.%S.png"))
    picture.save(path)
    try:
        chores.picture_to_clipboard(picture)
        copied = " and copied (Ctrl+V pastes it)"
    except Exception:
        copied = ""
    return f"Screenshot saved in Pictures\\Screenshots{copied}."

# ---------- A new folder ----------
PLACES = {"desktop": "Desktop", "documents": "Documents", "downloads": "Downloads", "pictures": "Pictures",
          "videos": "Videos", "music": "Music"}

def place(name):
    # The real folder for "desktop", "documents"... (Windows often keeps Desktop/Documents inside OneDrive)
    folder = PLACES.get(str(name).lower().strip().removeprefix("my ").removesuffix(" folder"))
    if not folder:
        return None
    for base in (os.path.join(HOME, "OneDrive"), HOME):
        if os.path.isdir(os.path.join(base, folder)):
            return os.path.join(base, folder)
    return None

def new_folder(name, where=""):
    name = re.sub(r'[<>:"/\\|?*]', "", str(name or "")).strip(" .")
    if not name:
        return "Not made: ask what to call the folder."
    base = place(where or "desktop") or place("desktop") or HOME
    path = os.path.join(base, name)
    if os.path.exists(path):
        return f"There's already a folder called {name} in {os.path.basename(base)}."
    os.mkdir(path)
    os.startfile(path)
    return f"Made the folder {name} in {os.path.basename(base)} and opened it."

# ---------- Windows Settings pages ----------
# Windows doesn't let a program flip Bluetooth / Wi-Fi / night light without extra rights, so Mind opens the
# exact page where the switch is (one click from there).
PAGES = [
    (r"bluetooth|earbud|earphone|headphone|headset|pair|device", "bluetooth", "Bluetooth & devices"),
    (r"wi-?fi|wireless", "network-wifi", "Wi-Fi"),
    (r"air ?plane|flight", "network-airplanemode", "Airplane mode"),
    (r"hotspot", "network-mobilehotspot", "Mobile hotspot"),
    (r"vpn", "network-vpn", "VPN"),
    (r"network|internet|ethernet", "network-status", "Network & internet"),
    (r"night ?light|blue light", "nightlight", "Night light"),
    (r"battery|power saver|energy", "batterysaver", "Battery"),
    (r"update", "windowsupdate", "Windows Update"),
    (r"storage|disk|space|clean", "storagesense", "Storage"),
    (r"notification|focus|do not disturb", "notifications", "Notifications"),
    (r"sound|speaker|microphone|mic|audio", "sound", "Sound"),
    (r"display|resolution|scale|monitor|screen", "display", "Display"),
    (r"wallpaper|background", "personalization-background", "Background"),
    (r"theme|colou?r|personal", "personalization", "Personalization"),
    (r"lock screen", "lockscreen", "Lock screen"),
    (r"default app", "defaultapps", "Default apps"),
    (r"startup", "startupapps", "Startup apps"),
    (r"app|uninstall|program", "appsfeatures", "Installed apps"),
    (r"account|password|sign.?in|pin|fingerprint", "signinoptions", "Sign-in options"),
    (r"time|date|clock", "dateandtime", "Date & time"),
    (r"language|keyboard|typing", "regionlanguage", "Language"),
    (r"mouse|touchpad|cursor", "mousetouchpad", "Mouse"),
    (r"printer|scanner", "printers", "Printers & scanners"),
    (r"camera|privacy|location|permission", "privacy", "Privacy"),
    (r"about|spec|version|system", "about", "About"),
]

def settings_page(what=""):
    for words, page, name in PAGES:
        if re.search(words, str(what), re.I):
            os.startfile("ms-settings:" + page)
            return (f"Opened Windows Settings on {name}: the switch is right there (Windows doesn't let an app flip "
                    "it for them). Say that in a few words.")
    os.startfile("ms-settings:")
    return "Opened Windows Settings."

# ---------- The tool ----------
def laptop(action, value="", where=""):
    action = str(action or "").lower().strip()
    try:
        if action.startswith("brightness"):
            return brightness(action, value)
        if action == "screen_off":
            import phone
            return phone.screen_off()
        if action in POWER_WORDS:
            return power(action)
        if action == "cancel_power":
            return cancel_power()
        if action in ("dark_mode", "light_mode"):
            return colour_mode(action == "dark_mode")
        if action == "screenshot":
            return screenshot(value or where)
        if action == "new_folder":
            return new_folder(value, where)
        if action == "settings":
            return settings_page(value)
    except Exception as e:
        return f"That didn't work ({str(e)[:80]})."
    return "Unknown action. Use one of: brightness_up, brightness_down, brightness_set, screen_off, sleep, shutdown, restart, cancel_power, dark_mode, light_mode, screenshot, new_folder, settings."
