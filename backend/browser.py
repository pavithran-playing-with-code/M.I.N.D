# What the M.I.N.D Chrome extension (../extension) tells us about Chrome:
# every tab in every window of every profile that has it, and each AI chat's state
# (Claude / ChatGPT / Gemini: running or done, and the latest answer), even in background tabs.
# The extension POSTs to /api/browser (server.py); only requests from an extension are accepted.
import os
import json
import time
import hashlib
import threading
from memory import BASE_DIR

FRESH_SECONDS = 150  # a profile that hasn't reported for this long is treated as closed

lock = threading.Lock()
profiles = {}  # extension id per profile -> {"seen": time, "tabs": [...], "chats": {tab id: chat}}

EXTENSION = os.path.join(os.path.dirname(BASE_DIR), "extension")
FILES = ["manifest.json", "background.js", "chat.js"]  # the same files the extension fingerprints
reload_wanted = set()  # profiles told to reload on their next report ("Mind, reload the extension")
last_reload = {}       # profile -> time it was told to reload (never more than once in 10 min)

def code_hash():
    # Fingerprint of the extension files on disk (SHA-256 of their text, like background.js does)
    text = ""
    for name in FILES:
        with open(os.path.join(EXTENSION, name), encoding="utf-8", newline="") as f:
            text += f.read()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def report(data):
    # One report from one Chrome profile: {"profile", "tabs": [...]} or {"profile", "chat": {...}}.
    # Returns what to tell the extension back: {"reload": True} when its code is old (or you asked).
    who = str(data.get("profile", ""))[:40]
    if not who:
        return {}
    answer = {}
    outdated = data.get("code") and data["code"] != code_hash()
    if who in reload_wanted or (outdated and time.time() - last_reload.get(who, 0) > 600):
        last_reload[who] = time.time()
        reload_wanted.discard(who)
        answer["reload"] = True
    with lock:
        entry = profiles.setdefault(who, {"seen": 0, "tabs": [], "chats": {}})
        entry["seen"] = time.time()
        if "tabs" in data:
            entry["tabs"] = data["tabs"][:300]
            open_tabs = {t.get("id") for t in entry["tabs"]}
            entry["chats"] = {k: v for k, v in entry["chats"].items() if k in open_tabs}  # closed tabs go
        chat = data.get("chat")
        if chat and chat.get("tab") is not None:
            chat["seen"] = time.time()
            entry["chats"][chat["tab"]] = chat
    return answer

def active():
    # True if at least one Chrome profile with the extension is reporting
    return any(time.time() - p["seen"] < FRESH_SECONDS for p in profiles.values())

def chats():
    # [{"key", "site", "title", "running", "reply", "prompt", "tab", "window", "profile"}] from live profiles
    found = []
    with lock:
        for who, entry in profiles.items():
            if time.time() - entry["seen"] > FRESH_SECONDS:
                continue
            for tab, chat in entry["chats"].items():
                found.append(dict(chat, key=f"ext:{who}:{tab}", profile=who))
    return found

def tabs():
    found = []
    with lock:
        for who, entry in profiles.items():
            if time.time() - entry["seen"] < FRESH_SECONDS:
                found += [dict(t, profile=who) for t in entry["tabs"]]
    return found

# ---------- Is the extension installed and on? (read from Chrome's own files, no extension needed) ----------
def installed():
    # [(profile folder, profile name, on?)] for every Chrome profile that has the M.I.N.D extension
    base = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    try:
        with open(os.path.join(base, "Local State"), encoding="utf-8") as f:
            names = json.load(f)["profile"]["info_cache"]
    except Exception:
        return []
    found = []
    for folder, info in names.items():
        try:
            with open(os.path.join(base, folder, "Secure Preferences"), encoding="utf-8") as f:
                settings = json.load(f).get("extensions", {}).get("settings", {})
        except Exception:
            continue
        for extension in settings.values():
            if os.path.normcase(str(extension.get("path", ""))) == os.path.normcase(EXTENSION):
                # disable_reasons is empty while it's on (1 = you turned it off)
                found.append((folder, info.get("name", folder), not extension.get("disable_reasons")))
    return found

def status():
    # The extension tool's "status": where it's installed, on/off, and whether it's talking to M.I.N.D
    places = installed()
    if not places:
        return ("The M.I.N.D extension isn't added to any Chrome profile yet. Add it once per profile: "
                "chrome://extensions, Developer mode, Load unpacked, pick the M.I.N.D 'extension' folder.")
    lines = [f"{name}: {'on' if on else 'OFF (turned off in chrome://extensions)'}" for _, name, on in places]
    live = sum(1 for p in profiles.values() if time.time() - p["seen"] < FRESH_SECONDS)
    lines.append(f"Talking to M.I.N.D right now: {live} Chrome profile(s)" +
                 (", nothing (Chrome closed, or the extension is asleep: it checks in every minute)" if not live else ""))
    return "M.I.N.D extension: " + "; ".join(lines)

def reload_all():
    reload_wanted.update(profiles)
    if not profiles:
        return "No Chrome profile with the extension is talking to M.I.N.D right now, so there's nothing to reload."
    return f"Told the extension to reload in {len(profiles)} profile(s); it happens within a minute."

def open_extensions_page(want=""):
    # Opens chrome://extensions in the profile that has the extension (Chrome doesn't let programs
    # open chrome:// pages directly, so it opens a new window and types the address)
    import subprocess
    import pc
    import hud
    places = installed()
    if not places:
        return status()
    pick = [p for p in places if want and want.lower() in p[1].lower()] or [p for p in places if not p[2]] or places
    folder, name, _ = pick[0]
    before = set(pc.chrome_windows())
    subprocess.Popen([hud.chrome_path(), f"--profile-directory={folder}", "--new-window", "about:blank"])
    window = None
    for _ in range(40):
        time.sleep(0.2)
        fresh = [h for h in pc.chrome_windows() if h not in before]
        if fresh:
            window = fresh[0]
            break
    if not window or not pc.bring_to_front(window):
        return f"Couldn't open Chrome for {name}."
    time.sleep(0.5)
    pc.tap_keys(0x11, 0x4C)  # ctrl+L: the address bar
    time.sleep(0.2)
    pc.type_text("chrome://extensions", press_enter=True)
    return f"Opened the extensions page in your {name} Chrome."
