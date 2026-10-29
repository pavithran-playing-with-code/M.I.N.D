# Floating window: a glowing arc reactor that stays on top of everything, with the chat
# floating beside it (no title bar, no background). Every frame is drawn with Pillow and
# shown in a "layered" Windows window, so each pixel can be see-through.
# Colors: blue = waiting / speaking, gold = listening / thinking, red = offline (mic off).
import ctypes
import math
import queue
import threading
import time
from ctypes import wintypes

import win32api
import win32con
import win32gui
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import state

TITLE = "M.I.N.D mini"  # pc.MIND_WINDOWS keeps close/window tools away from it
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
REACTOR = 72        # reactor size in pixels (at 100% screen scale)
TEXT_WIDTH = 230    # chat text beside the reactor
GAP = 8
HEIGHT = 92
MARGIN = 14         # distance from the screen edge
SHOW_SECONDS = 4    # the chat fades away this long after M.I.N.D goes quiet
NUDGE = 60      # "move it a little up", in pixels ("a lot" = 4 times this)

BLUE = (40, 200, 255)
GOLD = (255, 184, 56)
AMBER = (255, 150, 40)
RED = (255, 75, 75)
# status: (color, brightness, spin speed in degrees per second)
LOOKS = {
    "waiting":   (BLUE, 0.6, 14),
    "starting":  (BLUE, 0.6, 14),
    "listening": (GOLD, 1.0, 40),
    "thinking":  (AMBER, 0.95, 170),
    "speaking":  (BLUE, 1.0, 60),
    "muted":     (RED, 0.45, 6),
}

FONT_DIR = r"C:\Windows\Fonts"

def font(size, tamil=False):
    try:
        name = "Nirmala.ttc" if tamil else "bahnschrift.ttf"
        return ImageFont.truetype(f"{FONT_DIR}\\{name}", size)
    except OSError:
        return ImageFont.load_default(size)

def has_tamil(text):
    return any("\u0B80" <= ch <= "\u0BFF" for ch in text)

def wrap(text, fnt, width, max_lines):
    # Split text into lines that fit the width; "..." if it's too long
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if fnt.getlength(test) <= width or not line:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and fnt.getlength(lines[-1] + "…") > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines

