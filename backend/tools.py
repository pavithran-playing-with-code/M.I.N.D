# Tools: things M.I.N.D can DO.
# We don't hardcode sentences like "open X". The brain reads the descriptions
# in TOOLS (bottom of this file) and decides by itself which tool to use.
# To teach M.I.N.D a new skill: write a function, then add it to TOOLS and FUNCTIONS.
import os
import re
import json
import time
import ctypes
import difflib
import datetime
import threading
import subprocess
import webbrowser
import urllib.request
from urllib.parse import quote_plus
from memory import profile, save_profile, BASE_DIR

def squash(text):
    # "Chat GPT" -> "chatgpt", so spaces and dots don't matter
    return re.sub(r"[^a-z0-9]", "", text.lower())

# ---------- Websites ----------
def open_url(url):
    url = url.strip()
    if not re.match(r"https?://", url):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"

# ---------- Apps (any app in your Start menu, found automatically) ----------
installed = {}  # app name -> Windows app id

def load_apps():
    # Ask Windows for every app in the Start menu (takes about a second)
    command = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
               "Get-StartApps | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="ignore", timeout=30).stdout
        apps = json.loads(out)
        if isinstance(apps, dict):  # only one app
            apps = [apps]
        installed.update({a["Name"]: a["AppID"] for a in apps})
    except Exception as e:
        print("Couldn't list apps:", e)

threading.Thread(target=load_apps, daemon=True).start()  # load in the background

def find_app(name):
    # Best matching installed app name, or None
    if not installed:
        load_apps()
    keys = {squash(n): n for n in installed}
    want = squash(name)
    if want in keys:
        return keys[want]
    if len(want) >= 3:
        # "chrome" -> "Google Chrome" (the shortest name that contains it)
        inside = sorted((k for k in keys if want in k), key=len)
        if inside:
            return keys[inside[0]]
    close = difflib.get_close_matches(want, list(keys), n=1, cutoff=0.75)
    return keys[close[0]] if close else None

def open_app(name):
    app = find_app(name)
    if not app:
        keys = {squash(n): n for n in installed}
        similar = difflib.get_close_matches(squash(name), list(keys), n=5, cutoff=0.4)
        if similar:
            return f"No app called {name}. Similar installed apps: {', '.join(keys[s] for s in similar)}."
        return f"No app called {name} is installed. Maybe open a website instead."
    # Only apps from your Start menu can be opened, nothing else
    subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + installed[app]])
    return f"Opened {app}"

# ---------- Weather (Open-Meteo, free, no key) ----------
def weather_words(code):
    # Open-Meteo gives a number; turn it into words
    if code == 0: return "clear sky"
    if code <= 3: return "partly cloudy"
    if code <= 48: return "foggy"
    if code <= 57: return "drizzle"
    if code <= 67: return "rain"
    if code <= 77: return "snow"
    if code <= 82: return "rain showers"
    return "thunderstorms"

def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)

def get_weather(city=""):
    city = city.strip() or profile.get("city", "")
    if not city:
        return "The user's city is unknown. Ask them which city."
    found = get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + quote_plus(city))
    if not found.get("results"):
        return f"Couldn't find a place called {city}."
    place = found["results"][0]
    data = get_json(
        "https://api.open-meteo.com/v1/forecast?timezone=auto&forecast_days=2"
        "&current=temperature_2m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code"
        f"&latitude={place['latitude']}&longitude={place['longitude']}"
    )
    now, day = data["current"], data["daily"]
    report = f"{place['name']} now: {round(now['temperature_2m'])}°C, {weather_words(now['weather_code'])}."
    for i, label in enumerate(["Today", "Tomorrow"]):
        report += (f" {label}: {round(day['temperature_2m_min'][i])} to {round(day['temperature_2m_max'][i])}°C, "
                   f"{weather_words(day['weather_code'][i])}.")
    return report

