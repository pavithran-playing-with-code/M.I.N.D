# First-run setup: the HUD walks a new user through getting M.I.N.D ready (their name, what to call them,
# city, their OWN free Gemini and Groq keys, learning their voice, the Chrome extension).
# Keys are checked live before they're saved into backend\.env (never shown again, never sent anywhere else).
import os
import re
import threading
from memory import profile, save_profile, BASE_DIR
import state

ENV_FILE = os.path.join(BASE_DIR, ".env")
PLACEHOLDER = "your_key_here"
KEYS = {
    "gemini": ("GEMINI_API_KEY", "https://aistudio.google.com/apikey"),
    "groq": ("GROQ_API_KEY", "https://console.groq.com/keys"),
}
EXTENSION_FOLDER = os.path.join(os.path.dirname(BASE_DIR), "extension")
VOICEPRINT = os.path.join(BASE_DIR, "voiceprint.npy")
learning = {"busy": False}

def has_key(kind):
    value = os.getenv(KEYS[kind][0], "").strip()
    return bool(value) and value != PLACEHOLDER

def needed():
    return not profile.get("setup_done")

def mark_existing():
    # At start: someone who already had M.I.N.D working (a name and a Gemini key) never sees the setup
    if not profile.get("setup_done") and has_key("gemini") and profile.get("name"):
        profile["setup_done"] = True
        save_profile()

def status():
    return {
        "needed": needed(),
        "real_name": profile.get("real_name", ""),
        "call_me": profile.get("name", ""),
        "city": profile.get("city", ""),
        "gemini": has_key("gemini"),
        "groq": has_key("groq"),
        "voice": os.path.exists(VOICEPRINT),
        "learning": learning["busy"] or state.learn_voice,
        "extension_folder": EXTENSION_FOLDER,
        "lines": voice_lines(),
    }

def voice_lines():
    import speaker
    return speaker.SENTENCES  # what they read out while M.I.N.D learns their voice

def save_about(real_name, call_me, city):
    real_name, call_me, city = (str(x or "").strip()[:40] for x in (real_name, call_me, city))
    if not real_name:
        return False, "Tell me your name first."
    profile["real_name"] = real_name
    profile["name"] = call_me or real_name.split()[0]
    if city:
        profile["city"] = city
    save_profile()
    return True, f"Nice to meet you, {real_name}!"

def write_env(name, value):
    # Puts NAME=value in .env (replacing the old line), keeps every other line as it is
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"\s*{name}\s*=", line):
            lines[i] = f"{name}={value}"
            break
    else:
        lines.append(f"{name}={value}")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.environ[name] = value

def check_key(kind, key):
    # Tries the key with a tiny free request (listing the models). Only a key that works is saved.
    key = re.sub(r"\s+", "", str(key or ""))
    if kind not in KEYS:
        return False, "Unknown key."
    if len(key) < 20:
        return False, "That doesn't look like a full key. Copy the whole thing and paste it again."
    try:
        if kind == "gemini":
            from google import genai
            client = genai.Client(api_key=key)  # (kept in a variable: a client nobody holds closes itself mid-request)
            next(iter(client.models.list()))
        else:
            from groq import Groq
            Groq(api_key=key, max_retries=0, timeout=10).models.list()
    except Exception as e:
        text = str(e)
        if re.search(r"401|403|invalid|API_KEY_INVALID|not valid", text, re.I):
            who = "Google" if kind == "gemini" else "Groq"
            return False, f"{who} says this key isn't valid. Make a new one and paste it again."
        return False, "Couldn't check it (internet?). Try again in a moment."
    write_env(KEYS[kind][0], key)
    return True, "Key works and is saved."

def open_page(what):
    import pc
    if what in KEYS:
        pc.open_in_browser(KEYS[what][1])
    elif what == "extensions":
        import tools
        tools.mind_extension("open")
    elif what == "extension_folder":
        os.startfile(EXTENSION_FOLDER)
    return True, "Opened."

def learn_voice():
    # main.py's loop sees the flag and reads the 5 lines with them (main.learn_voice)
    if not learning["busy"]:
        state.learn_voice = True
    return True, "Listen to me and read each line after me."

def finish():
    # Saved; M.I.N.D restarts once so every part loads the new keys
    state.alerts.clear()  # (anything queued before the keys existed is old news; the restart starts fresh)
    profile["setup_done"] = True
    save_profile()
    import selfknow
    threading.Thread(target=selfknow.restart_now, args=("first-run setup finished",), daemon=True).start()
    return True, "All set! Restarting once to load your keys (about 30 seconds)."

ACTIONS = {
    "about": lambda a: save_about(a.get("real_name"), a.get("call_me"), a.get("city")),
    "key": lambda a: check_key(a.get("kind"), a.get("key")),
    "open": lambda a: open_page(a.get("what")),
    "voice": lambda a: learn_voice(),
    "finish": lambda a: finish(),
}

def act(what, args):
    if what not in ACTIONS:
        return False, "Unknown step."
    try:
        return ACTIONS[what](args or {})
    except Exception as e:
        print("Setup:", str(e)[:150])
        return False, "Something went wrong there. Try again."
