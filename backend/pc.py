# PC control: typing, keyboard shortcuts, closing apps, PC health, locking, and looking at the screen.
# These are used as tools by the brain (see TOOLS in tools.py).
import io
import json
import os
import re
import time
import base64
import ctypes
import threading
import subprocess
from ctypes import wintypes
from collections import deque
import difflib
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

HUD_TITLE = "M.I.N.D"  # the HUD's browser tab title
MIND_WINDOWS = {"M.I.N.D", "M.I.N.D mini"}  # the HUD and the floating window
CLOSING_KEYS = {"ctrl+w", "ctrl+f4", "alt+f4", "ctrl+shift+w"}

def front_title():
    return win32gui.GetWindowText(win32gui.GetForegroundWindow())

def press_keys(keys):
    # keys like "ctrl+w", "alt+tab", "win+d"
    keys = keys.lower().replace(" ", "")
    codes = [key_code(k) for k in keys.split("+")]
    if None in codes or not codes:
        return f"Don't know the keys '{keys}'."
    if keys in CLOSING_KEYS and front_title().startswith(HUD_TITLE):
        # It would close M.I.N.D's own HUD (it once did, on "close the YouTube tab")
        return "Not done: the M.I.N.D HUD is in front. Use close_tab or close_app instead."
    for c in codes:
        user32.keybd_event(c, 0, 0, 0)
    for c in reversed(codes):
        user32.keybd_event(c, 0, KEY_UP, 0)
    return f"Pressed {keys}."

# ---------- Browser tabs ----------
BROWSERS = {"chrome", "msedge", "firefox", "brave", "opera"}

def bring_to_front(hwnd):
    # Windows only lets a program bring a window to the front after a key press
    user32.keybd_event(0x12, 0, 0, 0)       # Alt down
    user32.keybd_event(0x12, 0, KEY_UP, 0)  # Alt up
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.3)
    return win32gui.GetForegroundWindow() == hwnd

def close_tab(name):
    # Goes through the tabs of every browser window (the window title shows the open tab)
    # and closes the ones whose title contains 'name'. Never closes the M.I.N.D HUD.
    want, closed = name.lower().strip(), 0
    for hwnd, pid, app, title in open_windows():
        if app.lower() not in BROWSERS or not bring_to_front(hwnd):
            continue
        seen = []  # tab titles visited since the last close
        for _ in range(40):
            if win32gui.GetForegroundWindow() != hwnd:
                break  # the window closed (last tab) or something else came in front
            title = win32gui.GetWindowText(hwnd)
            if want in title.lower() and not title.startswith(HUD_TITLE):
                tap_keys(0x11, 0x57)  # ctrl+w
                closed += 1
                seen = []
                time.sleep(0.4)
                continue
            if title in seen:
                break  # went all the way round
            seen.append(title)
            tap_keys(0x11, 0x09)  # ctrl+tab: next tab
            time.sleep(0.25)
    return f"Closed {closed} tab(s) with '{name}'." if closed else f"No open tab with '{name}' in its title."

TABS_SCRIPT = """
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$tab = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::TabItem)
$out = @()
foreach ($h in @(HANDLES)) {
  $w = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$h)
  foreach ($t in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $tab)) { $out += $t.Current.Name }
}
ConvertTo-Json @($out)
"""

def list_tabs():
    # Titles of all open browser tabs, in order (read with Windows' accessibility interface)
    windows = [w[0] for w in open_windows() if w[2].lower() in BROWSERS and w[3] not in MIND_WINDOWS]
    if not windows:
        return "No browser is open."
    out = subprocess.run(["powershell", "-NoProfile", "-Command", TABS_SCRIPT.replace("HANDLES", ",".join(map(str, windows)))],
                         capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20,
                         creationflags=subprocess.CREATE_NO_WINDOW).stdout
    tabs = [t for t in json.loads(out or "[]") if t and t not in MIND_WINDOWS]
    if not tabs:
        return "No browser tabs found."
    return "Open tabs, in order: " + "; ".join(f"{i}. {t}" for i, t in enumerate(tabs, 1))

