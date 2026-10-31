# Jarvis mode: the HUD as its own desktop app (the Electron app in ../desktop) with any of your REAL windows working
# inside it ("Mind, show my VS Code in the HUD"). Nothing is filmed: the HUD cuts a hole in itself and the real
# window sits exactly in the hole, so there's no lag, and your own mouse and keyboard just work in it.
# It only runs while it's on, so it uses no memory when it's off. Ctrl+Alt+M brings it forward / tucks it away.
# Also: what the HUD's buttons ask for (bring a window forward, minimize, maximize, close).
import ctypes
import io
import json
import os
import time
import threading
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
    import calls
    if calls.in_call():
        return "Not opened: they're on a call, and Jarvis mode would take over the screen. Tell them it can wait till the call ends."
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
    return "Jarvis mode is on: any of your windows can work inside the HUD (Ctrl+Alt+M brings it forward)."

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
    release()
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
    # It takes over the whole screen, so it only opens if they really asked (it once opened on a "Mhm" during a call).
    turning_on = on in (True, "true", "yes", "on") and close_view not in (True, "true", "yes") and not running()
    if turning_on and not asked_for_jarvis():
        asked_jarvis["at"] = time.time()
        return "NOT opened: I didn't clearly hear them ask. Ask just \"Jarvis mode?\" and only call this again if they say yes."
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
                return f"'{answer['shown']}' is working inside the HUD now."
            return f"Nothing open matches '{name}'. Open now: " + "; ".join(answer.get("open", [])[:10])
    return "The Jarvis HUD didn't answer (it may still be opening). Say so."

asked_jarvis = {"at": 0.0}
JARVIS_WORDS = ("jarvis", "jar is", "travis", "service mode", "in the hud", "inside the hud", "on the hud")
YES_WORDS = ("yes", "yeah", "yep", "ok", "okay", "sure", "go ahead", "do it", "ஆமா", "சரி")

def asked_for_jarvis():
    said = (state.last_user_text or "").lower()
    if any(word in said for word in JARVIS_WORDS):
        return True
    return time.time() - asked_jarvis["at"] < 60 and any(word in said for word in YES_WORDS)

MIND_TITLES = {"M.I.N.D", "M.I.N.D mini", "M.I.N.D Live", TITLE}
NOT_WINDOWS = MIND_TITLES | {"Windows Input Experience", "Program Manager", "Settings", "Microsoft Text Input Application"}

# ---------- The window in the hole ----------
embedded = {"handle": None, "placement": None, "rect": None}
LEFT_BEHIND = os.path.join(BASE_DIR, "embedded.json")  # (if M.I.N.D stops suddenly, the next start puts the window back)

def embed(handle, x, y, width, height, tab=""):
    # Puts the real window exactly in the HUD's hole, right under the HUD, and remembers where it was
    import pc
    if not handle or not win32gui.IsWindow(handle) or win32gui.GetWindowText(handle) in MIND_TITLES:
        return "That window is gone."
    first = embedded["handle"] != handle
    if first:
        release()
        embedded.update(handle=handle, placement=win32gui.GetWindowPlacement(handle))
        remember_embedded()
        keep_watch()
    if win32gui.IsIconic(handle) or win32gui.GetWindowPlacement(handle)[1] == win32con.SW_SHOWMAXIMIZED:
        win32gui.ShowWindow(handle, win32con.SW_RESTORE)
    if tab:
        pc.show_tab(handle, tab)
    hud = win32gui.FindWindow(None, TITLE)
    try:
        win32gui.SetWindowPos(handle, hud or win32con.HWND_TOP, int(x), int(y), int(width), int(height), win32con.SWP_NOACTIVATE)
    except win32gui.error:  # (it closed just now, or the HUD did)
        return "That window is gone."
    embedded["rect"] = win32gui.GetWindowRect(handle)  # (where it really went: some windows have a minimum size)
    if first or tab:
        pc.bring_to_front(handle)  # (so you can type in it right away)
    return win32gui.GetWindowText(handle)

