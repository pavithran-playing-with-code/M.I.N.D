# Tools: things M.I.N.D can DO.
# We don't hardcode sentences like "open X". The brain reads the descriptions
# in TOOLS (bottom of this file) and decides by itself which tool to use.
# To teach M.I.N.D a new skill: write a function, then add it to TOOLS and FUNCTIONS.
import os
import re
import json
import inspect
import random
import time
import ctypes
import difflib
import datetime
import threading
import subprocess
import webbrowser
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from memory import profile, save_profile, BASE_DIR
import pc
import info
import state

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

# ---------- Music and videos ----------
def play_youtube(query):
    # Finds the top YouTube result and opens it, so it starts playing (no key needed)
    page = urllib.request.Request(
        "https://www.youtube.com/results?search_query=" + quote_plus(query),
        headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"})
    html = urllib.request.urlopen(page, timeout=5).read().decode("utf-8", "ignore")
    video = re.search(r'"videoId":"([\w-]{11})"', html)
    if not video:
        open_url("https://www.youtube.com/results?search_query=" + quote_plus(query))
        return f"Couldn't find a video to play, so opened the search for {query}."
    title = re.search(r'"title":\{"runs":\[\{"text":"(.*?)"', html)
    webbrowser.open("https://www.youtube.com/watch?v=" + video.group(1))
    return f"Playing on YouTube: {title.group(1) if title else query}"

# Keyboard media keys work with YouTube in the browser, Spotify, and most players
MEDIA_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}

def media_control(action):
    press_key(MEDIA_KEYS[action])
    return f"Pressed the {action.replace('_', '/')} media key."

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

def fetch(url, timeout=8):
    # Download a web page; tries twice, because the internet sometimes drops a request
    page = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(page, timeout=timeout) as resp:
                return resp.read()
        except OSError:
            if attempt == 1:
                raise

def get_json(url):
    return json.loads(fetch(url))

def get_weather(city=""):
    city = city.strip()
    if not city and state.location:
        # Your exact spot, from the HUD (browser location)
        place = {"name": state.location["name"] or "your area",
                 "latitude": state.location["lat"], "longitude": state.location["lon"]}
    else:
        city = city or profile.get("city", "")
        if not city:
            return "The user's city is unknown. Ask them which city."
        found = get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + quote_plus(city))
        if not found.get("results"):
            return f"Couldn't find a place called {city}."
        place = found["results"][0]
    data = get_json(
        "https://api.open-meteo.com/v1/forecast?timezone=auto&forecast_days=2"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max"
        f"&latitude={place['latitude']}&longitude={place['longitude']}"
    )
    now, day = data["current"], data["daily"]
    report = (f"{place['name']} now: {round(now['temperature_2m'])}°C (feels like {round(now['apparent_temperature'])}), "
              f"{weather_words(now['weather_code'])}, humidity {now['relative_humidity_2m']}%, "
              f"wind {round(now['wind_speed_10m'])} km/h.")
    for i, label in enumerate(["Today", "Tomorrow"]):
        report += (f" {label}: {round(day['temperature_2m_min'][i])} to {round(day['temperature_2m_max'][i])}°C, "
                   f"{weather_words(day['weather_code'][i])}, {day['precipitation_probability_max'][i]}% chance of rain.")
    return report

# ---------- News (Google News, free, no key) ----------
def get_news(topic="", count=5):
    # Top headlines in India, or headlines about a topic
    base = "https://news.google.com/rss"
    url = (f"{base}/search?q={quote_plus(topic)}&" if topic.strip() else f"{base}?") + "hl=en-IN&gl=IN&ceid=IN:en"
    items = ET.fromstring(fetch(url)).findall("./channel/item")
    titles = [item.findtext("title", "").rsplit(" - ", 1)[0][:120] for item in items[:int(count)]]
    return "Headlines: " + " | ".join(titles) if titles else "Couldn't find any news on that."