def tab_action(name, action="switch"):
    # Finds the first tab whose title has 'name' (by going through the tabs) and switches to it,
    # pauses/plays it (YouTube's "k" key) or closes it
    want = name.lower().strip()
    for hwnd, pid, app, title in open_windows():
        if app.lower() not in BROWSERS or title in MIND_WINDOWS or not bring_to_front(hwnd):
            continue
        seen = []
        for _ in range(40):
            title = win32gui.GetWindowText(hwnd)
            if want in title.lower() and not title.startswith(HUD_TITLE):
                if action == "close":
                    tap_keys(0x11, 0x57)  # ctrl+w
                elif action in ("pause", "play"):
                    tap(0x4B)  # "k": YouTube's play/pause key
                return f"{action.capitalize()}: {title.rsplit(' - ', 1)[0]}"
            if title in seen:
                break
            seen.append(title)
            tap_keys(0x11, 0x09)  # next tab
            time.sleep(0.25)
    return f"No open tab with '{name}' in its title."

def tap_keys(*codes):
    for c in codes:
        user32.keybd_event(c, 0, 0, 0)
    for c in reversed(codes):
        user32.keybd_event(c, 0, KEY_UP, 0)

# ---------- Folders and projects ----------
HOME = os.path.expanduser("~")
FOLDER_ROOTS = [os.path.join(HOME, d) for d in ("Desktop", "Documents", "Downloads", "source", "projects")]
SKIP_FOLDERS = {"node_modules", "venv", "__pycache__", "dist", "build", "site-packages"}
VSCODE = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Microsoft VS Code\Code.exe")
folders = []  # every folder under Desktop, Documents... (made in the background, ~5 seconds)

def index_folders():
    found = [r for r in FOLDER_ROOTS if os.path.isdir(r)]  # Desktop, Downloads... themselves
    for root in FOLDER_ROOTS:
        for path, subfolders, _ in os.walk(root):
            depth = path[len(root):].count(os.sep)
            subfolders[:] = ([d for d in subfolders if d not in SKIP_FOLDERS and not d.startswith(".")]
                             if depth < 6 else [])
            found += [os.path.join(path, d) for d in subfolders]
    folders[:] = found

def keep_indexing(minutes=15):
    # Scan again every 15 minutes, so new folders and projects are known without restarting
    while True:
        try:
            index_folders()
        except Exception as e:
            print("Folder scan failed:", e)
        time.sleep(minutes * 60)

threading.Thread(target=keep_indexing, daemon=True).start()

FOLDER_FILLER = re.compile(r"\b(the|my|project|projects|folder|repo|in|vs|code|vscode|open)\b", re.I)

def find_folder(name):
    # Best folder for a name: exact name first ("mind" = "M.I.N.D"), then projects, then shorter paths.
    # Words like "project" or "folder" are left out ("dai project" = "dai")
    name = FOLDER_FILLER.sub(" ", name).strip() or name
    want = squash(name)
    if not folders:
        index_folders()
    matches = [f for f in folders if want and (squash(os.path.basename(f)) == want
                                               or (len(want) >= 4 and want in squash(os.path.basename(f))))]
    def score(f):
        exact = squash(os.path.basename(f)) == want
        project = any(os.path.exists(os.path.join(f, m)) for m in (".git", "package.json", "main.py", "CLAUDE.md"))
        return (not exact, not project, f.count(os.sep))
    return sorted(matches, key=score)

def projects():
    # Folders that are code projects (they have .git or package.json), newest first
    found = [f for f in folders if any(os.path.exists(os.path.join(f, m)) for m in (".git", "package.json"))]
    return sorted(found, key=lambda f: -os.path.getmtime(f))

def project_names(limit=25):
    names = []
    for f in projects():
        name = os.path.basename(f)
        if name.lower() not in (n.lower() for n in names):
            names.append(name)
    return names[:limit]