def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Painter:
    # Draws one frame of the floating window (reactor + chat) as an RGBA image
    def __init__(self, scale=1.0, mirrored=False):
        self.s = scale
        self.mirrored = mirrored  # right-side corners: reactor at the edge, chat on its left
        self.r = int(REACTOR * scale)
        self.w = int((REACTOR + GAP + TEXT_WIDTH) * scale)
        self.h = int(HEIGHT * scale)
        self.color = BLUE
        self.bright = 0.6
        self.angle = 0.0
        self.level = 0.0
        self.last = time.time()
        self.text_key = None
        self.text_layer = None
        self.text_alpha = 0.0
        self.hide_at = time.time() + SHOW_SECONDS
        self.seen_id = 0
        self.chips = []  # [(action, (left, top, right, bottom))] buttons in window pixels (Copy / Replace)
        self.chip_spots = []  # the same, inside the text layer (moved into place each frame)
        # Soft glow behind the reactor (made once, tinted every frame)
        glow = Image.new("L", (self.r, self.r), 0)
        ImageDraw.Draw(glow).ellipse([self.r * 0.22] * 2 + [self.r * 0.78] * 2, fill=255)
        self.glow = glow.filter(ImageFilter.GaussianBlur(self.r * 0.12))

    def reactor(self, now, pulse):
        r2 = self.r * 2  # drawn at double size, then shrunk for smooth edges
        c = r2 / 2
        img = Image.new("RGBA", (r2, r2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        col = self.color
        b = self.bright
        s2 = self.s * 2

        def rgba(alpha, color=col):
            return color + (int(255 * max(0, min(1, alpha))),)

        def ring(radius, width, alpha):
            d.ellipse([c - radius, c - radius, c + radius, c + radius], outline=rgba(alpha), width=max(1, int(width)))

        # Outer ticks, turning slowly
        for i in range(48):
            a = math.radians(i * 7.5 + self.angle * 0.3)
            long = i % 4 == 0
            r_out, r_in = c * 0.97, c * (0.88 if long else 0.92)
            d.line([(c + r_in * math.cos(a), c + r_in * math.sin(a)),
                    (c + r_out * math.cos(a), c + r_out * math.sin(a))],
                   fill=rgba(b * (0.7 if long else 0.4)), width=max(1, int(1.2 * s2)))
        # Three arcs, turning with the state's speed
        rad = c * 0.82
        for i in range(3):
            start = self.angle + i * 120
            d.arc([c - rad, c - rad, c + rad, c + rad], start, start + 70, fill=rgba(b), width=max(1, int(2.5 * s2)))
        ring(c * 0.74, 1 * s2, b * 0.35)
        # The arc reactor's ring of 10 coils, turning the other way
        r_in, r_out = c * 0.46, c * 0.66
        for i in range(10):
            a0 = math.radians(-self.angle * 0.6 + i * 36)
            a1 = a0 + math.radians(26)
            points = [(c + r_in * math.cos(a0), c + r_in * math.sin(a0)),
                      (c + r_out * math.cos(a0 - 0.03), c + r_out * math.sin(a0 - 0.03)),
                      (c + r_out * math.cos(a1 + 0.03), c + r_out * math.sin(a1 + 0.03)),
                      (c + r_in * math.cos(a1), c + r_in * math.sin(a1))]
            d.polygon(points, fill=rgba(b * (0.25 + 0.35 * pulse)), outline=rgba(b * 0.9))
        ring(c * 0.42, 1.5 * s2, b * 0.8)
        # Glowing core: grows with the voice / mic
        core = c * (0.22 + 0.1 * pulse)
        d.ellipse([c - core, c - core, c + core, c + core], fill=rgba(b * 0.85))
        inner = core * 0.6
        d.ellipse([c - inner, c - inner, c + inner, c + inner], fill=rgba(min(1, b + 0.2), mix(col, (255, 255, 255), 0.7)))
        img = img.resize((self.r, self.r), Image.LANCZOS)

        # Glow underneath
        glow_alpha = (0.35 + 0.45 * pulse) * b
        tint = Image.new("RGBA", (self.r, self.r), col + (0,))
        tint.putalpha(self.glow.point(lambda v: int(v * glow_alpha)))
        return Image.alpha_composite(tint, img)

    def make_text(self, you, reply):
        # The chat lines with a dark shadow, so they're readable on any background
        width = int(TEXT_WIDTH * self.s)
        f_you = font(int(11 * self.s), has_tamil(you))
        f_reply = font(int(14 * self.s), has_tamil(reply))
        rows = [(line, f_you, (175, 205, 225)) for line in wrap(f"You: {you}", f_you, width, 1)] if you else []
        rows += [(line, f_reply, (230, 248, 255)) for line in wrap(reply, f_reply, width, 3)] if reply else []
        layer = Image.new("RGBA", (width + int(16 * self.s), self.h), (0, 0, 0, 0))
        if not rows:
            return layer
        heights = [f.getbbox("Ag")[3] + int(3 * self.s) for _, f, _ in rows]
        y = (self.h - sum(heights)) // 2
        pad = int(6 * self.s)
        shadow = Image.new("L", layer.size, 0)
        sd = ImageDraw.Draw(shadow)
        td = ImageDraw.Draw(layer)
        for (line, f, color), h in zip(rows, heights):
            x = pad if not self.mirrored else layer.width - pad - int(f.getlength(line))
            sd.text((x, y), line, font=f, fill=255)
            td.text((x, y), line, font=f, fill=color + (255,))
            y += h
        # Shadow: the text blurred and darkened, under the text
        shadow = shadow.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(3 * self.s))
        dark = Image.new("RGBA", layer.size, (0, 8, 16, 0))
        dark.putalpha(shadow.point(lambda v: min(255, v * 2)))
        return Image.alpha_composite(dark, layer)

    def make_offer(self, offer):
        # A fix (grammar) with Copy / Replace buttons, so you can use it without opening the HUD
        width = int(TEXT_WIDTH * self.s)
        f_label = font(int(10 * self.s))
        f_text = font(int(12 * self.s), has_tamil(offer["text"]))
        f_chip = font(int(11 * self.s))
        lines = wrap(offer["text"], f_text, width, 3)
        layer = Image.new("RGBA", (width + int(16 * self.s), self.h), (0, 0, 0, 0))
        td = ImageDraw.Draw(layer)
        line_h = f_text.getbbox("Ag")[3] + int(2 * self.s)
        chip_h = int(18 * self.s)
        label_h = f_label.getbbox("Ag")[3] + int(2 * self.s)
        total = label_h + line_h * len(lines) + int(4 * self.s) + chip_h
        y = max(0, (self.h - total) // 2)
        pad = int(6 * self.s)
        # dark rounded card behind it all, so it's readable on any background
        td.rounded_rectangle([0, max(0, y - int(4 * self.s)), width + int(2 * self.s), min(self.h - 1, y + total + int(4 * self.s))],
                             radius=int(8 * self.s), fill=(4, 18, 28, 215), outline=(40, 200, 255, 140))
        td.text((pad, y), offer.get("done") or "Better version:", font=f_label, fill=(61, 255, 154, 255))
        y += label_h
        for line in lines:
            td.text((pad, y), line, font=f_text, fill=(230, 248, 255, 255))
            y += line_h
        y += int(4 * self.s)
        self.chip_spots = []
        if not offer.get("done"):
            x = pad
            for action, label in [("copy", "Copy")] + ([("replace", "Replace")] if offer.get("replace") else []):
                w = int(f_chip.getlength(label)) + int(16 * self.s)
                td.rounded_rectangle([x, y, x + w, y + chip_h], radius=int(6 * self.s),
                                     fill=(20, 70, 95, 255), outline=(40, 200, 255, 255))
                td.text((x + int(8 * self.s), y + int(3 * self.s)), label, font=f_chip, fill=(200, 240, 255, 255))
                self.chip_spots.append((action, (x, y, x + w, y + chip_h)))
                x += w + int(8 * self.s)
        return layer

    def frame(self, snap):
        now = time.time()
        dt = min(0.2, now - self.last)
        self.last = now
        status = "muted" if snap.get("muted") else snap.get("status", "waiting")
        color, bright, speed = LOOKS.get(status, LOOKS["waiting"])
        k = min(1, dt * 5)  # smooth color changes
        self.color = mix(self.color, color, k)
        self.bright += (bright - self.bright) * k
        self.angle = (self.angle + speed * dt) % 360

        if status == "listening":
            self.level += (min(1, snap.get("level", 0) * 2.5) - self.level) * min(1, dt * 12)
            pulse = self.level
        elif status == "speaking":
            pulse = 0.55 + 0.3 * math.sin(now * 9) + 0.15 * math.sin(now * 23)
        elif status == "thinking":
            pulse = 0.45 + 0.2 * math.sin(now * 5)
        else:
            pulse = 0.25 + 0.12 * math.sin(now * 1.6)  # slow breathing

        # The chat: your last words and the reply to them
        messages = snap.get("messages", [])
        you = next((m for m in reversed(messages) if m["who"] == "you"), None)
        reply = next((m for m in reversed(messages) if m["who"] == "mind"), None)
        if reply and you and reply["id"] < you["id"]:
            reply = None  # that reply was for something earlier
        newest = max([m["id"] for m in (you, reply) if m] or [0])
        if newest > self.seen_id:
            self.seen_id = newest
            self.hide_at = now + SHOW_SECONDS
        if status in ("thinking", "speaking"):  # (not while just listening for a follow-up)
            self.hide_at = max(self.hide_at, now + SHOW_SECONDS)
        offer = state.offer if state.offer and now < state.offer["until"] else None
        if offer:
            key = ("offer", offer["id"], offer.get("done"))
            self.hide_at = max(self.hide_at, offer["until"])
        else:
            key = (you and you["text"], reply and reply["text"])
            self.chip_spots = []
        if key != self.text_key:
            self.text_key = key
            self.text_layer = self.make_offer(offer) if offer else self.make_text(key[0] or "", key[1] or "")
        target = 1.0 if now < self.hide_at and any(key) else 0.0
        self.text_alpha += (target - self.text_alpha) * min(1, dt * (6 if target else 2.5))

        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        rx = self.w - self.r if self.mirrored else 0
        img.alpha_composite(self.reactor(now, max(0, min(1, pulse))), (rx, (self.h - self.r) // 2))
        if self.text_alpha > 0.01:
            layer = self.text_layer.copy()
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * self.text_alpha)))
            slide = int((1 - self.text_alpha) * 10 * self.s)  # drifts out from the reactor
            gap = int(GAP * self.s)
            tx = (rx - gap - layer.width - slide + int(8 * self.s)) if self.mirrored else (self.r + gap + slide - int(8 * self.s))
            img.alpha_composite(layer, (max(0, tx), 0))
            self.chips = [(a, (l + max(0, tx), t, r + max(0, tx), b)) for a, (l, t, r, b) in self.chip_spots]
        else:
            self.chips = []
        busy = status in ("listening", "thinking", "speaking") or 0.01 < self.text_alpha < 0.99
        return img, busy


# ---------- The Windows window ----------
class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]

