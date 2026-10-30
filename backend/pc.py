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
import win32api
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
# The HUD, the floating window and the Live page (as an app window or a Chrome tab): never acted on
MIND_WINDOWS = {"M.I.N.D", "M.I.N.D mini", "M.I.N.D Live", "M.I.N.D Live - Google Chrome"}
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
    # Search, then LOOK at the results before opening anything (it used to press Enter blindly and
    # say "Chat's open" while WhatsApp showed "No chats, contacts or messages found")
    tried, results = [], []
    for search in [name] + name_variants(name):
        whatsapp_search(search)
        tried.append(search)
        results = whatsapp_results(hwnd)
        if results:
            break
    if results and same_person(name, results[0]):
        tap(0x0D)             # Enter: open the top result, which we checked is the right person
        time.sleep(1)
        if message:
            type_text(message)
            if send:
                tap(0x0D)
        result = f"Opened the WhatsApp chat with {results[0]}"
        return result + (" and sent the message." if message and send else " (message typed, not sent)." if message else ".")
    tap(0x1B)  # Esc: clear the search, open nothing
    if results:
        return (f"No WhatsApp chat matches '{name}'. Searching '{tried[-1]}' shows: {', '.join(results)}. "
                "Nothing was opened. Ask which one they meant.")
    return (f"WhatsApp found no chat for '{name}' (tried: {', '.join(tried)}). Nothing was opened. "
            "Ask them to say the name again.")

def whatsapp_search(text):
    tap_keys(0x11, 0x46)  # ctrl+f: search chats
    time.sleep(0.6)
    tap_keys(0x11, 0x41)  # ctrl+a: clear an old search
    type_text(text)
    time.sleep(1.5)       # wait for results

def whatsapp_results(hwnd):
    # The chat names WhatsApp's search shows (top first), read by looking at the window
    answer = look_at_window(hwnd, "This is WhatsApp after searching chats. If the left panel says 'No chats, "
                                  "contacts or messages found' or shows no results, answer exactly NONE. Otherwise "
                                  "answer ONLY the chat/contact names in the search results on the left, top to "
                                  "bottom, separated by ' | ' (at most 5). No other words.")
    if "NONE" in answer.upper():
        return []
    return [n.strip(" .*-\"'") for n in answer.split("|") if n.strip(" .*-\"'")][:5]

def same_person(asked, shown):
    # "siva chithappa" = "Siva Chithappa"; "jenny" = "Jenny Cousin"; "Shiva Kevalavadi IT" != "Siva Chithappa"
    a, b = squash(asked), squash(shown)
    return bool(a and b) and (a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75)

def name_variants(name):
    # The first name alone, and how Indian names are often spelled the other way (Shiva/Siva, Vijay/Wijay...)
    first = name.split()[0] if name.split() else ""
    found = [first] if first and first != name else []
    for a, b in (("sh", "s"), ("s", "sh"), ("v", "w"), ("w", "v"), ("th", "t"), ("ee", "i"), ("oo", "u")):
        if a in first.lower() and not (a == "s" and "sh" in first.lower()):  # (not "Shiva" -> "Shhiva")
            found.append(re.sub(a, b, first, count=1, flags=re.I))
    return [v for i, v in enumerate(found) if v and v.lower() not in (x.lower() for x in found[:i])][:3]

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
    return ask_eyes(ImageGrab.grab(), f"This is a screenshot of the user's screen. {question} Answer briefly.")

def look_at_window(hwnd, question):
    # Like look_at_screen, but only one window: smaller picture, so faster and fewer mistakes.
    # Used to CHECK what really happened before saying it worked ("Chat's open" was said when WhatsApp
    # showed "No chats, contacts or messages found").
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return ask_eyes(ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True), question)