# ---------- Morning briefing ----------
def daily_briefing():
    # Everything for "good morning": weather, today's reminders, laptop, internet and news
    parts = [f"Today is {datetime.datetime.now().strftime('%A, %d %B')}."]
    for name, job in [("Weather", get_weather), ("News", lambda: get_news(count=3))]:
        try:
            parts.append(job())
        except Exception:
            parts.append(f"{name}: not available right now.")
    today = datetime.date.today()
    todays = [f"{r['text']} at {nice_time(r['due'])}" for r in reminders
              if datetime.date.fromtimestamp(r["due"]) == today]
    parts.append("Reminders today: " + ("; ".join(todays) if todays else "none"))
    pc_now = info.system()
    parts.append(f"Laptop: battery {pc_now['battery']}% ({'charging' if pc_now['charging'] else 'on battery'}), "
                 f"memory {pc_now['ram']}% used.")
    if info.speed["result"]:
        r = info.speed["result"]
        parts.append(f"Internet: {r['label']}, {r['down']} Mbps.")
    return "\n".join(parts)

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

def cancel_reminder(which="", everything=False):
    # Removes the reminder that best matches 'which' (its text or time), or all of them
    if not reminders:
        return "There are no reminders."
    if everything:
        count = len(reminders)
        reminders.clear()
        save_reminders()
        return f"Cancelled all {count} reminders."
    described = [f"{r['text']} at {nice_time(r['due'])}".lower() for r in reminders]
    scores = [difflib.SequenceMatcher(None, which.lower(), d).ratio() + (which.lower() in d)
              for d in described]
    best = max(range(len(reminders)), key=lambda i: scores[i])
    if scores[best] < 0.3:
        return "No reminder matches that. Reminders: " + "; ".join(described)
    gone = reminders.pop(best)
    save_reminders()
    return f"Cancelled: {gone['text']} at {nice_time(gone['due'])}"

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
    value = value.strip()
    if field == "wake_word" and len(value.split()) < 2:
        return "Not changed: a wake word needs at least two words (like 'hey jarvis'), or it wakes up by accident."
    if field == "language":
        value = "tamil" if "tamil" in value.lower() else "english"
    profile[field] = value
    save_profile()
    if field == "wake_word":
        return f"Wake word changed to {value}. It works after this conversation ends."
    if field == "language":
        return f"Language is now {value}. Reply in {value} from now on."
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
    tool("play_youtube", "Play a song, music or video right away (opens the top YouTube result, "
         "which starts playing). Use this whenever the user wants to listen to or watch something. "
         "For vague requests ('play any song', 'some chill music'), pick a good search yourself.",
         ["query"], query=text("What to search for, e.g. 'Rathinamo Saurav Srisan' or 'lofi chill music'")),
    tool("media_control", "Control music or video that is already playing: pause/resume, next, previous, stop.",
         ["action"], action=text("What to do", ["play_pause", "next", "previous", "stop"])),
    tool("open_url", "Open any website in the browser. Also use it for Google searches "
         "(https://www.google.com/search?q=...), YouTube search pages, maps, etc. "
         "To ask ChatGPT something, open https://chatgpt.com/?q=<question>; "
         "for Claude, https://claude.ai/new?q=<question> (URL-encode the question).",
         ["url"], url=text("Full web address")),
    tool("type_text", "Type text into whatever app is in front (where the cursor is), as if on the keyboard. "
         "If you just opened the app, wait a few seconds first so it's ready.",
         ["text"], text=text("What to type"),
         wait_seconds=number("Seconds to wait before typing (about 3 after opening an app), default 0"),
         press_enter={"type": "boolean", "description": "Press Enter after typing"}),
    tool("press_keys", "Press a keyboard shortcut in the app in front, e.g. 'ctrl+t' (new tab), "
         "'alt+tab' (switch app), 'win+d' (show desktop), 'ctrl+s' (save). To close browser tabs use close_tab.",
         ["keys"], keys=text("Keys joined with +")),
    tool("close_tab", "Close browser tabs whose title contains a word, e.g. 'YouTube' closes all "
         "YouTube tabs. Use for 'close the YouTube tab', 'close that video', 'close all Gmail tabs'.",
         ["name"], name=text("A word from the tab's title, e.g. YouTube, Gmail, the song name")),
    tool("open_folder", "Open a folder or project by its name, in VS Code (default) or File Explorer. "
         "Use for 'open project mind', 'open the M.I.N.D project in VS Code', 'open my downloads folder'.",
         ["name"], name=text("Folder or project name, e.g. mind, playroom, downloads"),
         open_with=text("Where to open it", ["vscode", "explorer"])),
    tool("close_app", "Close an open app's windows (politely, it can still ask to save). "
         "For browser tabs (YouTube, a website...) use close_tab instead.",
         ["name"], name=text("App name, e.g. chrome, notepad, spotify")),
    tool("system_info", "Check the laptop: battery, CPU, RAM and disk space. "
         "Use for 'how's my battery', 'why is my laptop slow', etc.",
         include_apps={"type": "boolean",
                       "description": "Also list the apps using the most memory (for 'why is it slow'). Slower."}),
    tool("lock_pc", "Lock the computer. Only when the user clearly asks to lock it."),
    tool("daily_briefing", "A quick briefing: weather, today's reminders, laptop status, internet and top news. "
         "Use for 'good morning', 'brief me', 'what's my day like', 'catch me up'. Turn it into a short, "
         "friendly spoken summary (up to 4 sentences, mention only the interesting bits)."),
    tool("get_news", "Latest news headlines, in general or about a topic (a place, team, company...). "
         "Summarise the top 2 or 3 in a sentence or two, using only what the headlines say.",
         topic=text("Topic, or empty for top news"), count=number("How many headlines, default 5")),
    tool("internet_speed", "Run a real internet speed test (download, upload, ping) and check the Wi-Fi. "
         "Takes about 10 seconds."),
    tool("look_at_screen", "Take a screenshot and look at what's on the user's screen. "
         "Only use when they ask about their screen ('what's on my screen', 'read this', 'what is this error').",
         question=text("What to find out about the screen")),
    tool("open_app", "Open an app installed on this Windows laptop (Spotify, Notepad, VS Code, Calculator, "
         "Settings...). If it isn't found, the result lists similar apps; then try one of those or a website.",
         ["name"], name=text("App name")),
    tool("get_weather", "Current weather plus today's and tomorrow's forecast for a city. "
         "Leave city empty for the user's own city.",
         city=text("City name, or empty")),
    tool("change_volume", "Change the computer's sound volume.",
         ["action"], action=text("What to do", ["up", "down", "mute", "set"]),
         percent=number("How much to change, or the level for 'set'. Default 10")),
    tool("set_reminder", "Remind the user about something later, or set a timer. Work out the number of seconds "
         "from the current time (e.g. 'in 10 minutes' = 600, 'at 5 pm' = seconds until 5 pm).",
         ["seconds_from_now", "text"],
         seconds_from_now=number("Seconds from now"), text=text("What to remind them about")),
    tool("cancel_reminder", "Cancel a reminder (or all of them) that the user doesn't want, "
         "or that was set by mistake.",
         which=text("Words or time from the reminder, e.g. 'back to office' or '6:15'"),
         everything={"type": "boolean", "description": "Cancel all reminders"}),
    tool("save_note", "Write down a note for the user.", ["text"], text=text("The note")),
    tool("read_notes", "Read the user's latest notes.", count=number("How many, default 5")),
    tool("update_profile", "Save a basic detail about the user: what to call them (name), "
         "their real name, their city, your own voice, or the wake word (ONLY if they clearly say "
         "'change your wake word to ...'; never because they want quiet). "
         "Voices: orpheus-austin (most human, American man, default), orpheus-troy, orpheus-daniel "
         "(men), orpheus-autumn, orpheus-diana, orpheus-hannah (women); Edge voices: "
         "en-GB-RyanNeural (British man), en-GB-ThomasNeural (British man), "
         "en-GB-SoniaNeural (British woman), en-US-GuyNeural (American man), "
         "en-US-AndrewNeural (American man, warm), en-US-JennyNeural (American woman), "
         "en-IN-PrabhatNeural (Indian man), en-IN-NeerjaNeural (Indian woman), "
         "ta-IN-ValluvarNeural (Tamil man), ta-IN-PallaviNeural (Tamil woman). "
         "language: 'tamil' or 'english' switches the language you listen and talk in "
         "(use it when the user asks you to speak Tamil or English).",
         ["field", "value"],
         field=text("Which detail", ["name", "real_name", "city", "wake_word", "voice", "language"]),
         value=text("The new value (for voice, the exact voice id; for language, tamil or english)")),
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
    tool("stay_silent", "Say nothing: the words weren't meant for you (the user talking to someone else "
         "or to themselves, song lyrics, TV, random half sentences)."),
    tool("end_conversation", "The user is done for now (bye, that's all, thanks, never mind). "
         "You go back to waiting for the wake word."),
    tool("shut_down", "The user wants M.I.N.D to fully close/exit/shut down."),
]