def open_folder(name, open_with="vscode"):
    matches = find_folder(name)
    if not matches:
        index_folders()  # maybe it's brand new: scan again right now
        matches = find_folder(name)
    if not matches:
        # Maybe misheard ("the fresh" = dfresh): open the closest project only if it's clearly the one
        short = FOLDER_FILLER.sub(" ", name).strip() or name
        scored = sorted(((difflib.SequenceMatcher(None, squash(short), squash(os.path.basename(p))).ratio(), p)
                         for p in projects()), reverse=True)
        if scored and scored[0][0] >= 0.75 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.15):
            matches = [scored[0][1]]
        else:
            closest = ", ".join(os.path.basename(p) for _, p in scored[:3])
            return f"No folder called {name}. Closest projects: {closest}. Ask which one they meant."
    folder = matches[0]
    if open_with == "explorer" or not os.path.exists(VSCODE):
        os.startfile(folder)
    else:
        subprocess.Popen([VSCODE, folder])
        project = os.path.basename(folder).lower()
        for _ in range(30):  # wait up to 15 seconds for its window
            time.sleep(0.5)
            found = [w for w in open_windows() if "visual studio code" in w[3].lower() and project in w[3].lower()]
            if found:
                win32gui.ShowWindow(found[0][0], win32con.SW_MAXIMIZE)  # full size
                bring_to_front(found[0][0])
                break
    others = f" Other matches: {', '.join(matches[1:3])}." if len(matches) > 1 else ""
    return f"Opened {folder} in {'File Explorer' if open_with == 'explorer' else 'VS Code'}.{others}"

# ---------- WhatsApp ----------
def whatsapp_window():
    for hwnd, pid, app, title in open_windows():
        if app == "WhatsApp.Root" or title == "WhatsApp":
            return hwnd
    return None

def whatsapp_chat(name, message="", send=False, phone=""):
    # Opens WhatsApp on someone's chat. With their number it's exact (a WhatsApp link);
    # without, it searches the name in WhatsApp and opens the top result.
    # A message is typed in; it's only sent when send=True (you clearly said "send").
    from urllib.parse import quote
    if phone:
        os.startfile(f"whatsapp://send?phone={phone}&text={quote(message)}")
        time.sleep(3)
        hwnd = whatsapp_window()
        if send and hwnd and bring_to_front(hwnd):
            tap(0x0D)
        return f"Opened {name}'s chat" + (" and sent the message." if send else (" with the message typed." if message else "."))
    hwnd = whatsapp_window()
    if not hwnd:
        os.startfile("whatsapp:")  # open WhatsApp
        for _ in range(20):
            time.sleep(0.5)
            hwnd = whatsapp_window()
            if hwnd:
                break
        time.sleep(2)  # let it finish loading
    if not hwnd or not bring_to_front(hwnd):
        return "Couldn't bring WhatsApp to the front."
    tap_keys(0x11, 0x46)  # ctrl+f: search chats
    time.sleep(0.6)
    tap_keys(0x11, 0x41)  # ctrl+a: clear an old search
    type_text(name)
    time.sleep(1.5)       # wait for results
    tap(0x0D)             # Enter: open the top result
    time.sleep(1)
    if message:
        type_text(message)
        if send:
            tap(0x0D)
    result = f"Searched WhatsApp for {name} and opened the top chat"
    return result + (" and sent the message." if message and send else " (message typed, not sent)." if message else ".")

# ---------- Windows: switch to, minimize, maximize ----------
def find_windows(name):
    want = squash(name)
    windows = [w for w in open_windows() if w[3] not in MIND_WINDOWS]
    match = [w for w in windows if want and want in squash(w[2])]
    return match or [w for w in windows if want and want in squash(w[3])]

def window_action(name, action="focus"):
    match = find_windows(name)
    if not match:
        apps = sorted({w[2] for w in open_windows() if w[2].lower() not in ("explorer", "textinputhost")})
        return f"No open window called {name}. Open apps: {', '.join(apps)}."
    if action == "minimize":
        for hwnd, *_ in match:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        return f"Minimized {len(match)} window(s)."
    hwnd = match[0][0]
    if action == "maximize":
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    bring_to_front(hwnd)
    return f"{'Maximized' if action == 'maximize' else 'Switched to'} {match[0][3]}."

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
    windows = [w for w in open_windows() if w[3] not in MIND_WINDOWS]  # never the M.I.N.D HUD window
    # Match the app's name first ("chrome"), then window titles ("YouTube")
    match = [w for w in windows if want and want in squash(w[2])]
    if not match:
        match = [w for w in windows if want and want in squash(w[3])]
        if match and all(w[2].lower() in BROWSERS for w in match):
            # "Close YouTube" = a website in a browser tab: close only that tab, never the
            # whole browser window (it once closed every Chrome tab this way)
            return tab_action(name, "close")
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
psutil.cpu_percent(interval=None)  # start measuring CPU now, so later checks are instant

