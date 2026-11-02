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
        return "NOT opened: I didn't clearly hear them ask. Ask just \"Jarvis mode?\" once (not again if you already did) and only call this again if they say yes."
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
JARVIS_WORDS = ("jarvis", "jar is", "jaro", "travis", "service mode", "in the hud", "inside the hud", "on the hud")
YES_WORDS = ("yes", "yeah", "yep", "ok", "okay", "sure", "go ahead", "do it", "ஆமா", "சரி")
EARS_COUNT_FOR = 20  # seconds: what the wake-up ears heard still counts as what they asked

def asked_for_jarvis():
    said = (state.last_user_text or "").lower()
    # (Live and the wake-up ears can hear it differently: "Mind, Jarvis mode" came out as "Mind Jaro Smart" in Live)
    if time.time() - state.ears_heard_at < EARS_COUNT_FOR:
        said += " " + state.ears_heard.lower()
    if any(word in said for word in JARVIS_WORDS):
        return True
    return time.time() - asked_jarvis["at"] < 60 and any(word in said for word in YES_WORDS)

MIND_TITLES = {"M.I.N.D", "M.I.N.D mini", "M.I.N.D Live", TITLE}
NOT_WINDOWS = MIND_TITLES | {"Windows Input Experience", "Program Manager", "Settings", "Microsoft Text Input Application"}

# ---------- The window in the hole ----------
# handle -> {"placement": its own place, "rect": its place in the HUD, "out": you went to it from another app, so it's
# at its own place right now}. The size and spot in the HUD only ever apply inside the HUD.
embedded = {"windows": {}, "waiting": False}
LEFT_BEHIND = os.path.join(BASE_DIR, "embedded.json")  # (if M.I.N.D stops suddenly, the next start puts them back)

# One at a time: two requests moving the same window at once left Chrome "maximized" at the wrong place and size
moving = threading.RLock()

