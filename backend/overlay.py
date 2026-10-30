# Jarvis mode: the HUD as its own desktop app (the Electron app in ../desktop) that can show any of your windows
# or screens LIVE inside the HUD, in full quality ("Mind, show my VS Code in the HUD"). It only runs while it's
# on, so it uses no memory when it's off. Ctrl+Alt+M brings it forward / tucks it away.
# Also: what the HUD's buttons ask for (bring a window forward, minimize, maximize, close).
import os
import time
import subprocess
import psutil
import win32con
import win32gui
import state
from memory import BASE_DIR

ROOT = os.path.dirname(BASE_DIR)
ELECTRON = os.path.join(ROOT, "node_modules", "electron", "dist", "electron.exe")
APP = os.path.join(ROOT, "desktop", "main.cjs")
TITLE = "M.I.N.D Jarvis"

def processes():
    # The Jarvis app's processes (Electron runs a few), found by its script in the command line
    found = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() == "electron.exe" and any("main.cjs" in a for a in p.info["cmdline"] or []):
                found.append(p)
        except psutil.Error:
            pass
    return found

def running():
    return bool(processes())

def start():
    if not os.path.exists(ELECTRON):
        return "Jarvis mode isn't installed (run npm install in the M.I.N.D folder)."
    # The normal HUD window closes: Jarvis mode IS the HUD now (two HUDs showed everything twice)
    import hud
    for hwnd in hud.hud_windows():
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    # (if it's already running, a second start just brings it forward: the app allows only one copy)
    # (ELECTRON_RUN_AS_NODE, set when M.I.N.D was started from VS Code, makes Electron a plain Node: no window)
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}
    subprocess.Popen([ELECTRON, APP], cwd=ROOT, env=env)
    import threading
    threading.Thread(target=to_front, daemon=True).start()
    return "Jarvis mode is on: the HUD can show any of your windows live (Ctrl+Alt+M brings it forward)."

def to_front():
    # Windows doesn't let a newly opened app jump in front by itself (it only flashed on the taskbar,
    # behind VS Code), so M.I.N.D brings it forward once it's there
    import pc
    for _ in range(40):
        time.sleep(0.5)
        hwnd = win32gui.FindWindow(None, TITLE)
        if hwnd and win32gui.IsWindowVisible(hwnd):
            time.sleep(0.8)
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            pc.bring_to_front(hwnd)
            return

def stop():
    for p in processes():
        try:
            for child in p.children(recursive=True):
                child.kill()
            p.kill()
        except psutil.Error:
            pass
    return "Jarvis mode is off."

def jarvis_mode(on=True, show="", close_view=False):
    # Tool: "Mind, Jarvis mode" / "turn off Jarvis mode" / "show my VS Code in the HUD" / "close the live view"
    if close_view in (True, "true", "yes"):
        return show_screen(close=True)
    if show:
        return show_screen(show)
    return start() if on in (True, "true", "yes", "on") else stop()

def show_screen(name="", close=False):
    # Tool: "show my VS Code in the HUD" / "show my screen" / "close the screen view". Opens Jarvis mode if
    # needed, asks the HUD to show it live, and waits for the HUD's answer (so it never claims what isn't true)
    if not running():
        start()
        for _ in range(40):  # (the app takes a few seconds to open)
            time.sleep(0.5)
            if win32gui.FindWindow(None, TITLE):
                break
        time.sleep(3)
    ask = int(time.time() * 1000)
    state.screen_view = {"id": ask, "close": True} if close in (True, "true", "yes") else {"id": ask, "name": name or "screen"}
    for _ in range(60):  # wait up to 6 s for the HUD
        time.sleep(0.1)
        answer = state.screen_result
        if answer.get("id") == ask:
            if answer["shown"] == "closed":
                return "Closed the live view."
            if answer["shown"]:
                return f"Showing '{answer['shown']}' live in the HUD."
            return f"Nothing open matches '{name}'. Open now: " + "; ".join(answer.get("open", [])[:10])
    return "The Jarvis HUD didn't answer (it may still be opening). Say so."

MIND_TITLES = {"M.I.N.D", "M.I.N.D mini", "M.I.N.D Live", TITLE}

def window_act(handle, action):
    # The HUD's buttons: focus / minimize / maximize / close one window (never M.I.N.D's own)
    import pc
    if not handle or not win32gui.IsWindow(handle):
        return "That window is gone."
    title = win32gui.GetWindowText(handle)
    if title in MIND_TITLES and action == "close":
        return "Not closing M.I.N.D's own window."
    if action == "focus":
        if win32gui.IsIconic(handle):
            win32gui.ShowWindow(handle, win32con.SW_RESTORE)
        pc.bring_to_front(handle)
    elif action == "minimize":
        win32gui.ShowWindow(handle, win32con.SW_MINIMIZE)
    elif action == "maximize":
        placement = win32gui.GetWindowPlacement(handle)[1]
        win32gui.ShowWindow(handle, win32con.SW_RESTORE if placement == win32con.SW_SHOWMAXIMIZED else win32con.SW_MAXIMIZE)
    elif action == "close":
        win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
    else:
        return "Unknown action."
    return f"{action}: {title[:60]}"