commands = queue.Queue()
thread = None

def corner_spot(corner, w, h, offset=(0, 0), scale=1.0):
    # Top-left point of the window: a corner of the main screen (without the taskbar),
    # shifted by the "a little up / left" nudges, but always kept on the screen
    monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
    left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
    margin = int(MARGIN * scale)
    x = left + margin if "left" in corner else right - w - margin
    y = top + margin if "top" in corner else bottom - h - margin
    x = max(left, min(right - w, x + int(offset[0] * scale)))
    y = max(top, min(bottom - h, y + int(offset[1] * scale)))
    return x, y

# ---------- Mouse: click = wake / stop M.I.N.D, hold and drag = move it ----------
spot = {"x": 0, "y": 0}  # where the window is now (screen pixels)
current = {}             # the painter in use (its size and which side the chat is on)
drag = None              # while the mouse button is down: where it started

def on_down(hwnd, msg, wparam, lparam):
    global drag
    drag = {"mouse": win32api.GetCursorPos(), "window": (spot["x"], spot["y"]), "moved": False}
    win32gui.SetCapture(hwnd)  # keep getting the mouse even if it leaves the window
    return 0

def on_move(hwnd, msg, wparam, lparam):
    if drag:
        mx, my = win32api.GetCursorPos()
        dx, dy = mx - drag["mouse"][0], my - drag["mouse"][1]
        if abs(dx) + abs(dy) > 4:
            drag["moved"] = True  # a real drag, not a shaky click
        if drag["moved"]:
            spot["x"], spot["y"] = drag["window"][0] + dx, drag["window"][1] + dy
            win32gui.SetWindowPos(hwnd, 0, spot["x"], spot["y"], 0, 0,
                                  win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
    return 0

def on_up(hwnd, msg, wparam, lparam):
    global drag
    was, drag = drag, None
    win32gui.ReleaseCapture()
    if was and was["moved"]:
        dropped()
        return 0
    if pressed_button():
        return 0
    # One click = wake M.I.N.D / stop it talking. Two quick clicks = open or close the HUD.
    # So a single click waits a moment to see if a second one comes.
    now = time.time()
    if clicks["timer"] and now - clicks["last"] < DOUBLE_CLICK:
        clicks["timer"].cancel()
        clicks["timer"] = None
        threading.Thread(target=toggle_hud, daemon=True).start()
    else:
        clicks["last"] = now
        clicks["timer"] = threading.Timer(DOUBLE_CLICK, single_click)
        clicks["timer"].start()
    return 0

DOUBLE_CLICK = 0.35  # seconds between two clicks to count as a double-click

def pressed_button():
    # A click on Copy / Replace (next to the reactor): do it. The reactor never takes the keyboard
    # focus, so the box you were typing in (WhatsApp...) still has it and Replace pastes right there.
    import writing
    p = current.get("painter")
    if not p or not p.chips:
        return False
    mx, my = win32api.GetCursorPos()
    x, y = mx - spot["x"], my - spot["y"]
    for action, (left, top, right, bottom) in p.chips:
        if left <= x <= right and top <= y <= bottom:
            threading.Thread(target=writing.copy_now if action == "copy" else writing.replace_now, daemon=True).start()
            return True
    return False
clicks = {"last": 0.0, "timer": None}

def single_click():
    import typebox
    clicks["timer"] = None
    if typebox.is_open():
        # Second click while the little box is open: close it and stop listening
        typebox.close()
        state.stop_listening.set()
        return
    state.click()  # same as clicking the HUD orb: wake M.I.N.D / stop it talking

BOX_HEIGHT = 30  # the little text box (at 100% screen scale)

def type_box_spot():
    # Where the little text box goes: beside the reactor, towards the middle of the screen
    # (reactor on the right -> box on its left, and the other way round), centred on it.
    # Follows the reactor while you drag it.
    p = current.get("painter")
    if not is_shown() or not p:
        return None
    width, height, gap = int(TEXT_WIDTH * p.s), int(BOX_HEIGHT * p.s), int(GAP * p.s)
    reactor_x = spot["x"] + (p.w - p.r if p.mirrored else 0)
    monitor = win32api.MonitorFromPoint((reactor_x, spot["y"]), win32con.MONITOR_DEFAULTTONEAREST)
    left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
    if reactor_x + p.r / 2 > (left + right) / 2:
        x = reactor_x - gap - width  # reactor on the right half: box on its left
    else:
        x = reactor_x + p.r + gap
    y = spot["y"] + (p.h - height) // 2  # same height as the reactor's centre
    return max(left, min(right - width, x)), max(top, min(bottom - height, y)), width, height

def open_type_box():
    # Click on the reactor: a small text box appears next to it
    import typebox
    if type_box_spot():
        typebox.show(type_box_spot)

def toggle_hud():
    # Double-click: the HUD comes up (opens, or comes to the front if it's behind other windows);
    # if it's already in front, it closes. The reactor stays.
    import hud
    windows = hud.hud_windows()
    in_front = win32gui.GetForegroundWindow() in windows or any(
        not win32gui.IsIconic(w) and hud_on_top(w) for w in windows)
    if windows and in_front:
        for hud_window in windows:
            win32gui.PostMessage(hud_window, win32con.WM_CLOSE, 0, 0)
    else:
        hud.open_hud()  # opens it, or brings the open one to the front

def hud_on_top(hwnd):
    # The HUD is the top window at its own centre (so it's visible, not hidden behind WhatsApp...)
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        here = win32gui.WindowFromPoint(((left + right) // 2, (top + bottom) // 2))
        return win32gui.GetAncestor(here, 2) == hwnd  # 2 = the top-level window
    except Exception:
        return False

def dropped():
    # Remember where it was dropped: as the nearest corner + how far from it (survives restarts).
    # The chat goes on the side with more room, and the reactor stays where you put it.
    p = current["painter"]
    reactor_x = spot["x"] + (p.w - p.r if p.mirrored else 0)
    monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
    left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
    corner = (("top" if spot["y"] + p.h / 2 < (top + bottom) / 2 else "bottom") + "-"
              + ("left" if reactor_x + p.r / 2 < (left + right) / 2 else "right"))
    x = reactor_x - (p.w - p.r if "right" in corner else 0)
    base_x, base_y = corner_spot(corner, p.w, p.h)
    offset = (round((x - base_x) / p.s), round((spot["y"] - base_y) / p.s))
    commands.put(("move", (corner, offset)))
    try:
        from memory import profile, save_profile
        profile.update(floating=True, floating_position=corner, floating_offset=list(offset))
        save_profile()
    except Exception as e:
        print("Couldn't save the floating window's place:", e)

def no_focus(hwnd, msg, wparam, lparam):
    return 3  # MA_NOACTIVATE: clicking it doesn't take the keyboard away from your app

def on_close(hwnd, msg, wparam, lparam):
    commands.put(("hide", None))
    return 0

def run(corner, offset):
    # Runs in its own thread: makes the window, then draws up to 24 frames a second
    try:
        user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # sharp on scaled screens
    except Exception:
        pass
    instance = win32api.GetModuleHandle(None)
    wc = win32gui.WNDCLASS()
    wc.lpszClassName = "MIND_floating"
    wc.hInstance = instance
    wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_HAND)
    wc.lpfnWndProc = {win32con.WM_LBUTTONDOWN: on_down, win32con.WM_MOUSEMOVE: on_move,
                      win32con.WM_LBUTTONUP: on_up, win32con.WM_MOUSEACTIVATE: no_focus,
                      win32con.WM_CLOSE: on_close}
    try:
        win32gui.RegisterClass(wc)
    except win32gui.error:
        pass  # already registered (shown before)
    ex = win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE
    hwnd = win32gui.CreateWindowEx(ex, "MIND_floating", TITLE, win32con.WS_POPUP, 0, 0, 10, 10, 0, 0, instance, None)
    scale = (user32.GetDpiForWindow(hwnd) or 96) / 96

    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = None
    painter = None
    blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, use each pixel's alpha
    shown = False
    while True:
        win32gui.PumpWaitingMessages()
        try:
            action, arg = commands.get_nowait()
        except queue.Empty:
            action, arg = None, None
        if action == "hide":
            break
        if action == "move" or painter is None:
            if arg:
                corner, offset = arg
            painter = Painter(scale, mirrored="right" in corner)
            bits = ctypes.c_void_p()
            header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), painter.w, -painter.h, 1, 32, 0)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
            gdi32.SelectObject(memory, bitmap)
            spot["x"], spot["y"] = corner_spot(corner, painter.w, painter.h, offset, scale)
            current["painter"] = painter

        img, busy = painter.frame(state.snapshot())
        data = img.convert("RGBa").tobytes("raw", "BGRa")  # Windows wants blue-green-red-alpha, premultiplied
        ctypes.memmove(bits, data, len(data))
        user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(wintypes.POINT(spot["x"], spot["y"])),
                                   ctypes.byref(wintypes.SIZE(painter.w, painter.h)), memory,
                                   ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), 2)  # ULW_ALPHA
        if not shown:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
            shown = True
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        time.sleep(1 / 60 if drag else 1 / 24 if busy else 1 / 10)  # smooth while dragging, calm when idle

    win32gui.DestroyWindow(hwnd)
    if bitmap:
        gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(None, screen)