def system_info(include_apps=False):
    include_apps = include_apps in (True, "yes", "true")
    parts = []
    battery = psutil.sensors_battery()
    if battery:
        charging = "charging" if battery.power_plugged else "not charging"
        parts.append(f"Battery {round(battery.percent)}%, {charging}")
        if not battery.power_plugged and battery.secsleft > 0:
            parts[-1] += f", about {battery.secsleft // 3600}h {battery.secsleft % 3600 // 60}m left"
    parts.append(f"CPU {psutil.cpu_percent(interval=None)}% busy")
    ram = psutil.virtual_memory()
    parts.append(f"RAM {ram.percent}% used ({ram.available / 2**30:.1f} GB free of {ram.total / 2**30:.0f} GB)")
    disk = psutil.disk_usage("C:\\")
    parts.append(f"C: drive {disk.free / 2**30:.0f} GB free")
    if not include_apps:
        return ". ".join(parts) + "."
    # Apps using the most memory (slower: checks every running program)
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

# ---------- Chrome profiles (one per Google account) ----------
# "Open YouTube with my tigerboogipink mail" -> that account's own Chrome window.
# Chrome lists its profiles (folder, name, email) in its "Local State" settings file.
CHROME_STATE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data", "Local State")

def chrome_profiles():
    # [(folder, name, email)], e.g. ("Profile 2", "Pavithran", "someone@gmail.com")
    try:
        with open(CHROME_STATE, encoding="utf-8") as f:
            cache = json.load(f)["profile"]["info_cache"]
    except (OSError, ValueError, KeyError):
        return []
    return [(folder, p.get("shortcut_name") or p.get("name", ""), p.get("user_name", "")) for folder, p in cache.items()]

def find_chrome_profile(want):
    # Best profile for an email or name (speech may be a bit off: "tigerboogipink" = "tigerboogipinky").
    # Returns (folder, name), or an error message for the brain (names only: never other people's emails).
    want = squash(want.replace(" at ", "@").replace(" dot ", "."))
    if not want:
        return "Say which Chrome account (its email or name)."
    scored = []
    for folder, name, email in chrome_profiles():
        user = squash(email.split("@")[0])
        score = max(difflib.SequenceMatcher(None, want, squash(email)).ratio() if email else 0,
                    difflib.SequenceMatcher(None, want, user).ratio() if user else 0,
                    difflib.SequenceMatcher(None, want, squash(name)).ratio(),
                    1.0 if user and len(user) >= 5 and user in want else 0)
        scored.append((score, folder, name))
    scored.sort(reverse=True)
    if not scored:
        return "No Chrome profiles found."
    if scored[0][0] >= 0.8 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.05):
        return scored[0][1], scored[0][2]
    close = [name for score, _, name in scored[:4] if score >= 0.5]
    if close:
        return f"Several Chrome profiles could match: {', '.join(close)}. Ask which one (the email works best)."
    return f"No Chrome profile like {want}. Profiles: {', '.join(sorted({n for _, _, n in scored}))}."

def open_in_browser(url, account=""):
    # Opens a website. With an account (email or profile name), in that Chrome profile's window;
    # otherwise in the browser you used last (a new tab there).
    # Returns None if it opened, or a message saying why not.
    import webbrowser
    import hud
    account = account or profile_default_account()
    if not account:
        webbrowser.open(url)
        return None
    found = find_chrome_profile(account)
    if isinstance(found, str):
        return found
    chrome = hud.chrome_path()
    if not chrome:
        webbrowser.open(url)
        return None
    subprocess.Popen([chrome, f"--profile-directory={found[0]}", url])
    return None

def profile_default_account():
    # "Always use my tigerboogipink account" (saved as chrome_account in profile.json)
    from memory import profile
    return profile.get("chrome_account", "")

# ---------- What you're doing: the window in front, over time ----------
# Every 3 seconds, notes which window (and so which browser tab) is in front when it changes.
# Kept in memory only (3,000 changes, a few hours), for "what was I doing?" and "the tab I just closed".
activity = deque(maxlen=3000)  # (time, app, title)
app_names = {}  # process id -> app name

