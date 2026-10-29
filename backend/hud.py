# HUD window: opens M.I.N.D's HUD as its own app window (Chrome "app mode": no tabs,
# no address bar, like a desktop app), reuses it if it's already open, and closes it
# when M.I.N.D turns off. (A web page isn't allowed to close its own tab, but this is.)
import os
import time
import threading
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
        # NOT Chrome's start-fullscreen switch: if Chrome wasn't running, the HUD's launch becomes ALL of Chrome,
        # and every window it opened afterwards (links from WhatsApp...) came up full screen (2026-10-29).
        subprocess.Popen([chrome, f"--app={URL}"])
        threading.Thread(target=full_screen_when_open, daemon=True).start()
    else:
        webbrowser.open(URL)  # no Chrome: a normal tab in the default browser

def full_screen_when_open():
    # Only the HUD window goes full screen, like a Jarvis display (F11 leaves it)
    import ctypes
    for _ in range(40):  # wait up to 10 s for it
        time.sleep(0.25)
        windows = hud_windows()
        if windows:
            time.sleep(0.5)  # let the page appear first
            bring_to_front(windows[0])
            if win32gui.GetForegroundWindow() == windows[0]:
                ctypes.windll.user32.keybd_event(0x7A, 0, 0, 0)  # F11 down
                ctypes.windll.user32.keybd_event(0x7A, 0, 2, 0)  # F11 up
            return

def close_hud():
    import floating
    import live_window
    floating.hide()  # the floating reactor too
    live_window.close_window()  # and M.I.N.D Live's hidden window
    for hwnd in hud_windows():
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
