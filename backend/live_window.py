# The hidden M.I.N.D Live window: a small Chrome window of M.I.N.D's own that holds the live page
# (live.html?auto=1), so you can just say "Mind" any time with no page to open and no tap.
#
# It's a SEPARATE Chrome (its own settings folder, backend/live_chrome), because only a separate
# Chrome accepts these settings: microphone allowed without a popup, sound allowed without a click,
# and never slowed down while minimized. Chrome's echo removal then keeps it from hearing itself.
import os
import time
import subprocess
import threading
import psutil
import win32gui
import win32con
import hud
from memory import BASE_DIR

URL = "http://localhost:8000/live?auto=1"
FOLDER = os.path.join(BASE_DIR, "live_chrome")  # its own Chrome settings (git-ignored)
TITLE = "M.I.N.D Live"

def processes():
    # The Chrome processes of M.I.N.D's own live window (found by its settings folder)
    found = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() == "chrome.exe" and FOLDER in " ".join(p.info["cmdline"] or []):
                found.append(p)
        except psutil.Error:
            pass
    return found

def windows():
    pids = {p.pid for p in processes()}
    found = []
    def check(hwnd, _):
        import win32process
        if win32process.GetWindowThreadProcessId(hwnd)[1] in pids and win32gui.GetWindowText(hwnd).startswith(TITLE):
            found.append(hwnd)
    win32gui.EnumWindows(check, None)
    return found

def open_window():
    # Starts the hidden live window (if it isn't running already) and minimizes it
    if processes():
        return
    chrome = hud.chrome_path()
    if not chrome:
        print("No Chrome: M.I.N.D Live needs Chrome")
        return
    subprocess.Popen([chrome, f"--user-data-dir={FOLDER}", f"--app={URL}", "--no-first-run",
                      "--no-default-browser-check", "--window-size=420,520",
                      "--use-fake-ui-for-media-stream",              # allow the mic without a popup
                      "--autoplay-policy=no-user-gesture-required",  # allow its voice without a click
                      "--disable-background-timer-throttling",       # keep working while minimized
                      "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
                      # a voice page needs none of Chrome's extras (the laptop has 8 GB and little free):
                      # no graphics card process, extensions, sync, updates, translate or background helpers
                      "--disable-gpu", "--disable-extensions", "--disable-sync", "--disable-component-update",
                      "--disable-background-networking", "--disable-default-apps", "--no-pings",
                      "--disable-features=Translate,OptimizationHints,MediaRouter,AutofillServerCommunication",
                      "--renderer-process-limit=1", "--js-flags=--max-old-space-size=64"])
    def minimize():
        for _ in range(40):  # wait up to 10 s for the window, then tuck it away
            time.sleep(0.25)
            found = windows()
            if found:
                for hwnd in found:
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                return
    threading.Thread(target=minimize, daemon=True).start()

closing = {"now": False}  # M.I.N.D is turning off: don't bring the window back

def keep_open():
    # If the hidden window gets closed (Chrome "Exit" closed it once, and the old brain answered
    # instead of Live), open it again within a few seconds. Runs in the background.
    def check():
        while not closing["now"]:
            time.sleep(10)
            if not closing["now"] and not processes():
                print("(M.I.N.D Live's window was closed, opening it again)")
                open_window()
    threading.Thread(target=check, daemon=True).start()

def close_window():
    closing["now"] = True
    for p in processes():
        try:
            p.terminate()
        except psutil.Error:
            pass