def window_app(hwnd):
    pid = win32process.GetWindowThreadProcessId(hwnd)[1]
    if pid not in app_names:
        try:
            app_names[pid] = psutil.Process(pid).name().removesuffix(".exe")
        except psutil.Error:
            return ""
    return app_names[pid]

def watch_activity():
    last = None
    while True:
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd).strip()
            if title and title not in MIND_WINDOWS and title not in NEVER_CLOSE and title != "Task Switching":
                app = window_app(hwnd)
                if app and (app, title) != last:
                    last = (app, title)
                    activity.append((time.time(), app, title))
        except Exception:
            pass
        time.sleep(3)

def short_title(app, title):
    # "Rathinamo - YouTube - Google Chrome" -> "Chrome: Rathinamo - YouTube"
    title = re.sub(r"\s+[-–—]\s+(Google Chrome|Microsoft Edge|Mozilla Firefox|Visual Studio Code)$", "", title)
    nice = {"chrome": "Chrome", "msedge": "Edge", "Code": "VS Code", "WhatsApp.Root": "WhatsApp"}.get(app, app)
    return f"{nice}: {title[:90]}"

def in_front():
    # What you're looking at right now (the last window that wasn't M.I.N.D's own)
    return short_title(*activity[-1][1:]) if activity else ""

def activity_report(about="", start=None, end=None):
    # What was in front, and for how long, between start and end (default: the last hour)
    end = end or time.time() + 1
    start = start or end - 3600
    items = [a for a in activity if start <= a[0] < end]
    words = [w for w in re.findall(r"\w+", about.lower()) if len(w) > 2]
    lines = []
    for i, (t, app, title) in enumerate(items):
        stay = (items[i + 1][0] if i + 1 < len(items) else time.time()) - t
        if words and not any(w in f"{app} {title}".lower() for w in words):
            continue
        if stay < 6 and not words:
            continue  # just passing through (alt-tab)
        minutes = f"{round(stay / 60)} min" if stay >= 90 else f"{round(stay)} s"
        lines.append(f"{time.strftime('%I:%M %p', time.localtime(t)).lstrip('0')} ({minutes}): {short_title(app, title)}")
    if not lines:
        return "Nothing like that on screen in that time." if words else "No activity noted in that time."
    return ("On screen (window or browser tab in front, oldest first):\n" + "\n".join(lines[-15:])
            + "\nTo reopen a closed browser tab: press_keys ctrl+shift+t with the browser in front.")

threading.Thread(target=watch_activity, daemon=True).start()

# ---------- Is the app OK? (after opening it) ----------
# WhatsApp once opened as a plain black window. After an app opens, M.I.N.D looks at its window:
# not opening, frozen ("not responding") or all black/blank is reported, with a way to fix it.
def window_problem(hwnd):
    if ctypes.windll.user32.IsHungAppWindow(hwnd):
        return "is frozen (not responding)"
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right - left < 200 or bottom - top < 150 or win32gui.IsIconic(hwnd):
            return None  # tiny or minimized: can't judge
        shot = ImageGrab.grab(bbox=(left + 8, top + 40, right - 8, bottom - 8)).convert("L")
        counts = shot.histogram()  # how many pixels of each brightness (0 = black ... 255 = white)
        main = max(range(256), key=lambda v: counts[v])  # the most common brightness
        same = sum(counts[max(0, main - 10):main + 11]) / max(1, sum(counts))
        if same > 0.97:  # almost all one colour: nothing is drawn in the window
            return "shows a blank black screen" if main < 40 else "shows a blank screen"
    except Exception:
        return None
    return None