def embed(handle, x, y, width, height, tab=""):
    # Puts the real window exactly in its hole in the HUD, in front (Chrome stops drawing what it thinks is covered,
    # which looked like a blank grey box), and remembers where it was. Says what size it really became.
    import pc
    gone = {"title": "That window is gone."}
    with moving:
        if not handle or not win32gui.IsWindow(handle) or win32gui.GetWindowText(handle) in MIND_TITLES:
            return gone
        first = handle not in embedded["windows"]
        if first:
            embedded["windows"][handle] = {"placement": win32gui.GetWindowPlacement(handle), "rect": None}
            remember_embedded()
            keep_watch()
        elif embedded["windows"][handle].get("out"):
            # You're using it outside the HUD: don't pull it away, it goes to this spot when you come back to the HUD
            embedded["windows"][handle]["rect"] = (int(x), int(y), int(x) + int(width), int(y) + int(height))
            return {"title": win32gui.GetWindowText(handle), "width": int(width), "height": int(height)}
        if win32gui.IsIconic(handle) or win32gui.GetWindowPlacement(handle)[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(handle, win32con.SW_RESTORE)  # (only this takes a window out of maximized)
        if tab:
            pc.show_tab(handle, tab)
        try:
            win32gui.SetWindowPos(handle, 0, int(x), int(y), int(width), int(height), win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            embedded["waiting"] = False
            in_front(handle)
        except win32gui.error:  # (it closed just now, or the HUD did)
            return gone
        rect = win32gui.GetWindowRect(handle)  # (where it really went: every app has a minimum size)
        embedded["windows"][handle]["rect"] = rect
        title = win32gui.GetWindowText(handle)
    if first or tab:
        pc.bring_to_front(handle)  # (so you can type in it right away)
    return {"title": title, "width": rect[2] - rect[0], "height": rect[3] - rect[1]}

STAY = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE

def in_front(handle):
    # In front of the HUD, without taking the keyboard. Windows ignores a plain "bring to top" from a program in the
    # background (the HUD stayed on top, and Chrome stops drawing what it thinks is covered: a blank grey box).
    # Becoming "always on top" for a moment does work.
    win32gui.SetWindowPos(handle, win32con.HWND_TOPMOST, 0, 0, 0, 0, STAY)
    win32gui.SetWindowPos(handle, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, STAY)

def raise_embedded(handle=0):
    # The HUD was clicked: its windows come back in front of it
    with moving:
        embedded["waiting"] = False
        for window, about in list(embedded["windows"].items()):
            if win32gui.IsWindow(window) and not about.get("out") and (not handle or handle == window):
                try:
                    in_front(window)
                except win32gui.error:
                    pass  # (the HUD or the window closed just now: nothing to line up)

def hud_covers_it(handle, hud):
    # Is the HUD above the window? (top of the screen downwards: whichever comes first)
    window = win32gui.GetTopWindow(0)
    while window:
        if window == handle:
            return False
        if window == hud:
            return True
        window = win32gui.GetWindow(window, win32con.GW_HWNDNEXT)
    return False

def lower_embedded(handle=0):
    # The Control Center is open: the windows wait behind the HUD
    hud = win32gui.FindWindow(None, TITLE)
    with moving:
        embedded["waiting"] = True
        for window, about in list(embedded["windows"].items()):
            if hud and win32gui.IsWindow(window) and not about.get("out") and (not handle or handle == window):
                try:
                    win32gui.SetWindowPos(window, hud, 0, 0, 0, 0, STAY)
                except win32gui.error:
                    pass

def in_taskbar(window):
    # (clicking the taskbar or Start isn't going to another app yet)
    return win32gui.GetClassName(window) in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow", "TaskListThumbnailWnd")

def hud_on_screen():
    hud = win32gui.FindWindow(None, TITLE)
    return hud if hud and win32gui.IsWindowVisible(hud) and not win32gui.IsIconic(hud) else 0

def release(only=0):
    # Back to exactly where and how it was (all of them, or only this one).
    # If the HUD is still in use, it goes BEHIND the HUD: a window going back to full size jumps to the front,
    # and it buried the HUD, which looked like a crash.
    import pc
    with moving:
        leaving = [w for w in embedded["windows"] if not only or w == only]
        if not leaving:
            return
        hud = hud_on_screen()
        for window in leaving:
            about = embedded["windows"].pop(window)
            if win32gui.IsWindow(window) and not about.get("out"):  # (an "out" one is already at its own place)
                put_back(window, about["placement"])
                if hud:
                    try:
                        win32gui.SetWindowPos(window, hud, 0, 0, 0, 0, STAY)
                    except win32gui.error:
                        pass
        if not embedded["windows"]:
            embedded["waiting"] = False
        remember_embedded()
    if hud and win32gui.GetForegroundWindow() != hud:
        pc.bring_to_front(hud)

def put_back(handle, placement):
    try:
        flags, show, low, high, normal = placement
        # First as a normal window at its normal place, THEN maximized if it was: the other way round leaves it
        # "maximized" at the wrong spot, half off the screen
        win32gui.SetWindowPlacement(handle, (flags, win32con.SW_SHOWNORMAL, low, high, normal))
        if show == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(handle, win32con.SW_SHOWMAXIMIZED)
        elif show in (win32con.SW_SHOWMINIMIZED, win32con.SW_MINIMIZE):
            win32gui.ShowWindow(handle, win32con.SW_MINIMIZE)
        # Make it draw itself again
        win32gui.SetWindowPos(handle, 0, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                              | win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED)
        win32gui.RedrawWindow(handle, None, None, win32con.RDW_INVALIDATE | win32con.RDW_ALLCHILDREN | win32con.RDW_UPDATENOW | win32con.RDW_FRAME)
    except Exception as e:
        print("Couldn't put the window back:", e)

def shown_placement(placement):
    # The same place, but on screen even if it was minimized when it came into the HUD
    flags, show, low, high, normal = placement
    if show in (win32con.SW_SHOWMINIMIZED, win32con.SW_MINIMIZE):
        show = win32con.SW_SHOWMAXIMIZED if flags & win32con.WPF_RESTORETOMAXIMIZED else win32con.SW_SHOWNORMAL
    return (flags, show, low, high, normal)

def go_outside(window, about):
    # You came to this window from another app (Alt+Tab, taskbar): out here it's its own size and place
    about["out"] = True
    put_back(window, shown_placement(about["placement"]))

def come_back_in(window, about):
    # Back to the HUD: it returns to its spot there. Wherever you left it outside is now its own place.
    about["placement"] = win32gui.GetWindowPlacement(window)
    about["out"] = False
    remember_embedded()
    if win32gui.IsIconic(window) or about["placement"][1] == win32con.SW_SHOWMAXIMIZED:
        win32gui.ShowWindow(window, win32con.SW_RESTORE)
    left, top, right, bottom = about["rect"]
    win32gui.SetWindowPos(window, 0, left, top, right - left, bottom - top, win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
    in_front(window)
    about["rect"] = win32gui.GetWindowRect(window)

def let_go(window, about):
    # You maximized, minimized or moved it yourself: the HUD lets go, and none of the HUD's size stays with it.
    # (Maximized or minimized stays that way, but "restore" now goes to its own size, not the HUD's.)
    flags, _, low, high, normal = about["placement"]
    now = win32gui.GetWindowPlacement(window)
    if now[1] in (win32con.SW_SHOWMAXIMIZED, win32con.SW_SHOWMINIMIZED):
        win32gui.SetWindowPlacement(window, (flags, now[1], low, high, normal))
    else:
        put_back(window, shown_placement(about["placement"]))

def remember_embedded():
    try:
        if embedded["windows"]:
            with open(LEFT_BEHIND, "w", encoding="utf-8") as f:
                json.dump([{"handle": w, "placement": d["placement"]} for w, d in embedded["windows"].items()], f)
        elif os.path.exists(LEFT_BEHIND):
            os.remove(LEFT_BEHIND)
    except OSError as e:
        print("Couldn't note the windows in the HUD:", e)

def restore_left_behind():
    # At start: windows that were in the HUD when M.I.N.D stopped go back where they were
    try:
        with open(LEFT_BEHIND, encoding="utf-8") as f:
            left = json.load(f)
        os.remove(LEFT_BEHIND)
    except (OSError, ValueError):
        return
    for one in left if isinstance(left, list) else [left]:
        if win32gui.IsWindow(one["handle"]):
            p = one["placement"]
            put_back(one["handle"], (p[0], p[1], tuple(p[2]), tuple(p[3]), tuple(p[4])))
            print("(Put a window back that was still in the Jarvis HUD)")

# A window in the HUD is still YOURS. Every second: if the HUD went away, they go back; if you maximized, moved or
# minimized one yourself, the HUD lets go of it at once and never pulls it back (it used to feel stuck).
watching = {"on": False}
CLICK_COUNTS_FOR = 0.6  # seconds: a window got the keyboard this soon after a click on it = you clicked it in the HUD

def clicked_on(window, clicked_at):
    if time.time() - clicked_at > CLICK_COUNTS_FOR:
        return False
    left, top, right, bottom = win32gui.GetWindowRect(window)
    x, y = win32gui.GetCursorPos()
    return left <= x < right and top <= y < bottom

def keep_watch():
    if not watching["on"]:
        watching["on"] = True
        threading.Thread(target=watch_embedded, daemon=True).start()

def watch_embedded():
    turn = 0
    in_other_app = False
    clicked_at = 0.0
    while embedded["windows"]:
        time.sleep(0.25)
        turn += 1
        if ctypes.windll.user32.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8001:
            clicked_at = time.time()
        try:
            with moving:
                hud = win32gui.FindWindow(None, TITLE)
                front = win32gui.GetForegroundWindow()
                owner = win32gui.GetAncestor(front, 3) if front else 0
                inside = embedded["windows"].get(owner)
                if hud and front == hud:
                    # You clicked the HUD: the windows come back in front of it right away, so they keep drawing
                    in_other_app = False
                    if not embedded["waiting"]:
                        for window, about in list(embedded["windows"].items()):
                            if not win32gui.IsWindow(window):
                                continue
                            if about.get("out"):
                                come_back_in(window, about)
                            elif hud_covers_it(window, hud):
                                in_front(window)
                elif inside:
                    if inside.get("out"):
                        in_other_app = True  # (you're using it out there, like any other app)
                    elif in_other_app and hud:
                        if clicked_on(owner, clicked_at):
                            in_other_app = False  # (you clicked it where it sits in the HUD)
                        else:
                            go_outside(owner, inside)
                elif hud and front and not in_taskbar(front):
                    # You went to another app (Alt+Tab): the HUD's windows go with the HUD, not over your app
                    in_other_app = True
                    for window, about in list(embedded["windows"].items()):
                        if win32gui.IsWindow(window) and not about.get("out") and not hud_covers_it(window, hud):
                            win32gui.SetWindowPos(window, hud, 0, 0, 0, 0, STAY)
        except win32gui.error:
            pass
        if turn % 4:
            continue  # (the rest once a second)
        hud = win32gui.FindWindow(None, TITLE)
        if not hud or not win32gui.IsWindowVisible(hud):
            print("(The Jarvis HUD went away: the windows go back)")
            release()
            break
        with moving:
            for window, about in list(embedded["windows"].items()):
                if not win32gui.IsWindow(window):
                    embedded["windows"].pop(window, None)
                    remember_embedded()
                    continue
                rect = about["rect"]
                if not rect or about.get("out"):
                    continue
                now = win32gui.GetWindowRect(window)
                moved = any(abs(a - b) > 10 for a, b in zip(now, rect))
                if moved or win32gui.IsIconic(window) or win32gui.GetWindowPlacement(window)[1] == win32con.SW_SHOWMAXIMIZED:
                    print("(You took a window out of the HUD: it's back to its own size)")
                    let_go(window, about)
                    embedded["windows"].pop(window, None)
                    remember_embedded()
                    state.screen_view = {"id": int(time.time() * 1000), "close": window}  # (the HUD closes its hole)
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
        # (nor anything always on top, like Chrome's Picture in Picture: it floats over everything by design)
        if title in NOT_WINDOWS or is_cloaked(hwnd) or win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST:
            continue
        minimized = bool(win32gui.IsIconic(hwnd))
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if not minimized and hwnd not in embedded["windows"] and (right - left < 120 or bottom - top < 80):
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
        # (its own size first: Chrome opens its next window at the size the last one closed with)
        with moving:
            about = embedded["windows"].pop(handle, None)
            if about and not about.get("out"):
                put_back(handle, shown_placement(about["placement"]))
            remember_embedded()
        win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
    else:
        return "Unknown action."
    return f"{action}: {title[:60]}"
