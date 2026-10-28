# What the M.I.N.D Chrome extension (../extension) tells us about Chrome:
# every tab in every window of every profile that has it, and each AI chat's state
# (Claude / ChatGPT / Gemini: running or done, and the latest answer), even in background tabs.
# The extension POSTs to /api/browser (server.py); only requests from an extension are accepted.
import time
import threading

FRESH_SECONDS = 150  # a profile that hasn't reported for this long is treated as closed

lock = threading.Lock()
profiles = {}  # extension id per profile -> {"seen": time, "tabs": [...], "chats": {tab id: chat}}

def report(data):
    # One report from one Chrome profile: {"profile", "tabs": [...]} or {"profile", "chat": {...}}
    who = str(data.get("profile", ""))[:40]
    if not who:
        return
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