def is_shown():
    return thread is not None and thread.is_alive()

def show(corner="bottom-right", offset=(0, 0)):
    global thread
    if is_shown():
        commands.put(("move", (corner, tuple(offset))))
        return
    while not commands.empty():
        commands.get_nowait()
    thread = threading.Thread(target=run, args=(corner, tuple(offset)), daemon=True)
    thread.start()

def hide():
    if is_shown():
        commands.put(("hide", None))
        thread.join(3)

def window_tool(action="show", position="", far=False):
    # The floating_window tool: show / hide / move to a corner / nudge a little up, down, left or right.
    # Remembers the place in profile.json.
    from memory import profile, save_profile
    if action == "hide":
        hide()
        profile["floating"] = False
        save_profile()
        return "Floating window hidden."
    corner = profile.get("floating_position", "bottom-right")
    dx, dy = profile.get("floating_offset", [0, 0])
    if position in CORNERS:
        corner, dx, dy = position, 0, 0  # a new corner starts fresh
    if position in ("up", "down", "left", "right"):
        step = NUDGE * (4 if far else 1)
        dx += {"left": -step, "right": step}.get(position, 0)
        dy += {"up": -step, "down": step}.get(position, 0)
    show(corner, (dx, dy))
    profile.update(floating=True, floating_position=corner, floating_offset=[dx, dy])
    save_profile()
    if position in ("up", "down", "left", "right"):
        return f"Floating window moved {'a lot' if far else 'a little'} {position}."
    return f"Floating window {'moved to' if action == 'move' else 'shown at'} the {corner.replace('-', ' ')}."