def raise_embedded():
    # The HUD was clicked: the window goes straight under it again (another app may have come between them)
    handle = embedded["handle"]
    hud = win32gui.FindWindow(None, TITLE)
    if handle and hud and win32gui.IsWindow(handle):
        try:
            win32gui.SetWindowPos(handle, hud, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        except win32gui.error:
            pass  # (the HUD or the window closed just now: nothing to line up)

def release():
    # The window goes back to exactly where and how it was
    handle, placement = embedded["handle"], embedded["placement"]
    embedded.update(handle=None, placement=None, rect=None)
    remember_embedded()
    if handle and win32gui.IsWindow(handle):
        put_back(handle, placement)

def put_back(handle, placement):
    try:
        win32gui.SetWindowPlacement(handle, placement)
        # Make it draw itself again (VS Code and Chrome can stay blank after being covered by the HUD)
        win32gui.SetWindowPos(handle, 0, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                              | win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED)
        win32gui.RedrawWindow(handle, None, None, win32con.RDW_INVALIDATE | win32con.RDW_ALLCHILDREN | win32con.RDW_UPDATENOW | win32con.RDW_FRAME)
    except Exception as e:
        print("Couldn't put the window back:", e)

def remember_embedded():
    try:
        if embedded["handle"]:
            with open(LEFT_BEHIND, "w", encoding="utf-8") as f:
                json.dump({"handle": embedded["handle"], "placement": embedded["placement"]}, f)
        elif os.path.exists(LEFT_BEHIND):
            os.remove(LEFT_BEHIND)
    except OSError as e:
        print("Couldn't note the window in the HUD:", e)

def restore_left_behind():
    # At start: a window that was in the HUD when M.I.N.D stopped goes back where it was
    try:
        with open(LEFT_BEHIND, encoding="utf-8") as f:
            left = json.load(f)
        os.remove(LEFT_BEHIND)
    except (OSError, ValueError):
        return
    if win32gui.IsWindow(left["handle"]):
        p = left["placement"]
        put_back(left["handle"], (p[0], p[1], tuple(p[2]), tuple(p[3]), tuple(p[4])))
        print("(Put a window back that was still in the Jarvis HUD)")

# The window in the HUD is still YOURS. Every second: if the HUD went away, it goes back; if you maximized it, moved it
# or minimized it yourself, the HUD lets go at once and never pulls it back (it used to feel stuck).
watching = {"on": False}

def keep_watch():
    if not watching["on"]:
        watching["on"] = True
        threading.Thread(target=watch_embedded, daemon=True).start()

def watch_embedded():
    while embedded["handle"]:
        time.sleep(1)
        handle = embedded["handle"]
        rect = embedded["rect"]
        if not handle:
            break
        if not win32gui.IsWindow(handle):
            embedded.update(handle=None, placement=None, rect=None)
            remember_embedded()
            break
        hud = win32gui.FindWindow(None, TITLE)
        if not hud or not win32gui.IsWindowVisible(hud):
            print("(The Jarvis HUD went away: the window goes back)")
            release()
            break
        if rect and handle == embedded["handle"] and embedded["rect"] == rect:
            now = win32gui.GetWindowRect(handle)
            moved = any(abs(a - b) > 10 for a, b in zip(now, rect))
            if moved or win32gui.IsIconic(handle) or win32gui.GetWindowPlacement(handle)[1] == win32con.SW_SHOWMAXIMIZED:
                print("(You took the window out of the HUD: it stays where you put it)")
                embedded.update(handle=None, placement=None, rect=None)
                remember_embedded()
                state.screen_view = {"id": int(time.time() * 1000), "close": True}  # (the HUD closes its hole)
                break
    watching["on"] = False

# ---------- What's open: every window, even minimized, and every browser tab ----------
tabs_cache = {"at": 0.0, "tabs": {}}

def is_cloaked(handle):
    # Windows' hidden helper windows look visible, but are "cloaked"
    cloaked = ctypes.c_int(0)
    ctypes.windll.dwmapi.DwmGetWindowAttribute(handle, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return bool(cloaked.value)

def refresh_tabs():
    import pc
    found = {}
    try:
        for hwnd, _, name in pc.browser_tabs():
            found.setdefault(hwnd, []).append(name)
    except Exception as e:
        print("Couldn't read the browser tabs:", str(e)[:100])
    tabs_cache.update(tabs=found, at=time.time(), busy=False)

def open_list():
    import pc
    if time.time() - tabs_cache["at"] > 8 and not tabs_cache.get("busy"):
        tabs_cache["busy"] = True
        threading.Thread(target=refresh_tabs, daemon=True).start()  # (takes ~0.5 s: never makes the HUD wait)
    found = []
    for hwnd, _, app, title in pc.open_windows():
        if title in NOT_WINDOWS or is_cloaked(hwnd):
            continue
        minimized = bool(win32gui.IsIconic(hwnd))
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if not minimized and hwnd != embedded["handle"] and (right - left < 120 or bottom - top < 80):
            continue
        found.append({"handle": hwnd, "title": title, "app": app, "minimized": minimized, "tabs": tabs_cache["tabs"].get(hwnd, [])})
    return found

def picture(handle):
    # A small picture of a window, even one that's behind others (a minimized one has none)
    import win32ui
    from PIL import Image
    if not win32gui.IsWindow(handle) or win32gui.IsIconic(handle):
        return None
    left, top, right, bottom = win32gui.GetWindowRect(handle)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None
    window_dc = win32gui.GetWindowDC(handle)
    source = win32ui.CreateDCFromHandle(window_dc)
    target = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(source, width, height)
    target.SelectObject(bitmap)
    try:
        # 2 = also what Chrome draws with the graphics card. It makes the app redraw, so it's done rarely, never on a stuck one
        if ctypes.windll.user32.IsHungAppWindow(handle):
            return None
        ctypes.windll.user32.PrintWindow(handle, target.GetSafeHdc(), 2)
        info = bitmap.GetInfo()
        image = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
        image.thumbnail((360, 220))
        out = io.BytesIO()
        image.save(out, "JPEG", quality=70)
        return out.getvalue()
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        target.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(handle, window_dc)

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
