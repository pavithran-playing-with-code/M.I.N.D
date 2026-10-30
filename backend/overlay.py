# Jarvis mode: the see-through desktop HUD (the Electron app in ../desktop). It only runs while it's on,
# so it uses no memory when it's off. "Mind, Jarvis mode" / "Jarvis mode off", or Ctrl+Alt+M to hide/show.
# Also: what the overlay's Windows panel asks for (bring a window forward, minimize, maximize, close).
import os
import subprocess
import psutil
import win32con
import win32gui
from memory import BASE_DIR

ROOT = os.path.dirname(BASE_DIR)
ELECTRON = os.path.join(ROOT, "node_modules", "electron", "dist", "electron.exe")
APP = os.path.join(ROOT, "desktop", "main.cjs")

def processes():
    # The overlay's processes (Electron runs a few), found by its script in the command line
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
    # The normal HUD window and the floating reactor step aside (both at once showed two cores and two
    # conversations on top of each other, and the reactor covered the overlay's Send button)
    import hud
    import floating
    for hwnd in hud.hud_windows():
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    floating.hide()
    # (if it's already running, a second start just shows it again: the app allows only one copy)
    # (ELECTRON_RUN_AS_NODE, set when M.I.N.D was started from VS Code, makes Electron a plain Node: no window)
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}
    subprocess.Popen([ELECTRON, APP], cwd=ROOT, env=env)
    return "Jarvis mode is on: the HUD floats over your desktop. Ctrl+Alt+M hides or shows it."

def stop(bring_back=True):
    # bring_back: the floating reactor comes back (not when M.I.N.D itself is turning off)
    was_on = running()
    for p in processes():
        try:
            for child in p.children(recursive=True):
                child.kill()
            p.kill()
        except psutil.Error:
            pass
    if was_on and bring_back:
        import floating
        from memory import profile
        floating.show(profile.get("floating_position", "bottom-right"), profile.get("floating_offset", (0, 0)))
    return "Jarvis mode is off."

def jarvis_mode(on=True):
    # Tool: "Mind, Jarvis mode" / "turn off Jarvis mode"
    return start() if on in (True, "true", "yes", "on") else stop()

MIND_TITLES = {"M.I.N.D", "M.I.N.D mini", "M.I.N.D Live", "M.I.N.D overlay"}

def window_act(handle, action):
    # The overlay's Windows panel: focus / minimize / maximize / close one window (never M.I.N.D's own)
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