# After these tools, the conversation ends (so playing music isn't heard as you talking)
ENDS_CONVERSATION = {"play_youtube"}

FUNCTIONS = {
    "play_youtube": play_youtube, "media_control": media_control,
    "open_url": open_url,
    "type_text": pc.type_text, "press_keys": pc.press_keys, "close_app": pc.close_app,
    "close_tab": pc.close_tab, "open_folder": pc.open_folder,
    "system_info": pc.system_info, "lock_pc": pc.lock_pc, "look_at_screen": pc.look_at_screen,
    "internet_speed": info.internet_speed, "daily_briefing": daily_briefing, "get_news": get_news,
    "open_app": open_app, "get_weather": get_weather,
    "change_volume": change_volume, "set_reminder": set_reminder, "cancel_reminder": cancel_reminder,
    "save_note": save_note, "read_notes": read_notes,
    "update_profile": update_profile, "remember_fact": remember_fact,
    "forget_fact": forget_fact, "add_correction": add_correction,
    "add_shortcut": add_shortcut, "end_conversation": end_conversation, "stay_silent": lambda: "ok", "shut_down": shut_down,
}

def run_tool(name, args):
    # Runs the tool the brain picked. Returns (result text for the brain, True if it worked).
    func = FUNCTIONS.get(name)
    if not func:
        return f"There is no tool called {name}.", False
    # Ignore settings the tool doesn't have (the brain sometimes adds extra ones)
    known = inspect.signature(func).parameters
    args = {k: v for k, v in args.items() if k in known}
    try:
        return str(func(**args)), True
    except Exception as e:
        print(f"Tool {name} failed:", e)
        return f"The tool failed: {e}", False

