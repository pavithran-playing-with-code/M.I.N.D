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
    import overlay
    if overlay.running():
        # Jarvis mode is on: it IS the HUD (pictures too). Opening the normal one as well showed everything twice.
        overlay.start()  # (brings it forward)
        return
    windows = hud_windows()
    if windows:
        bring_to_front(windows[0])  # already open (maybe hidden behind other windows): show it
        return
    chrome = chrome_path()
    if chrome:
        # NOT Chrome's start-fullscreen switch: if Chrome wasn't running, the HUD's launch becomes ALL of Chrome,
        # and every window it opened afterwards (links from WhatsApp...) came up full screen (2026-10-29).
        import pc
        folder = pc.default_chrome_folder()  # the Chrome account set in Controls ("Open links in this Chrome")
        subprocess.Popen([chrome, f"--app={URL}"] + ([f"--profile-directory={folder}"] if folder else []))
        threading.Thread(target=big_when_open, daemon=True).start()
    else:
        webbrowser.open(URL)  # no Chrome: a normal tab in the default browser

def big_when_open():
    # The HUD window opens maximized: a normal window filling the screen (owner's choice: full screen
    # showed Chrome's "press Esc to exit full screen" popup every time)
    for _ in range(40):  # wait up to 10 s for it
        time.sleep(0.25)
        windows = hud_windows()
        if windows:
            win32gui.ShowWindow(windows[0], win32con.SW_MAXIMIZE)
            time.sleep(0.3)
            bring_to_front(windows[0])  # (a new Chrome window opened by M.I.N.D stayed behind the others)
            return

def close_hud():
    import floating
    import live_window
    floating.hide()  # the floating reactor too
    live_window.close_window()  # and M.I.N.D Live's hidden window
    import overlay
    overlay.stop()  # and the Jarvis-mode HUD app, if it's on
    for hwnd in hud_windows():
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

# ---------- One taskbar button (owner's ask, 2026-11-06) ----------
# The pinned M.I.N.D button does everything (button.py: click = HUD, double click = on/off), so the HUD window
# doesn't get a taskbar button of its own: Windows' ITaskbarList takes it off (Alt+Tab still shows it).
def taskbar_list():
    import comtypes
    import comtypes.client
    from comtypes import GUID, HRESULT, COMMETHOD
    from ctypes import c_int

    class ITaskbarList(comtypes.IUnknown):
        _iid_ = GUID("{56FDF342-FD6D-11d0-958A-006097C9A090}")
        _methods_ = [COMMETHOD([], HRESULT, "HrInit"),
                     COMMETHOD([], HRESULT, "AddTab", (["in"], c_int, "hwnd")),
                     COMMETHOD([], HRESULT, "DeleteTab", (["in"], c_int, "hwnd")),
                     COMMETHOD([], HRESULT, "ActivateTab", (["in"], c_int, "hwnd")),
                     COMMETHOD([], HRESULT, "SetActiveAlt", (["in"], c_int, "hwnd"))]
    comtypes.CoInitialize()
    tasks = comtypes.client.CreateObject(GUID("{56FDF344-FD6D-11d0-958A-006097C9A090}"), interface=ITaskbarList)
    tasks.HrInit()
    return tasks

def keep_off_taskbar():
    # Background thread: every 2 s, the HUD window(s) lose their own taskbar button (Chrome can add it back
    # when the window is shown again, so it keeps checking)
    try:
        tasks = taskbar_list()
    except Exception as error:
        print(f"(Couldn't reach the taskbar: {error})")
        return
    while True:
        for hwnd in hud_windows():
            try:
                tasks.DeleteTab(hwnd)
            except Exception:
                pass
        time.sleep(2)

def hud_button():
    # A single click on the taskbar button: the HUD comes up; if it's already in front, it's tucked away
    import floating
    import overlay
    windows = hud_windows()
    if overlay.running():
        open_hud()  # (Jarvis mode: brings it forward)
        return
    in_front = windows and (win32gui.GetForegroundWindow() in windows or any(
        not win32gui.IsIconic(w) and floating.hud_on_top(w) for w in windows))
    if in_front:
        for hwnd in windows:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    else:
        open_hud()