def on_top_at_center(hwnd):
    # Is this window the one you'd see in the middle of it (not covered by another window)?
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    seen = win32gui.WindowFromPoint(((left + right) // 2, (top + bottom) // 2))
    return seen and win32gui.GetAncestor(seen, win32con.GA_ROOT) == hwnd

def check_app(name, report):
    # Runs in the background after opening an app; report(problem) tells the user
    want = squash(name)
    time.sleep(6)
    windows = []
    for _ in range(10):  # wait up to ~16 s for its window
        windows = [w for w in open_windows() if want in squash(w[3]) or want in squash(w[2])]
        if windows:
            break
        time.sleep(1)
    if not windows:
        report(f"{name} didn't open a window")
        return
    for hwnd, *_ in windows:
        if not on_top_at_center(hwnd) and not ctypes.windll.user32.IsHungAppWindow(hwnd):
            continue  # another window covers it: can't judge from a screenshot
        problem = window_problem(hwnd)
        if problem:
            time.sleep(6)  # maybe it was just a loading screen: look again
            problem = window_problem(hwnd) if win32gui.IsWindow(hwnd) else None
        if problem:
            report(f"{name} opened but it {problem}")
            return

# ---------- Files: find them and open them (only in your own folders, never changes anything) ----------
FILE_ROOTS = [os.path.join(HOME, d) for d in ("Downloads", "Desktop", "Documents", "Pictures", "Videos", "Music", "OneDrive")]
KINDS = {
    "pdf": (".pdf",), "document": (".doc", ".docx", ".txt", ".rtf", ".odt", ".md"),
    "sheet": (".xls", ".xlsx", ".csv", ".ods"), "slides": (".ppt", ".pptx", ".odp"),
    "image": (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"),
    "video": (".mp4", ".mkv", ".mov", ".avi", ".webm"), "audio": (".mp3", ".wav", ".m4a", ".aac", ".flac"),
    "zip": (".zip", ".rar", ".7z", ".tar", ".gz"),
}
found_files = []  # the last find_files list, so "open the second one" works

def find_files(name="", kind="", when=""):
    import diary
    words = [w for w in re.findall(r"\w+", name.lower()) if w not in ("the", "a", "my", "file", "files")]
    endings = KINDS.get(kind)
    start, end = diary.period(when) if when else (0, time.time() + 1)
    hits, stop_at = [], time.time() + 4  # look for at most 4 seconds
    for root in FILE_ROOTS:
        for path, subfolders, files in os.walk(root):
            depth = path[len(root):].count(os.sep)
            subfolders[:] = [] if depth >= 5 else [s for s in subfolders
                                                   if s not in SKIP_FOLDERS and not s.startswith(".")]
            for f in files:
                low = f.lower()
                if (endings and not low.endswith(endings)) or not all(w in low for w in words):
                    continue
                full = os.path.join(path, f)
                try:
                    changed = os.path.getmtime(full)
                except OSError:
                    continue
                if start <= changed < end:
                    hits.append((changed, full))
            if time.time() > stop_at:
                break
    hits.sort(reverse=True)
    found_files[:] = [p for _, p in hits[:10]]
    if not found_files:
        return "No files like that found (looked in Downloads, Desktop, Documents, Pictures, Videos, Music)."
    lines = []
    for i, path in enumerate(found_files, 1):
        days = (time.time() - os.path.getmtime(path)) / 86400
        age = "today" if days < 1 else "yesterday" if days < 2 else f"{int(days)} days ago"
        size = os.path.getsize(path) / 2**20
        lines.append(f"{i}. {os.path.basename(path)} ({os.path.basename(os.path.dirname(path))}, {age}, {size:.1f} MB)")
    return f"Found {len(hits)} file(s), newest first:\n" + "\n".join(lines)

def open_file(which):
    # "1" / "the second one" from the last list, or a file name
    which = str(which).strip()
    numbers = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": len(found_files)}
    number = int(which) if which.isdigit() else next((n for w, n in numbers.items() if w in which.lower()), None)
    if number and 1 <= number <= len(found_files):
        path = found_files[number - 1]
    else:
        if not found_files or not any(squash(which) in squash(os.path.basename(p)) for p in found_files):
            find_files(which)
        path = next((p for p in found_files if squash(which) in squash(os.path.basename(p))), found_files[0] if found_files else None)
    if not path or not os.path.isfile(path):
        return f"Couldn't find a file called {which}."
    if not os.path.abspath(path).lower().startswith(HOME.lower()):
        return "I only open files from your own folders."
    os.startfile(path)  # opens with its usual app (PDF reader, Word, Photos...)
    return f"Opened {os.path.basename(path)}."

def repair_app(name, app_id):
    # Opens Windows' own Repair/Reset page for a Store app (like WhatsApp). Repair keeps your data.
    if "!" not in app_id:
        return f"{name} isn't a Store app, so there's no Repair page. Try reinstalling it."
    os.startfile(f"ms-settings:appsfeatures-app?{app_id.split('!')[0]}")
    return f"Opened the Repair page for {name}. 'Repair' keeps your data; 'Reset' signs you out."
