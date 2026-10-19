# HUD window: opens M.I.N.D's HUD as its own app window (Chrome "app mode": no tabs,
# no address bar, like a desktop app), reuses it if it's already open, and closes it
# when M.I.N.D turns off. (A web page isn't allowed to close its own tab, but this is.)
import os
import subprocess
import webbrowser
import winreg
import win32gui
import win32con

URL = "http://localhost:8000"
TITLE = "M.I.N.D"  # the HUD page's title: an app window shows exactly this (a tab adds " - Google Chrome")

def chrome_path():
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            path = winreg.QueryValue(key, None)
            if os.path.exists(path):
                return path
        except OSError:
            pass
    return None

def hud_windows():
    found = []
    def check(hwnd, _):
        if (win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == TITLE
                and win32gui.GetClassName(hwnd).startswith("Chrome_WidgetWin")):
            found.append(hwnd)
    win32gui.EnumWindows(check, None)
    return found

def bring_to_front(hwnd):
    # Windows only lets a program bring a window forward right after a key press, so tap Alt first
    import ctypes
    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)  # it was minimized
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass

def open_hud():
    windows = hud_windows()
    if windows:
        bring_to_front(windows[0])  # already open (maybe hidden behind other windows): show it
        return
    chrome = chrome_path()
    if chrome:
        # Full screen like a Jarvis display (press F11 to leave full screen)
        subprocess.Popen([chrome, f"--app={URL}", "--start-fullscreen"])
    else:
        webbrowser.open(URL)  # no Chrome: a normal tab in the default browser

def close_hud():
    for hwnd in hud_windows() + mini_windows():
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

# ---------- Floating window: small, always on top, in a corner ----------
MINI_TITLE = "M.I.N.D mini"
MINI_SIZE = (400, 170)  # includes Chrome's small title bar (drag it there with the mouse)
# Its own Chrome profile, so it doesn't copy the HUD's full-screen size
MINI_PROFILE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "MIND", "floating-window")
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")

def mini_windows():
    found = []
    def check(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == MINI_TITLE:
            found.append(hwnd)
    win32gui.EnumWindows(check, None)
    return found

def work_area():
    # The screen without the taskbar: (left, top, right, bottom)
    import ctypes
    from ctypes import wintypes
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom

def place_mini(hwnd, corner):
    left, top, right, bottom = work_area()
    w, h = MINI_SIZE
    x = left + 12 if "left" in corner else right - w - 12
    y = top + 12 if "top" in corner else bottom - h - 12
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)  # not maximized / full screen
    # Small, in the corner, and always on top of other windows
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, x, y, w, h, win32con.SWP_SHOWWINDOW)

def floating_window(action="show", position=""):
    # Show / hide / move the floating window. Remembers the choice in profile.json.
    import time
    from memory import profile, save_profile
    corner = position if position in CORNERS else profile.get("floating_position", "bottom-right")
    if action == "hide":
        for hwnd in mini_windows():
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        profile["floating"] = False
        save_profile()
        return "Floating window hidden."
    windows = mini_windows()
    if not windows:
        chrome = chrome_path()
        if not chrome:
            return "The floating window needs Google Chrome."
        subprocess.Popen([chrome, f"--app={URL}/?mini", f"--window-size={MINI_SIZE[0]},{MINI_SIZE[1]}",
                          f"--user-data-dir={MINI_PROFILE}", "--no-first-run", "--no-default-browser-check"])
        for _ in range(30):  # wait up to 9 seconds for it to appear
            time.sleep(0.3)
            windows = mini_windows()
            if windows:
                break
    if not windows:
        return "Couldn't open the floating window."
    place_mini(windows[0], corner)
    profile.update(floating=True, floating_position=corner)
    save_profile()
    return f"Floating window {'moved to' if action == 'move' else 'shown at'} the {corner.replace('-', ' ')}."