def ask_eyes(shot, question):
    # Sends a picture to the vision model with a question; returns its answer
    shot.thumbnail((1280, 1280))  # smaller = faster upload
    buffer = io.BytesIO()
    shot.convert("RGB").save(buffer, "JPEG", quality=70)
    picture = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    reply = vision.chat.completions.create(model=VISION_MODEL, messages=[{"role": "user", "content": [
        {"type": "text", "text": question},
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

# When several profiles could match, M.I.N.D asks "Which Chrome? 1. ... 2. ..." and remembers the list,
# so "2" (or "the second one") picks one. The pick is saved, so the same words never ask again.
last_choices = {"said": "", "folders": [], "at": 0}
NUMBERS = {"one": 1, "first": 1, "two": 2, "second": 2, "three": 3, "third": 3, "four": 4, "fourth": 4,
           "five": 5, "fifth": 5, "six": 6, "sixth": 6, "last": -1}
PICKED = re.compile(r"^\W*(?:the\s+)?(?:number\s+|no\.?\s*)?(\d|one|two|three|four|five|six|first|second|third|"
                    r"fourth|fifth|sixth|last)(?:\s+one)?\W*$", re.I)

def picked_profile(want):
    # "2" / "number two" / "the second one" -> that profile from the last "Which Chrome?" list
    from memory import profile, save_profile
    picked = PICKED.match(want)
    if not picked or not last_choices["folders"]:
        return None
    word = picked.group(1).lower()
    n = int(word) if word.isdigit() else NUMBERS[word]
    if n == -1:  # "the last one"
        n = len(last_choices["folders"])
    if not 1 <= n <= len(last_choices["folders"]):
        return f"Pick a number from 1 to {len(last_choices['folders'])}."
    folder = last_choices["folders"][n - 1]
    if last_choices["said"]:  # remember it: next time these words open this profile straight away
        profile.setdefault("account_choices", {})[last_choices["said"]] = folder
        save_profile()
    return folder

def find_chrome_profile(want):
    # Best profile for an email or name (speech may be a bit off: "tigerboogipink" = "tigerboogipinky").
    # Returns (folder, name), or a message: a numbered "Which Chrome?" question, or why it can't.
    from memory import profile
    names = {folder: name for folder, name, _ in chrome_profiles()}
    picked = picked_profile(want)
    if isinstance(picked, str) and picked in names:
        return picked, names[picked]
    if picked:
        return picked
    said_words = [w for w in re.findall(r"[a-z]+", want.lower()) if len(w) >= 4 and w not in ("gmail", "account", "mail")]
    want = squash(want.replace(" at ", "@").replace(" dot ", "."))
    if not want:
        return "Say which Chrome account (its email or name)."
    chosen = profile.get("account_choices", {}).get(want)
    if chosen in names:  # they picked from a list for these words before
        return chosen, names[chosen]
    scored = []
    for folder, name, email in chrome_profiles():
        user = squash(email.split("@")[0])
        start = len(os.path.commonprefix([want, user])) if user else 0
        close = max(difflib.SequenceMatcher(None, want, squash(email)).ratio() if email else 0,
                    difflib.SequenceMatcher(None, want, user).ratio() if user else 0,
                    difflib.SequenceMatcher(None, want, squash(name)).ratio(),
                    # the whole email name inside what they said ("tigerboogipinky at gmail"), but not
                    # a short one inside a longer address ("pavithran" in "pavithran.vv.2019...")
                    1.0 if user and len(user) >= 5 and user in want and len(user) >= 0.6 * len(want) else 0)
        loose = max(  # the start heard right ("tigergojimayready" for "tigerboogipinky": speech mangles the end)
                    min(0.9, 0.2 + start / 7) if start >= 4 else 0,
                    # a word they said is inside the email ("my tiger account")
                    0.9 if user and any(w in user for w in said_words) else 0)
        scored.append((close, loose, folder, name, email))
    if not scored:
        return "No Chrome profiles found."
    # Loose guesses only when nothing is clearly close: "dolluzgit3" starts like dolluz.github1 too,
    # but it's much closer to dolluz.github3
    sure = max(s[0] for s in scored) >= 0.8
    scored = sorted(((close if sure else max(close, loose), folder, name, email)
                     for close, loose, folder, name, email in scored), key=lambda s: -s[0])  # ties keep Chrome's order
    if scored[0][0] >= 0.8 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.05):
        return scored[0][1], scored[0][2]
    options = [s for s in scored[:6] if s[0] >= 0.5 and s[0] >= scored[0][0] - 0.15]
    if options:
        last_choices.update(said=want, folders=[folder for _, folder, _, _ in options], at=time.time())
        listed = ", ".join(f"{i}. {name}" + (f" ({email.split('@')[0]})" if email else "")
                           for i, (_, _, name, email) in enumerate(options, 1))
        return f"Which Chrome? {listed}. Just say the number."
    return f"No Chrome profile like {want}. Profiles: {', '.join(sorted(set(names.values())))}."

def open_in_browser(url, account=""):
    # Opens a website in Chrome. With an account (email or profile name), in that Chrome profile's window;
    # otherwise in the Chrome profile used last (a new tab there). Never Windows' default browser:
    # that's Edge on this laptop, and "open a new chrome tab" once opened Edge's MSN page.
    # Returns None if it opened, or a message saying why not.
    import webbrowser
    import hud
    account = account or profile_default_account()
    chrome = hud.chrome_path()
    if not chrome:
        webbrowser.open(url)
        return None
    if not account:
        subprocess.Popen([chrome, url])
        return None
    found = find_chrome_profile(account)
    if isinstance(found, str):
        return found
    subprocess.Popen([chrome, f"--profile-directory={found[0]}", url])
    return None

def own_account_words():
    # The owner's own Chrome accounts' user names (profiles with their name on them), for the
    # Whisper hint, so "tigerboogipinky" isn't heard as "tigergojimayready". Never other people's.
    from memory import profile
    me = (profile.get("real_name") or "").lower()
    if not me:
        return []
    words = []
    for folder, name, email in chrome_profiles():
        if me in name.lower() and "@" in email:
            words += [w for w in re.split(r"[^a-z0-9]+", email.split("@")[0].lower()) if len(w) >= 5]
    return sorted(set(words))

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
                global last_front
                last_front = hwnd  # for scroll / screen_items / click
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

# ---------- Seeing and using things on screen: scroll, list what's clickable, click ----------
# Windows' accessibility system (what screen readers use) names every link and button on screen:
# the video titles on YouTube, "Skip ad", "Like", "Back"... No screenshots or logins needed.
last_front = None  # the last window in front that wasn't M.I.N.D's own (set by watch_activity)
CLICKABLE = {50005: "link", 50000: "button", 50007: "item", 50011: "menu item", 50019: "tab",
             50002: "checkbox", 50013: "option"}
# Buttons that could cost money, send something or lose data: only clicked if you SAID that word
RISKY = re.compile(r"delete|remove|send|pay|buy|purchase|checkout|order|sign out|log ?out|unsubscribe|"
                   r"uninstall|transfer|submit|post|publish|discard|erase|reset", re.I)
on_screen = []  # the last screen_items list: (name, centre point), for "click the second one"

def target_window():
    # The window you're using (not M.I.N.D's HUD or floating reactor)
    hwnd = win32gui.GetForegroundWindow()
    if hwnd and win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) not in MIND_WINDOWS:
        return hwnd
    return last_front if last_front and win32gui.IsWindow(last_front) else None

def automation():
    import comtypes
    import comtypes.client
    comtypes.CoInitialize()  # each thread needs this once (harmless to repeat)
    try:
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
    except ImportError:
        # A Windows update changed UIAutomationCore.dll, so the helper comtypes made from it is out of
        # date ("Typelib different than module", 2026-10-29: tabs, copy, grammar and the prompt
        # watcher all broke). Delete the old helper and let comtypes make it again.
        import sys
        import comtypes.gen
        folder = os.path.dirname(comtypes.gen.__file__)
        for name in ("UIAutomationClient", "_944DE083_8FB8_45CF_BCB7_C477ACB2F897_0_1_0"):
            sys.modules.pop("comtypes.gen." + name, None)
            try:
                os.remove(os.path.join(folder, name + ".py"))
            except OSError:
                pass
        print("Screen reader helper was out of date (Windows update), rebuilt it")
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
    return comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)

def clickables(hwnd, unique=True):
    # [(top, left, name, kind, element)] for every named, visible link/button/item in the window
    # (unique=False keeps repeated names, like the many "Copy" buttons in a chat)
    uia = automation()
    condition = None
    for type_id in CLICKABLE:
        this = uia.CreatePropertyCondition(30003, type_id)  # 30003 = control type
        condition = this if condition is None else uia.CreateOrCondition(condition, this)
    found = uia.ElementFromHandle(hwnd).FindAll(4, condition)  # 4 = everything inside the window
    items, seen = [], set()
    for i in range(found.Length):
        element = found.GetElement(i)
        try:
            name = " ".join((element.CurrentName or "").split())
            box = element.CurrentBoundingRectangle
            if (not name or (unique and name in seen) or element.CurrentIsOffscreen
                    or box.right <= box.left or box.bottom <= box.top):
                continue
            seen.add(name)
            items.append((box.top, box.left, name, CLICKABLE.get(element.CurrentControlType, ""), element))
        except Exception:
            continue
    items.sort(key=lambda x: (x[0] // 25, x[1]))  # top to bottom, then left to right
    return items

def screen_items(kind=""):
    # The screen_items tool: a numbered list of what can be clicked in the window you're using
    hwnd = target_window()
    if not hwnd:
        return "No window in front."
    items = clickables(hwnd)
    if kind == "videos":  # video links say how long they are or how many views they have
        items = [x for x in items if re.search(r"\b(views|watching)\b|\b\d+:\d\d\b|\b\d+ (minutes?|seconds?)\b", x[2], re.I)]
    items = items[:30]
    on_screen[:] = []
    for top, left, name, what, element in items:
        box = element.CurrentBoundingRectangle
        on_screen.append((name, ((box.left + box.right) // 2, (box.top + box.bottom) // 2)))
    if not items:
        return "Nothing like that on screen there. Maybe scroll, or it's still loading."
    lines = [f"{i}. {name[:110]} ({what})" for i, (_, _, name, what, _) in enumerate(items, 1)]
    return f"On screen in '{win32gui.GetWindowText(hwnd)[:60]}', top to bottom:\n" + "\n".join(lines)

def click(which):
    # The click tool: a number from the last screen_items list, or the name of a link/button
    import state
    which = str(which).strip()
    hwnd = target_window()
    if not hwnd:
        return "No window in front."
    words = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "last": len(on_screen)}
    number = int(which) if which.isdigit() else next((n for w, n in words.items() if w in which.lower()), None)
    name, point = (on_screen[number - 1] if number and 1 <= number <= len(on_screen) else (which, None))
    risky = RISKY.search(name)
    if risky and risky.group(0).lower() not in getattr(state, "last_user_text", "").lower():
        return f"Not clicked: '{name}' looks risky ({risky.group(0)}). Ask the user to say it clearly first."
    # Find it fresh by name (best match) and press it the way a screen reader would
    want = squash(name)
    best, best_score = None, 0
    for top, left, item_name, what, element in clickables(hwnd):
        have = squash(item_name)
        score = 1.0 if have == want else 0.9 if want and want in have else difflib.SequenceMatcher(None, want, have).ratio()
        if score > best_score:
            best, best_score = (item_name, element), score
    if best and best_score >= 0.6:
        item_name, element = best
        try:
            from comtypes.gen.UIAutomationClient import IUIAutomationInvokePattern
            element.GetCurrentPattern(10000).QueryInterface(IUIAutomationInvokePattern).Invoke()  # 10000 = Invoke
            return f"Clicked: {item_name[:80]}"
        except Exception:
            box = element.CurrentBoundingRectangle
            point = ((box.left + box.right) // 2, (box.top + box.bottom) // 2)
            name = item_name
    if not point:
        return f"Couldn't find '{which}' on screen. Use screen_items to see what's there (maybe scroll first)."
    mouse_click(point)
    return f"Clicked: {name[:80]}"

def mouse_click(point):
    # A real left click at a screen point (physical pixels, as the accessibility system gives them)
    user32.SetPhysicalCursorPos(point[0], point[1])
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # left button down
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # left button up

def scroll(direction="down", amount="little"):
    # The scroll tool: rolls the mouse wheel over the middle of the window you're using
    hwnd = target_window()
    if not hwnd:
        return "No window in front."
    if win32gui.GetForegroundWindow() != hwnd:
        bring_to_front(hwnd)  # (the HUD may be in front and would get the scrolling)
        time.sleep(0.3)
    if direction in ("top", "bottom"):
        tap_keys(0x24 if direction == "top" else 0x23)  # Home / End
        return f"Went to the {direction}."
    if amount in ("page", "lot"):
        # Page Down / Page Up move a whole screen (the mouse wheel moved Chrome only a little)
        for _ in range(3 if amount == "lot" else 1):
            tap_keys(0x22 if direction == "down" else 0x21)
            time.sleep(0.15)
        return f"Scrolled {direction} a {'lot' if amount == 'lot' else 'page'}."
    # A little: a few slow mouse-wheel clicks over the middle of the window
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    old = win32gui.GetCursorPos()
    user32.SetCursorPos((left + right) // 2, (top + bottom) // 2)
    for _ in range(4):
        user32.mouse_event(0x0800, 0, 0, -120 if direction == "down" else 120, 0)  # 0x0800 = wheel
        time.sleep(0.08)
    user32.SetCursorPos(*old)
    return f"Scrolled {direction} a little."

# ---------- Copy and paste ----------
# "Copy Claude's last answer and paste it in Notepad": chat sites (Claude, ChatGPT...) have a "Copy"
# button under each reply, so M.I.N.D presses the LAST one (exact text, nothing retyped). It can also
# copy text on screen that has some words, the page link, the selection, or text you say.
COPY_BUTTON = re.compile(r"copy( (message|response|reply|answer|text|to clipboard))?", re.I)
CTRL, KEY_C, KEY_V, KEY_L, ENTER, ESCAPE = 0x11, 0x43, 0x56, 0x4C, 0x0D, 0x1B

def clipboard_text():
    import win32clipboard
    for _ in range(10):  # another app may be using the clipboard for a moment
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.05)
    return ""

def set_clipboard(text):
    import win32clipboard
    for _ in range(10):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                return True
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.05)
    return False

def page_text(hwnd):
    # All the text of the page/app in the window, in reading order (via the screen-reader API)
    uia = automation()
    from comtypes.gen.UIAutomationClient import IUIAutomationTextPattern
    root = uia.ElementFromHandle(hwnd)
    document = root.FindFirst(4, uia.CreatePropertyCondition(30003, 50030)) or root  # 50030 = document
    try:
        pattern = document.GetCurrentPattern(10014).QueryInterface(IUIAutomationTextPattern)  # 10014 = text
        return pattern.DocumentRange.GetText(-1)
    except Exception:
        texts = root.FindAll(4, uia.CreatePropertyCondition(30003, 50020))  # 50020 = text pieces
        return "\n".join(texts.GetElement(i).CurrentName for i in range(texts.Length))

def copy(what="last_answer", words="", text=""):
    # The copy tool. Returns what was copied (the start of it), or why not.
    if what == "text" or (text and what != "words"):
        set_clipboard(text)
        return f"Copied: {text[:150]}"
    hwnd = target_window()
    if not hwnd:
        return "No window in front."
    before = clipboard_text()
    if what == "words" or words:
        # The paragraph(s) on screen that have the most of these words
        want = [w for w in re.findall(r"\w+", words.lower()) if len(w) > 2]
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\r?\n", page_text(hwnd)) if len(p.strip()) > 20]
        if not want or not paragraphs:
            return "Say some words from the text to copy."
        best = max(paragraphs, key=lambda p: sum(w in p.lower() for w in want))
        if not any(w in best.lower() for w in want):
            return f"Couldn't find text with '{words}' on screen."
        set_clipboard(best)
        return f"Copied ({len(best)} characters): {best[:150]}"
    if win32gui.GetForegroundWindow() != hwnd:
        bring_to_front(hwnd)  # pages only copy while their window is in front
        time.sleep(0.4)
    if what == "link":
        tap_keys(CTRL, KEY_L)
        time.sleep(0.15)
        tap_keys(CTRL, KEY_C)
        time.sleep(0.15)
        tap_keys(ESCAPE)
    elif what == "selection":
        tap_keys(CTRL, KEY_C)
    else:  # the last chat answer: press the bottom-most "Copy" button
        buttons = [x for x in clickables(hwnd, unique=False) if COPY_BUTTON.fullmatch(x[2]) and x[3] == "button"]
        if not buttons:
            return ("No 'Copy' button on screen. Scroll to the answer, or tell me some words from it "
                    "(copy with words).")
        top, left, name, kind, element = max(buttons, key=lambda x: (x[0], x[1]))
        try:
            from comtypes.gen.UIAutomationClient import IUIAutomationInvokePattern
            element.GetCurrentPattern(10000).QueryInterface(IUIAutomationInvokePattern).Invoke()
        except Exception:
            box = element.CurrentBoundingRectangle
            mouse_click(((box.left + box.right) // 2, (box.top + box.bottom) // 2))
    for _ in range(20):  # wait up to 2 s for the clipboard to change
        time.sleep(0.1)
        after = clipboard_text()
        if after and after != before:
            return f"Copied ({len(after)} characters): {after[:150]}"
    return "Nothing new was copied (the page may not allow it). Try again with the window in front."

def paste(where=""):
    # The paste tool: brings the named window (or the one you're using) to the front and pastes.
    # It only presses Enter if you said "send" or "enter" yourself.
    import state
    hwnd = None
    if where:
        for _ in range(25):  # an app opened just now (Notepad...) may need a few seconds
            found = [w for w in find_windows(where) if win32gui.IsWindowVisible(w[0])]
            if found:
                hwnd = found[0][0]
                break
            time.sleep(0.2)
        if not hwnd and tab_action(where, "switch").startswith("Switch"):
            hwnd = win32gui.GetForegroundWindow()  # it was a browser tab
        if not hwnd:
            return f"No open window called {where}. Open it first, then paste."
    else:
        hwnd = target_window()
    if not hwnd:
        return "No window to paste into."
    if not clipboard_text():
        return "The clipboard is empty: copy something first."
    bring_to_front(hwnd)
    time.sleep(0.4)
    if win32gui.GetForegroundWindow() != hwnd:
        return f"Couldn't bring {where or 'that window'} to the front, so I didn't paste (it could go to the wrong place)."
    tap_keys(CTRL, KEY_V)
    title = win32gui.GetWindowText(hwnd)[:50]
    if re.search(r"\b(send|enter|submit)\b", getattr(state, "last_user_text", ""), re.I):
        time.sleep(0.3)
        tap_keys(ENTER)
        return f"Pasted into {title} and pressed Enter."
    return f"Pasted into {title} (not sent)."

# ---------- Typing into a named box, and reading the screen ----------
TEXT_BOXES = {50004: "box", 50003: "combo box", 50030: "document"}  # edit / combo box / editable page area
WANTS_TYPING = re.compile(r"\b(type|write|enter|fill|search|put|input|paste|add|reply|message)\b", re.I)
WANTS_ENTER = re.compile(r"\b(search|send|enter|submit|go|find|look up)\b", re.I)
AI_CHAT_TITLE = re.compile(r"\b(Claude|ChatGPT|Gemini)\b", re.I)  # a window showing an AI chat
CHAT_ASKS = re.compile(r"\b(continue|ask|tell|reply|answer|send|carry on|keep going|go ahead)\b", re.I)
CHAT_BOX = re.compile(r"prompt|message|reply|ask|chat|write", re.I)  # an AI chat's own text box name

def type_into(box="", text=""):
    # The type_into tool: puts text into a box by its name ("Search", "Message", "Email"...) in the
    # window you're using, and presses Enter only if you said search/send/enter.
    import state
    said = getattr(state, "last_user_text", "")
    hwnd = target_window()
    # An AI chat (Claude/ChatGPT/Gemini): "continue in that chat" / "ask it..." means type AND send.
    # ("continue" alone used to be refused: it isn't a typing word.) Other apps keep the strict rule.
    asking_ai = bool(hwnd and AI_CHAT_TITLE.search(win32gui.GetWindowText(hwnd)) and CHAT_ASKS.search(said))
    if not WANTS_TYPING.search(said) and not asking_ai:
        return "Not typed: only type when the user asks to type, write, search or fill something."
    if not hwnd or not text:
        return "No window or no text."
    uia = automation()
    condition = None
    for type_id in TEXT_BOXES:
        this = uia.CreatePropertyCondition(30003, type_id)
        condition = this if condition is None else uia.CreateOrCondition(condition, this)
    found = uia.ElementFromHandle(hwnd).FindAll(4, condition)
    boxes = []
    for i in range(found.Length):
        element = found.GetElement(i)
        try:
            if element.CurrentIsOffscreen or not element.CurrentIsEnabled:
                continue
            if element.CurrentControlType == 50030 and not element.CurrentIsKeyboardFocusable:
                continue  # a normal page, not an editable one
            boxes.append(((element.CurrentName or "").strip(), element))
        except Exception:
            continue
    if not boxes:
        return "No box to type into in that window."
    want = squash(box)
    if want:
        scored = [(1.0 if squash(n) == want else 0.9 if want in squash(n) else
                   difflib.SequenceMatcher(None, want, squash(n)).ratio(), n, e) for n, e in boxes]
        score, name, element = max(scored, key=lambda x: x[0])
        prompt_boxes = [b for b in boxes if CHAT_BOX.search(b[0])] if AI_CHAT_TITLE.search(win32gui.GetWindowText(hwnd)) else []
        if score < 0.6 and prompt_boxes:
            name, element = prompt_boxes[-1]  # an AI chat's own prompt box ("Write your prompt to Claude")
        elif score < 0.6:
            return f"No box called {box}. Boxes here: {', '.join(n for n, _ in boxes[:8] if n) or 'unnamed ones'}."
    else:
        name, element = boxes[0]
    if win32gui.GetForegroundWindow() != hwnd:
        bring_to_front(hwnd)
        time.sleep(0.3)
    element.SetFocus()
    time.sleep(0.2)
    tap_keys(CTRL, 0x41)  # select what's already there (Ctrl+A), so the new text replaces it
    enter = bool(WANTS_ENTER.search(said)) or asking_ai
    type_text(text, press_enter=enter)
    return f"Typed into {name or 'the box'}" + (" and pressed Enter." if enter else " (Enter not pressed).")

def read_screen(about=""):
    # The read_screen tool: the text of the page/app you're using, for reading out or answering about it
    hwnd = target_window()
    if not hwnd:
        return "No window in front."
    text = re.sub(r"[ \t]+", " ", page_text(hwnd))
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 2]
    if about:  # just the parts about something
        want = [w for w in re.findall(r"\w+", about.lower()) if len(w) > 2]
        picked = [l for l in lines if any(w in l.lower() for w in want)]
        lines = picked or lines
    body = "\n".join(lines)
    if not body:
        return "Couldn't read any text there."
    title = win32gui.GetWindowText(hwnd)[:60]
    return f"Text of '{title}'" + (" (cut)" if len(body) > 3500 else "") + ":\n" + body[:3500]

# ---------- Doing things without disturbing your work ----------
# Music opens in its own minimized Chrome window, and after WhatsApp sends something the window
# you were working in comes back to the front, so VS Code / your tab stays where you left it.
def give_back(hwnd):
    # Put the window you were using back in front (after WhatsApp or a new window popped up)
    if hwnd and win32gui.IsWindow(hwnd) and win32gui.GetForegroundWindow() != hwnd:
        time.sleep(0.2)
        bring_to_front(hwnd)

def chrome_windows():
    return [w[0] for w in open_windows() if w[2].lower() == "chrome"]

def new_chrome_tab(profile_folder=""):
    # A real new tab (Chrome's New Tab page with Google search), like pressing Ctrl+T yourself.
    # about:blank looked like a broken black page, and Chrome won't open its New Tab page from the command line.
    import hud
    chrome = hud.chrome_path()
    if profile_folder:  # that account: a window of its own, on its New Tab page
        subprocess.Popen([chrome, f"--profile-directory={profile_folder}"])
        return None
    windows = [h for h in chrome_windows() if win32gui.GetWindowText(h) not in MIND_WINDOWS]
    if last_front in windows:
        windows.insert(0, last_front)  # the Chrome window you were just using
    if not windows:
        subprocess.Popen([chrome])
        return None
    hwnd = windows[0]
    # (Alt-to-front when it's ALREADY in front moves Chrome's focus to its menu, so only when needed)
    if win32gui.GetForegroundWindow() != hwnd and not bring_to_front(hwnd):
        return "Couldn't bring Chrome to the front to open a tab."
    press_keys("ctrl+t")
    return None

QUIET_SIZE = (360, 240)    # the little window shown in the bottom-right corner while the song loads
QUIET_MAX_WAIT = 15        # seconds to wait for the sound before minimizing anyway
music_window = {"hwnd": None}  # the little window the last song opened in (closed when the next song opens)

def open_quietly(url, profile_folder=""):
    # Opens a page in its OWN Chrome window without disturbing your work:
    # it sits small in the bottom-right corner until the sound starts, then minimizes.
    # (Chrome won't start a video in a window that was never on screen, so it can't start minimized.)
    # Your window gets the keyboard back right away. Returns False if Chrome isn't there.
    import hud, audio
    chrome = hud.chrome_path()
    if not chrome:
        return False
    mine = target_window()
    # Only ONE music window: the old song's window (opened by M.I.N.D) is closed first
    old = music_window["hwnd"]
    if old and win32gui.IsWindow(old) and "youtube" in win32gui.GetWindowText(old).lower():
        win32gui.PostMessage(old, win32con.WM_CLOSE, 0, 0)
        for _ in range(20):  # wait up to 2 s for it to go (and its sound with it)
            if not win32gui.IsWindow(old):
                break
            time.sleep(0.1)
    if audio.chrome_playing():  # an old song in a tab: pause it, so two don't play at once
        win32api.keybd_event(0xB3, 0, 0, 0)  # media play/pause key
        win32api.keybd_event(0xB3, 0, 2, 0)
        time.sleep(0.4)
    already_playing = audio.chrome_playing()  # (then the sound can't tell us when the new song starts)
    titles = {h: win32gui.GetWindowText(h) for h in chrome_windows()}
    folder = [f"--profile-directory={profile_folder}"] if profile_folder else []
    # No --new-window: if that account already has a window, Chrome adds a TAB there (like Ctrl+T)
    subprocess.Popen([chrome] + folder + [url])
    new = None
    for _ in range(70):  # wait up to ~7 s
        time.sleep(0.1)
        fresh = [h for h in chrome_windows() if h not in titles]
        if fresh:
            new = fresh[0]  # that account had no window open: Chrome made one
            break
        front = win32gui.GetForegroundWindow()
        if front in titles and win32gui.GetWindowText(front) != titles[front]:
            # It went into your open window as a new tab. Keep it in front a moment: Chrome only
            # starts a video in a tab that has been on screen. Then your window comes back.
            for _ in range(30):
                if "youtube" in win32gui.GetWindowText(front).lower() or "youtube" not in url:
                    break
                time.sleep(0.1)
            time.sleep(1.0)
            music_window["hwnd"] = None  # (a tab in your window: never closed by M.I.N.D)
            give_back(mine)
            return True
    if not new:
        give_back(mine)
        return True
    music_window["hwnd"] = new
    width, height = QUIET_SIZE
    right, bottom = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
    win32gui.SetWindowPos(new, win32con.HWND_TOPMOST, right - width - 12, bottom - height - 60, width, height,
                          win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW)
    give_back(mine)
    threading.Thread(target=hide_when_playing, args=(new, already_playing), daemon=True).start()
    return True

def hide_when_playing(window, already_playing):
    # Minimize the little music window once it makes sound (or after QUIET_MAX_WAIT)
    import audio
    start = time.time()
    while time.time() - start < QUIET_MAX_WAIT and win32gui.IsWindow(window):
        if time.time() - start > (5 if already_playing else 1) and (already_playing or audio.chrome_playing()):
            break
        time.sleep(0.3)
    if win32gui.IsWindow(window):
        time.sleep(0.5)  # let playback settle before hiding it
        win32gui.SetWindowPos(window, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        win32gui.ShowWindow(window, 7)  # SW_SHOWMINNOACTIVE: minimized, without taking the keyboard