# ---------- Volume (presses the keyboard's volume keys) ----------
VOLUME_UP, VOLUME_DOWN, VOLUME_MUTE = 0xAF, 0xAE, 0xAD

def press_key(key, times=1):
    for _ in range(times):
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)  # key down
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)  # key up

def change_volume(action, percent=10):
    # Each key press moves the volume about 2 percent
    presses = max(1, round(percent / 2))
    if action == "mute":
        press_key(VOLUME_MUTE)  # the mute key switches mute on/off
        return "Mute switched."
    if action == "set":
        press_key(VOLUME_DOWN, 50)  # go to 0 first
        press_key(VOLUME_UP, presses)
        return f"Volume set to about {presses * 2} percent."
    press_key(VOLUME_UP if action == "up" else VOLUME_DOWN, presses)
    return f"Volume {action} by about {presses * 2} percent."

# ---------- Reminders (saved in reminders.json, so they survive restarts) ----------
REMINDERS_FILE = os.path.join(BASE_DIR, "reminders.json")

def load_reminders():
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

reminders = load_reminders()  # list of {"due": time, "text": what to remind}

def save_reminders():
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, indent=2)

def nice_time(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%I:%M %p on %A")

def set_reminder(seconds_from_now, text):
    due = time.time() + float(seconds_from_now)
    reminders.append({"due": due, "text": text})
    save_reminders()
    return f"Reminder set for {nice_time(due)}: {text}"

def upcoming_reminders():
    return [f"{r['text']} at {nice_time(r['due'])}" for r in reminders]

def reminder_due():
    return any(r["due"] <= time.time() for r in reminders)

def due_reminders():
    # Removes and returns the reminders whose time has come
    due = [r for r in reminders if r["due"] <= time.time()]
    for r in due:
        reminders.remove(r)
    if due:
        save_reminders()
    return [r["text"] for r in due]

# ---------- Notes (saved in notes.txt) ----------
NOTES_FILE = os.path.join(BASE_DIR, "notes.txt")

def save_note(text):
    stamp = datetime.datetime.now().strftime("%d %b %Y %I:%M %p")
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"{stamp} - {text.strip()}\n")
    return "Note saved."

def read_notes(count=5):
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            notes = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        notes = []
    if not notes:
        return "There are no notes yet."
    return f"{len(notes)} notes in total. Latest:\n" + "\n".join(notes[-int(count):])

# ---------- Things M.I.N.D learns about you ----------
def update_profile(field, value):
    profile[field] = value.strip()
    save_profile()
    if field == "wake_word":
        return f"Wake word changed to {value}. It works after this conversation ends."
    return f"Saved {field}: {value}"

def remember_fact(fact):
    facts = profile.setdefault("facts", [])
    if fact not in facts:
        facts.append(fact.strip())
        save_profile()
    return "Remembered."

def forget_fact(fact):
    facts = profile.get("facts", [])
    close = difflib.get_close_matches(fact, facts, n=1, cutoff=0.4)
    if not close:
        return "No matching memory found."
    facts.remove(close[0])
    save_profile()
    return f"Forgot: {close[0]}"

def add_correction(heard, meant):
    profile.setdefault("corrections", {})[heard.lower().strip()] = meant.strip()
    save_profile()
    return f"From now on '{heard}' will be heard as '{meant}'."

def add_shortcut(name, url):
    profile.setdefault("shortcuts", {})[name.lower().strip()] = url.strip()
    save_profile()
    return f"Shortcut saved: {name} opens {url}"

# ---------- Ending ----------
def end_conversation():
    return "The conversation will end after your reply. Say a short goodbye."

def shut_down():
    return "M.I.N.D will shut down after your reply. Say a short goodbye."

# ---------- Tool list the brain reads ----------
def tool(tool_name, description, required=(), **params):
    return {"type": "function", "function": {
        "name": tool_name, "description": description,
        "parameters": {"type": "object", "properties": params, "required": list(required)}}}