# ---------- Quick replies ----------
# For simple actions the brain doesn't need to see the result, so M.I.N.D answers
# right away with a short line instead of asking the brain again.
# (About a second faster, and half the free-limit use. Same lines = cached voice = instant.)
OKAYS = ["Done!", "Got it.", "Sure thing.", "All set.", "There you go."]

def pick(*lines):
    return random.choice(lines)

def song_name(result):
    # "Playing on YouTube: Rathinamo (Female Version) Lyric Video | Saurav" -> "Rathinamo"
    title = result.split(":", 1)[-1]
    return re.split(r"[|(\[\-–]", title)[0].strip()[:60]

QUICK = {
    "change_volume": lambda a, r: {"up": pick("Turning it up.", "Louder it is."),
                                   "down": pick("Turning it down.", "Bringing it down a bit.")}.get(a.get("action")),
    "media_control": lambda a, r: {"next": pick("Next one coming up.", "Skipping!"), "previous": "Going back one.",
                                   "stop": "Stopped."}.get(a.get("action")),
    "play_youtube": lambda a, r: pick(f"Here's {song_name(r)}, enjoy!", f"Playing {song_name(r)}.")
                                 if r.startswith("Playing") else None,
    "set_reminder": lambda a, r: pick("Got it, I'll remind you.", "Done, I'll give you a shout."),
    "save_note": lambda a, r: pick("Noted!", "Got it written down."),
    "remember_fact": lambda a, r: pick("Got it, I'll remember that.", "Noted, I won't forget."),
    "forget_fact": None, "update_profile": None, "add_correction": None, "add_shortcut": None,
    "press_keys": None, "lock_pc": None, "open_url": None, "type_text": None,
    "end_conversation": lambda a, r: pick("Alright, I'm here if you need me.", "Cool, catch you later."),
    "shut_down": lambda a, r: "Shutting down. See you!",
}

def quick_reply(name, args, result):
    # The line to say for a quick tool, or None if the brain should answer instead
    if name not in QUICK:
        return None
    make = QUICK[name]
    return (make(args, result) if make else None) or random.choice(OKAYS)
