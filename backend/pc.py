# PC control: typing, keyboard shortcuts, closing apps, PC health, locking, and looking at the screen.
# These are used as tools by the brain (see TOOLS in tools.py).
import io
import os
import re
import time
import base64
import ctypes
from ctypes import wintypes
import psutil
import win32gui
import win32con
import win32process
from PIL import ImageGrab
from groq import Groq

user32 = ctypes.windll.user32

def squash(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

# ---------- Typing (works in any app: the text goes where the cursor is) ----------
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

class INPUT(ctypes.Structure):
    class _KeyOrMouse(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _KeyOrMouse)]

KEYBOARD, UNICODE, KEY_UP = 1, 0x0004, 0x0002

def tap(vk):
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEY_UP, 0)

def send_letter(code):
    for flags in (UNICODE, UNICODE | KEY_UP):
        key = INPUT(type=KEYBOARD, ki=KEYBDINPUT(0, code, flags, 0, 0))
        user32.SendInput(1, ctypes.byref(key), ctypes.sizeof(INPUT))

def type_text(text, wait_seconds=0, press_enter=False):
    time.sleep(min(float(wait_seconds), 10))  # give a just-opened app time to load
    for ch in text:
        if ch == "\n":
            tap(0x0D)  # Enter
            continue
        # Emojis and some symbols are two pieces in Windows' format, so send each piece
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):
            send_letter(int.from_bytes(data[i:i + 2], "little"))
        time.sleep(0.004)
    if press_enter:
        tap(0x0D)
    return f"Typed {len(text)} characters" + (" and pressed Enter." if press_enter else ".")

# ---------- Keyboard shortcuts ----------
KEY_CODES = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B,
    "enter": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20, "backspace": 0x08,
    "delete": 0x2E, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "home": 0x24,
    "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "printscreen": 0x2C,
}

def key_code(name):
    name = name.strip().lower()
    if name in KEY_CODES:
        return KEY_CODES[name]
    if re.fullmatch(r"f([1-9]|1[0-2])", name):
        return 0x70 + int(name[1:]) - 1  # F1..F12
    if re.fullmatch(r"[a-z0-9]", name):
        return ord(name.upper())
    return None

def press_keys(keys):
    # keys like "ctrl+w", "alt+tab", "win+d"
    codes = [key_code(k) for k in keys.split("+")]
    if None in codes or not codes:
        return f"Don't know the keys '{keys}'."
    for c in codes:
        user32.keybd_event(c, 0, 0, 0)
    for c in reversed(codes):
        user32.keybd_event(c, 0, KEY_UP, 0)
    return f"Pressed {keys}."

# ---------- Closing apps ----------
def my_family():
    # M.I.N.D's own process and the ones that started it (terminal, VS Code...)
    ids, proc = set(), psutil.Process(os.getpid())
    while proc and proc.name().lower() != "explorer.exe":  # stop at Windows itself
        ids.add(proc.pid)
        proc = proc.parent()
    return ids

# Windows' own desktop window: closing it opens the shut down dialog, so never touch it
NEVER_CLOSE = {"Program Manager"}

def open_windows():
    # (window, process id, app name, title) for every visible window with a title
    found = []
    def check(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if win32gui.IsWindowVisible(hwnd) and title and title not in NEVER_CLOSE:
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            try:
                app = psutil.Process(pid).name().removesuffix(".exe")
            except psutil.Error:
                return
            found.append((hwnd, pid, app, title))
    win32gui.EnumWindows(check, None)
    return found

def close_app(name):
    want = squash(name)
    windows = open_windows()
    # Match the app's name first ("chrome"), then window titles ("YouTube")
    match = [w for w in windows if want and want in squash(w[2])]
    if not match:
        match = [w for w in windows if want and want in squash(w[3])]
    if not match:
        apps = sorted({w[2] for w in windows if w[2].lower() not in ("explorer", "textinputhost")})
        return f"No open app called {name}. Open apps: {', '.join(apps)}."
    family = my_family()
    if any(w[1] in family for w in match):
        return f"Closing {name} would also close M.I.N.D, so I left it open."
    for hwnd, *_ in match:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)  # polite close, apps can still ask to save
    return f"Closed {len(match)} window(s): {', '.join(sorted({w[2] for w in match}))}."

# ---------- PC health ----------
def system_info():
    parts = []
    battery = psutil.sensors_battery()
    if battery:
        charging = "charging" if battery.power_plugged else "not charging"
        parts.append(f"Battery {round(battery.percent)}%, {charging}")
        if not battery.power_plugged and battery.secsleft > 0:
            parts[-1] += f", about {battery.secsleft // 3600}h {battery.secsleft % 3600 // 60}m left"
    parts.append(f"CPU {psutil.cpu_percent(interval=0.5)}% busy")
    ram = psutil.virtual_memory()
    parts.append(f"RAM {ram.percent}% used ({ram.available / 2**30:.1f} GB free of {ram.total / 2**30:.0f} GB)")
    disk = psutil.disk_usage("C:\\")
    parts.append(f"C: drive {disk.free / 2**30:.0f} GB free")
    # Apps using the most memory
    use = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            name = p.info["name"].removesuffix(".exe")
            use[name] = use.get(name, 0) + p.info["memory_info"].rss
        except (psutil.Error, AttributeError, TypeError):
            pass
    top = sorted(use.items(), key=lambda x: -x[1])[:3]
    parts.append("Biggest memory users: " + ", ".join(f"{n} {m / 2**30:.1f} GB" for n, m in top))
    return ". ".join(parts) + "."

def lock_pc():
    user32.LockWorkStation()
    return "PC locked."

# ---------- Looking at the screen ----------
VISION_MODEL = "qwen/qwen3.8-27b"  # the Groq model on this account that can see images
vision = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0)

def look_at_screen(question="What's on the screen?"):
    shot = ImageGrab.grab()
    shot.thumbnail((1280, 1280))  # smaller = faster upload
    buffer = io.BytesIO()
    shot.convert("RGB").save(buffer, "JPEG", quality=70)
    picture = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    reply = vision.chat.completions.create(model=VISION_MODEL, messages=[{"role": "user", "content": [
        {"type": "text", "text": f"This is a screenshot of the user's screen. {question} Answer briefly."},
        {"type": "image_url", "image_url": {"url": picture}}]}])
    answer = reply.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip() or "Couldn't make out the screen."
