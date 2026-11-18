# Window layouts by voice (2026-11-06): "Mind, put VS Code on the left and Claude on the right",
# "WhatsApp in the top right corner", "save this as my coding setup", "coding setup", "undo that".
# Windows GLIDE to their spots together (a short animation), edge to edge with no gaps.
# Saved setups live in profile["layouts"]: each window's app, title and place as shares of the screen,
# so a setup still fits if the screen size changes. Apps that aren't open are opened first.
import ctypes
import threading
import time
from ctypes import wintypes

import psutil
import win32api
import win32con
import win32gui

import memory
import pc

profile = memory.profile

# Spots as shares of the screen's work area (the part above the taskbar): x, y, width, height
SPOTS = {
    "full": (0, 0, 1, 1), "center": (.15, .08, .7, .84),
    "left": (0, 0, .5, 1), "right": (.5, 0, .5, 1), "top": (0, 0, 1, .5), "bottom": (0, .5, 1, .5),
    "top_left": (0, 0, .5, .5), "top_right": (.5, 0, .5, .5), "bottom_left": (0, .5, .5, .5), "bottom_right": (.5, .5, .5, .5),
    "left_third": (0, 0, 1 / 3, 1), "middle_third": (1 / 3, 0, 1 / 3, 1), "right_third": (2 / 3, 0, 1 / 3, 1),
    "left_two_thirds": (0, 0, 2 / 3, 1), "right_two_thirds": (1 / 3, 0, 2 / 3, 1),
}
# When they just name windows ("put these side by side"): spots by how many there are
AUTO = {1: ["full"], 2: ["left", "right"], 3: ["left_third", "middle_third", "right_third"],
        4: ["top_left", "top_right", "bottom_left", "bottom_right"]}
GLIDE_SECONDS, GLIDE_STEPS = 0.28, 14
last = {"before": [], "moved": []}  # where windows were before the last move ("undo"), and which ones moved ("swap")

class real_pixels:
    # Real screen pixels (the screen is scaled 125 %; window sizes and the frame fix must agree)
    def __enter__(self):
        ctypes.windll.user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        self.before = ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    def __exit__(self, *problem):
        if self.before:
            ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(self.before))

def work_area(hwnd=None):
    # The screen the window is on, minus the taskbar
    monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTOPRIMARY) if hwnd else \
        win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
    return win32api.GetMonitorInfo(monitor)["Work"]

def frame_gap(hwnd):
    # Windows 10/11 windows have invisible borders (~7 px) for resizing; without this fix there are gaps
    visible = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(visible), ctypes.sizeof(visible))  # 9 = real frame
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return visible.left - left, visible.top - top, right - visible.right, bottom - visible.bottom

def place_for(hwnd, spot):
    x, y, w, h = SPOTS[spot]
    left, top, right, bottom = work_area(hwnd)
    width, height = right - left, bottom - top
    gl, gt, gr, gb = frame_gap(hwnd)
    return (round(left + x * width) - gl, round(top + y * height) - gt,
            round(w * width) + gl + gr, round(h * height) + gt + gb)

def glide(hwnd, to):
    # Slide and resize the window to `to` (x, y, width, height) with an ease-out, then land exactly
    with real_pixels():
        if win32gui.IsIconic(hwnd) or win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.12)
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        start = (left, top, right - left, bottom - top)
        flags = win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
        for step in range(1, GLIDE_STEPS + 1):
            t = 1 - (1 - step / GLIDE_STEPS) ** 3
            x, y, w, h = (round(a + (b - a) * t) for a, b in zip(start, to))
            try:
                win32gui.SetWindowPos(hwnd, 0, x, y, w, h, flags)
            except win32gui.error:
                return
            time.sleep(GLIDE_SECONDS / GLIDE_STEPS)