def text(description, choices=None):
    t = {"type": "string", "description": description}
    if choices:
        t["enum"] = choices
    return t

def number(description):
    return {"type": "number", "description": description}

TOOLS = [
    tool("open_url", "Open any website in the browser. Also use it for Google searches "
         "(https://www.google.com/search?q=...), YouTube searches or videos, maps, music sites, etc.",
         ["url"], url=text("Full web address")),
    tool("open_app", "Open an app installed on this Windows laptop (Spotify, Notepad, VS Code, Calculator, "
         "Settings...). If it isn't found, the result lists similar apps; then try one of those or a website.",
         ["name"], name=text("App name")),
    tool("get_weather", "Current weather plus today's and tomorrow's forecast for a city. "
         "Leave city empty for the user's own city.",
         city=text("City name, or empty")),
    tool("change_volume", "Change the computer's sound volume.",
         ["action"], action=text("What to do", ["up", "down", "mute", "set"]),
         percent=number("How much to change, or the level for 'set'. Default 10")),
    tool("set_reminder", "Remind the user about something later. Work out the number of seconds "
         "from the current time (e.g. 'in 10 minutes' = 600, 'at 5 pm' = seconds until 5 pm).",
         ["seconds_from_now", "text"],
         seconds_from_now=number("Seconds from now"), text=text("What to remind them about")),
    tool("save_note", "Write down a note for the user.", ["text"], text=text("The note")),
    tool("read_notes", "Read the user's latest notes.", count=number("How many, default 5")),
    tool("update_profile", "Save a basic detail about the user: what to call them (name), "
         "their real name, their city, the wake word that wakes you up, or your own voice. "
         "Voices: en-GB-RyanNeural (British man, default), en-GB-ThomasNeural (British man), "
         "en-GB-SoniaNeural (British woman), en-US-GuyNeural (American man), "
         "en-US-AndrewNeural (American man, warm), en-US-JennyNeural (American woman), "
         "en-IN-PrabhatNeural (Indian man), en-IN-NeerjaNeural (Indian woman).",
         ["field", "value"], field=text("Which detail", ["name", "real_name", "city", "wake_word", "voice"]),
         value=text("The new value (for voice, the exact voice id)")),
    tool("remember_fact", "Remember something about the user for the future "
         "(likes, plans, people, preferences). Use it when they share something worth remembering.",
         ["fact"], fact=text("Short fact, e.g. 'Loves Iron Man movies'")),
    tool("forget_fact", "Forget something you remembered about the user.",
         ["fact"], fact=text("The fact to forget")),
    tool("add_correction", "When the user says you keep mishearing a word, save the fix "
         "(e.g. 'when I say V V P I mean VVP').",
         ["heard", "meant"], heard=text("What you heard"), meant=text("What they meant")),
    tool("add_shortcut", "Save a named website shortcut for the user.",
         ["name", "url"], name=text("Shortcut name"), url=text("Full web address")),
    tool("end_conversation", "The user is done for now (bye, that's all, thanks, never mind). "
         "You go back to waiting for the wake word."),
    tool("shut_down", "The user wants M.I.N.D to fully close/exit/shut down."),
]

FUNCTIONS = {
    "open_url": open_url, "open_app": open_app, "get_weather": get_weather,
    "change_volume": change_volume, "set_reminder": set_reminder,
    "save_note": save_note, "read_notes": read_notes,
    "update_profile": update_profile, "remember_fact": remember_fact,
    "forget_fact": forget_fact, "add_correction": add_correction,
    "add_shortcut": add_shortcut, "end_conversation": end_conversation, "shut_down": shut_down,
}

def run_tool(name, args):
    # Runs the tool the brain picked, and returns the result as text for the brain
    func = FUNCTIONS.get(name)
    if not func:
        return f"There is no tool called {name}."
    try:
        return str(func(**args))
    except Exception as e:
        print(f"Tool {name} failed:", e)
        return f"The tool failed: {e}"