def move_all(moves):
    # moves: [(hwnd, (x, y, w, h))]; all glide at the same time, then come to the front
    with real_pixels():
        last["before"] = [(hwnd, win32gui.GetWindowRect(hwnd), win32gui.GetWindowPlacement(hwnd)[1])
                          for hwnd, _ in moves if win32gui.IsWindow(hwnd)]
    last["moved"] = [hwnd for hwnd, _ in moves]
    threads = [threading.Thread(target=glide, args=move, daemon=True) for move in moves]
    for t in threads:
        t.start()
    for t in threads:
        t.join(3)
    for hwnd, _ in reversed(moves):
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        except win32gui.error:
            pass
    if moves:
        pc.bring_to_front(moves[0][0])

def find_or_open(name, wait=10):
    found = pc.find_windows(name)
    if found:
        return found[0]
    import tools
    tools.open_app(name)
    for _ in range(int(wait / 0.5)):
        time.sleep(0.5)
        found = pc.find_windows(name)
        if found:
            return found[0]
    return None

def spot_name(spot):
    spot = (spot or "").lower().strip().replace("-", "_").replace(" ", "_")
    spot = {"left_half": "left", "right_half": "right", "top_half": "top", "bottom_half": "bottom",
            "middle": "center", "centre": "center", "maximize": "full", "maximized": "full", "whole": "full",
            "fullscreen": "full", "full_screen": "full", "top_left_corner": "top_left", "top_right_corner": "top_right",
            "bottom_left_corner": "bottom_left", "bottom_right_corner": "bottom_right"}.get(spot, spot)
    return spot if spot in SPOTS else ""

def arrange(windows):
    picked, missing = [], []
    for item in windows[:6]:
        name = str(item.get("name", "")).strip()
        window = find_or_open(name) if name else None
        if not window:
            missing.append(name)
        elif all(window[0] != p[0][0] for p in picked):
            picked.append((window, spot_name(item.get("spot"))))
    if not picked:
        return f"Couldn't find {', '.join(missing) or 'those windows'} open. Say which apps."
    auto = AUTO.get(len(picked), ["full"] * len(picked))
    spots = [spot or auto[i] for i, (_, spot) in enumerate(picked)]
    with real_pixels():
        moves = [(window[0], place_for(window[0], spot)) for (window, _), spot in zip(picked, spots)]
    move_all(moves)
    said = ", ".join(f"{window[3][:40]} {spot.replace('_', ' ')}" for (window, _), spot in zip(picked, spots))
    return "Arranged: " + said + (f". Not found: {', '.join(missing)}." if missing else ".")

def screen_windows():
    # Normal windows on screen now (not M.I.N.D's, not minimized, not tiny, not always-on-top ones)
    found = []
    for hwnd, pid, app, title in pc.open_windows():
        if title in pc.MIND_WINDOWS or app.lower() in ("explorer", "textinputhost", "shellexperiencehost", "applicationframehost") \
                or win32gui.IsIconic(hwnd) or win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & (win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW):
            continue
        with real_pixels():
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right - left < 200 or bottom - top < 150:
            continue
        found.append((hwnd, pid, app, title))
    return found

def save(layout):
    layout = (layout or "").strip().lower()
    if not layout:
        return "Ask what to call this setup."
    saved = []
    for hwnd, pid, app, title in screen_windows()[:8]:
        with real_pixels():
            area = work_area(hwnd)
            gl, gt, gr, gb = frame_gap(hwnd)
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            maximized = win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED
        width, height = area[2] - area[0], area[3] - area[1]
        try:
            exe = psutil.Process(pid).exe()
        except psutil.Error:
            exe = ""
        saved.append({"app": app, "title": title[:80], "exe": exe, "maximized": maximized,
                      "box": [round((left + gl - area[0]) / width, 4), round((top + gt - area[1]) / height, 4),
                              round((right - gr - left - gl) / width, 4), round((bottom - gb - top - gt) / height, 4)]})
    if not saved:
        return "No windows on screen to save."
    profile.setdefault("layouts", {})[layout] = saved
    memory.save_profile()
    return f"Saved '{layout}': " + ", ".join(w["title"][:30] for w in saved) + "."

def best_window(item, taken):
    # The open window that is most like the saved one: same app, then the most title words in common
    words = set(pc.squash(w) for w in item["title"].split() if len(w) > 2)
    best, score = None, -1
    for window in screen_windows() + [w for w in pc.open_windows() if win32gui.IsIconic(w[0])]:
        if window[0] in taken or window[2].lower() != item["app"].lower():
            continue
        common = len(words & set(pc.squash(w) for w in window[3].split()))
        if common > score:
            best, score = window, common
    return best

def restore(layout):
    layouts = profile.get("layouts", {})
    layout = (layout or "").strip().lower()
    if layout not in layouts:
        return f"No setup called '{layout}'. Saved setups: {', '.join(layouts) or 'none yet'}."
    moves, maximize, opened, taken = [], [], [], set()
    for item in layouts[layout]:
        window = best_window(item, taken)
        if not window and item.get("exe"):
            import subprocess
            try:
                subprocess.Popen([item["exe"]])
                opened.append(item["app"])
            except OSError:
                continue
            for _ in range(20):
                time.sleep(0.5)
                window = best_window(item, taken)
                if window:
                    break
        if not window:
            continue
        taken.add(window[0])
        if win32gui.IsIconic(window[0]):  # (a minimized window's frame can't be measured: bring it back first)
            win32gui.ShowWindow(window[0], win32con.SW_RESTORE)
            time.sleep(0.15)
        if item.get("maximized"):
            maximize.append(window[0])
            continue
        with real_pixels():
            area = work_area(window[0])
            gl, gt, gr, gb = frame_gap(window[0])
        width, height = area[2] - area[0], area[3] - area[1]
        x, y, w, h = item["box"]
        moves.append((window[0], (round(area[0] + x * width) - gl, round(area[1] + y * height) - gt,
                                  round(w * width) + gl + gr, round(h * height) + gt + gb)))
    move_all(moves)
    for hwnd in maximize:
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    if not (moves or maximize):
        return f"None of the '{layout}' windows could be found or opened."
    return f"'{layout}' is set up" + (f" (opened {', '.join(opened)})" if opened else "") + "."

def undo():
    if not last["before"]:
        return "Nothing to undo."
    moves = []
    for hwnd, (left, top, right, bottom), shown in last["before"]:
        if win32gui.IsWindow(hwnd):
            moves.append((hwnd, (left, top, right - left, bottom - top), shown))
    move_all([(hwnd, box) for hwnd, box, _ in moves])
    for hwnd, _, shown in moves:
        if shown == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    last["before"] = []  # (one undo: back to how it was)
    return "Put them back."

def swap():
    # The two windows moved last trade places (else the two in front)
    windows = [w for w in screen_windows() if w[0] in last["moved"]][:2]
    if len(windows) < 2:
        windows = screen_windows()[:2]
    if len(windows) < 2:
        return "Need two windows on screen to swap."
    with real_pixels():
        boxes = [win32gui.GetWindowRect(w[0]) for w in windows]
    a, b = [(l, t, r - l, btm - t) for l, t, r, btm in boxes]
    move_all([(windows[0][0], b), (windows[1][0], a)])
    return f"Swapped {windows[0][3][:30]} and {windows[1][3][:30]}."

def arrange_windows(action="arrange", windows=None, layout=""):
    # The tool
    action = (action or "arrange").lower()
    if action == "save":
        return save(layout)
    if action == "restore":
        return restore(layout)
    if action == "undo":
        return undo()
    if action == "swap":
        return swap()
    if action == "list":
        saved = profile.get("layouts", {})
        return ("Saved setups: " + "; ".join(f"{n} ({', '.join(w['app'] for w in ws)})" for n, ws in saved.items())) \
            if saved else "No saved setups yet."
    if action == "delete":
        if profile.get("layouts", {}).pop((layout or "").lower(), None) is None:
            return f"No setup called '{layout}'."
        memory.save_profile()
        return f"Deleted '{layout}'."
    if isinstance(windows, str):
        windows = [{"name": n.strip()} for n in windows.split(",") if n.strip()]
    return arrange([w if isinstance(w, dict) else {"name": str(w)} for w in (windows or [])])
