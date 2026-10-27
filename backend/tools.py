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
import hud
import floating
import diary
import telegram_bot
import info
import state

def squash(text):
    # "Chat GPT" -> "chatgpt", so spaces and dots don't matter
    return re.sub(r"[^a-z0-9]", "", text.lower())

# ---------- Websites ----------
def open_page(url, account=""):
    # Opens a page in the browser used last, or in a Chrome account's own window
    # ("open YouTube with my tigerboogipink mail"). Returns None, or why it couldn't.
    account = account or profile.get("chrome_account", "")
    if not account:
        webbrowser.open(url)
        return None
    return pc.open_in_browser(url, account)

def open_url(url, account=""):
    url = url.strip()
    if not re.match(r"https?://", url):
        url = "https://" + url
    problem = open_page(url, account)
    return problem or f"Opened {url}"

# ---------- Music and videos ----------
def whatsapp_chat(name, message="", send=False, paste_copied=False):
    # Uses the saved number if there is one (exact), otherwise searches the name in WhatsApp.
    # paste_copied: puts what was copied (a link, Claude's answer...) into the chat with Ctrl+V
    # (typing it could press Enter at a new line and send half of it)
    contacts = {k.lower(): v for k, v in profile.get("contacts", {}).items()}
    phone = contacts.get(name.lower().strip(), "")
    if paste_copied in (True, "true", "yes"):
        opened = pc.whatsapp_chat(name, "", False, phone)
        time.sleep(1)
        return opened + " " + pc.paste("whatsapp")
    return pc.whatsapp_chat(name, message, send in (True, "true", "yes"), phone)

def save_contact(name, phone):
    phone = re.sub(r"[^0-9]", "", phone)
    if len(phone) == 10:
        phone = "91" + phone  # an Indian number without the country code
    profile.setdefault("contacts", {})[name.strip()] = phone
    save_profile()
    return f"Saved {name}'s number."

def tab_action(action, name=""):
    # One tool for browser tabs: list them, or act on one, or close all with a word in the title
    if action == "list":
        return pc.list_tabs()
    if action == "close_all":
        return pc.close_tab(name)
    return pc.tab_action(name, action)

def send_to_phone(text="", screenshot=False):
    replies = []
    if text:
        replies.append(telegram_bot.send_to_phone(text))
    if screenshot in (True, "true", "yes") or not text:
        replies.append(telegram_bot.send_screenshot())
    return " ".join(replies)

def remember_song(query):
    # Keep the last 15 songs you played: they're hints for hearing song names right next time
    songs = [s for s in profile.get("songs", []) if s.lower() != query.lower()]
    profile["songs"] = (songs + [query])[-15:]
    save_profile()

def whatsapp_call(name, video=True):
    # Opens the chat and presses WhatsApp's call button, only if the user said "call" themselves.
    # Never pretends: if there's no call button (WhatsApp Web may not have one), it says so.
    if not re.search(r"\bcall", state.last_user_text, re.I):
        return "Not called: only call when the user clearly asks to call."
    video = video in (True, "true", "yes")
    opened = whatsapp_chat(name)
    time.sleep(1.5)
    want = "video call" if video else "voice call"
    windows = pc.find_windows("whatsapp")
    buttons = []
    for hwnd, *_ in windows:
        buttons += [x for x in pc.clickables(hwnd, unique=False)
                    if want in x[2].lower() or (not video and x[2].lower() in ("call", "audio call"))]
    if not buttons:
        return f"{opened} But there's no {want} button I can press here (WhatsApp Web may not have calls). Nothing was called."
    top, left, button, kind, element = buttons[0]
    try:
        from comtypes.gen.UIAutomationClient import IUIAutomationInvokePattern
        element.GetCurrentPattern(10000).QueryInterface(IUIAutomationInvokePattern).Invoke()
    except Exception:
        box = element.CurrentBoundingRectangle
        pc.mouse_click(((box.left + box.right) // 2, (box.top + box.bottom) // 2))
    return f"Started a {want} with {name}."

def voice_lock(action="learn"):
    # Only listen to the owner's voice: learn it, or turn the lock on/off
    import speaker
    if action == "learn":
        state.learn_voice = True
        return "Voice learning starts right after your reply: say you'll read out a few short lines with them."
    if action == "on" and speaker.voiceprint is None:
        state.learn_voice = True
        return "Your voice isn't learned yet: learning starts right after your reply."
    profile["voice_lock"] = action == "on"
    save_profile()
    return "Now only listening to your voice." if action == "on" else "Now listening to everyone."

def go_offline(offline=True):
    # Mic off (like double-tapping the orb). "Go online" works from the phone or the orb.
    state.muted = bool(offline)
    return "Offline: mic is off." if state.muted else "Online: listening again."

def play_youtube(query, account=""):
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
    remember_song(query)
    problem = open_page("https://www.youtube.com/watch?v=" + video.group(1), account)
    if problem:
        return problem
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
    threading.Thread(target=pc.check_app, args=(app, app_trouble), daemon=True).start()  # is it OK?
    return f"Opened {app}"

def app_trouble(problem):
    # An app opened badly (black screen, frozen...): tell the user, like a friend would
    line = f"Heads up, Sir: {problem}. Want me to restart it, or open its repair page?"
    print("(App problem)", problem)
    state.alerts.append(line)
    import brain
    brain.history.append({"role": "assistant", "content": line})  # so "yes, restart it" makes sense
    brain.save_history()

def paste(where=""):
    # Paste into an app; if it isn't open yet but is installed (Notepad...), open it first
    if where and not pc.find_windows(where) and find_app(where):
        open_app(where)
        time.sleep(1.5)
    return pc.paste(where)

def fix_app(name, action="restart"):
    # Restart a misbehaving app, or open Windows' Repair page for it
    app = find_app(name)
    if not app:
        return f"No app called {name}."
    if action == "repair":
        return pc.repair_app(app, installed[app])
    closed = pc.close_app(app)
    time.sleep(2)
    subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + installed[app]])
    threading.Thread(target=pc.check_app, args=(app, app_trouble), daemon=True).start()
    return f"Restarted {app} ({closed}). I'll check it opens properly."

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
# (Reading notes is part of diary.recall)

# ---------- Routines: one command, many actions ----------
# Each step is a tool and its settings, so a routine runs straight away without asking the brain.
DEFAULT_ROUTINES = {
    "work mode": [
        {"tool": "open_folder", "args": {"name": "mind"}},
        {"tool": "play_youtube", "args": {"query": "lofi focus music for coding"}},
        {"tool": "change_volume", "args": {"action": "set", "percent": 30}},
    ],
    "good night": [
        {"tool": "media_control", "args": {"action": "stop"}},
        {"tool": "change_volume", "args": {"action": "set", "percent": 20}},
        {"tool": "lock_pc", "args": {}},
    ],
    "movie time": [
        {"tool": "change_volume", "args": {"action": "set", "percent": 70}},
        {"tool": "open_url", "args": {"url": "https://www.youtube.com"}},
    ],
}
NOT_IN_ROUTINES = {"run_routine", "save_routine", "shut_down", "end_conversation"}

def routines():
    # Built-in routines plus yours from profile.json (yours win; None = deleted)
    merged = dict(DEFAULT_ROUTINES)
    merged.update(profile.get("routines", {}))
    return {name: steps for name, steps in merged.items() if steps}

def find_routine(name):
    names = list(routines())
    match = difflib.get_close_matches(name.lower().strip(), names, n=1, cutoff=0.5)
    return match[0] if match else None

def run_routine(name):
    found = find_routine(name)
    if not found:
        return f"No routine called {name}. Routines: {', '.join(routines())}."
    done = []
    for step in routines()[found]:
        result, worked = run_tool(step["tool"], dict(step.get("args", {})))
        done.append(result if worked else f"{step['tool']} failed")
        time.sleep(0.8)  # give each app a moment to open
    return f"Ran {found}: " + "; ".join(done)

def save_routine(name, steps=None):
    # steps: [{"tool": "play_youtube", "args": {"query": "..."}}, ...]; no steps = delete the routine
    if not steps:
        return delete_routine(name)
    if isinstance(steps, str):
        steps = json.loads(steps)
    clean = []
    for step in steps:
        tool_name = step.get("tool", "")
        if tool_name not in FUNCTIONS or tool_name in NOT_IN_ROUTINES:
            return f"Can't use '{tool_name}' in a routine."
        clean.append({"tool": tool_name, "args": step.get("args") or {}})
    if not clean:
        return "A routine needs at least one step."
    profile.setdefault("routines", {})[name.lower().strip()] = clean
    save_profile()
    return f"Saved routine '{name}' with {len(clean)} steps: " + ", ".join(s["tool"] for s in clean)

def delete_routine(name):
    found = find_routine(name)
    if not found:
        return f"No routine called {name}."
    profile.setdefault("routines", {})[found] = None  # None also hides a built-in one
    save_profile()
    return f"Deleted routine '{found}'."

# ---------- Things M.I.N.D learns about you ----------
def system_info(include_apps=False, speed_test=False):
    if speed_test in (True, "true", "yes"):
        return info.internet_speed()
    return pc.system_info(include_apps)

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

def remember_fact(fact, forget=False):
    if forget in (True, "true", "yes"):
        return forget_fact(fact)
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

def text(description="", choices=None):
    t = {"type": "string"}
    if description:
        t["description"] = description
    if choices:
        t["enum"] = choices
    return t

def number(description=""):
    return {"type": "number", "description": description} if description else {"type": "number"}

# Kept short on purpose: this whole list is sent with every request, and Groq's free
# limit is 8000 tokens a minute (long descriptions = fewer requests = waiting).
BOOL = {"type": "boolean"}
TOOLS = [
    tool("play_youtube", "Play a song/music/video now (top YouTube result). Not for 'search X in the search box' "
         "(that's type_into).",
         ["query"], query=text("Search, e.g. 'Rathinamo Saurav Srisan'"), account=text("")),
    tool("media_control", "Control what's playing.",
         ["action"], action=text("", ["play_pause", "next", "previous", "stop"])),
    tool("open_url", "Open a website or search URL (account = a Chrome account's email/name, if asked). "
         "Ask ChatGPT: https://chatgpt.com/?q=..., Claude: https://claude.ai/new?q=...",
         ["url"], url=text(""), account=text("")),
    tool("type_text", "Type into the app in front. After opening an app, wait ~3s.",
         ["text"], text=text(""), wait_seconds=number(""), press_enter=BOOL),
    tool("press_keys", "Keyboard shortcut in the app in front, e.g. ctrl+t, alt+tab, win+d, ctrl+s.",
         ["keys"], keys=text("")),
    tool("floating_window", "Floating reactor: show/hide/move. position = a corner, or up/down/left/right "
         "nudge (far=true = a lot).", ["action"], action=text("", ["show", "hide", "move"]),
         position=text("", ["top-left", "top-right", "bottom-left", "bottom-right", "up", "down", "left", "right"]),
         far=BOOL),
    tool("open_hud", "Show your HUD window (also 'hub', 'dashboard')."),
    tool("tab_action", "Browser tabs: list, or switch/pause/play/close one (or close_all) by a title word.", ["action"], action=text("", ["list", "switch", "pause", "play", "close", "close_all"]),
         name=text("Word in the tab title")),
    tool("open_folder", "Open a folder or code project by name in VS Code.",
         ["name"], name=text("e.g. mind, downloads"), open_with=text("", ["vscode", "explorer"])),
    tool("fix_app", "Fix a misbehaving app (black screen, frozen, won't open): restart it, or open "
         "Windows' Repair page for it (keeps data).", ["name"], name=text(""), action=text("", ["restart", "repair"])),
    tool("find_files", "Find files by name words, kind and/or when ('the PDF I downloaded yesterday').", [], name=text(""),
         kind=text("", ["pdf", "document", "sheet", "slides", "image", "video", "audio", "zip"]),
         when=text("", ["today", "yesterday", "this week", "last week", "this month"])),
    tool("screen_items", "List what can be clicked in the window they're using (links, buttons; "
         "kind=videos for just videos, e.g. on YouTube). Numbered, top to bottom.", [], kind=text("", ["all", "videos"])),
    tool("click", "Click a link/button in the window they're using: a number from screen_items, or its name "
         "('Skip ad', 'Like', a video title).", ["which"], which=text("")),
    tool("scroll", "Scroll the window they're using.", [], direction=text("", ["down", "up", "top", "bottom"]),
         amount=text("", ["little", "page", "lot"])),
    tool("copy", "Copy: last_answer (last Claude/ChatGPT answer on screen), words (screen text with these "
         "words, 'the part about X'), link (page link), selection, or text (exact text).",
         [], what=text("", ["last_answer", "words", "link", "selection", "text"]), words=text(""), text=text("")),
    tool("paste", "Paste the clipboard into an app/window/tab by name (notepad, vs code...; opens the app if "
         "needed) or the one in front (WhatsApp chat: whatsapp_chat paste_copied=true). Only sends if they said so.",
         [], where=text("")),
    tool("voice_lock", "Only listen to the owner's voice: learn it ('learn my voice'), or on/off "
         "('only listen to me' / 'listen to everyone').", [], action=text("", ["learn", "on", "off"])),
    tool("type_into", "Type text into a box by its name ('Search', 'Message'...) in the window they're using "
         "(e.g. 'search lofi in the YouTube search box'). Presses Enter only if they said search/send.",
         ["text"], box=text(""), text=text("")),
    tool("read_screen", "Get the text of the page/app they're using, to read it out ('read this article') or "
         "answer about it ('what does it say about pricing?' = about).", [], about=text("")),
    tool("open_file", "Open a file: a number from the last find_files list, or a file name.", ["which"], which=text("")),
    tool("close_app", "Close a whole app (WhatsApp, Notepad; Chrome = all tabs). A website (YouTube) = tab_action close.",
         ["name"], name=text("")),
    tool("window_action", "Switch to/minimize/maximize an already-open app.",
         ["name"], name=text(""), action=text("", ["focus", "minimize", "maximize"])),
    tool("open_app", "Open an installed app (not found: try a suggestion or a website).",
         ["name"], name=text("")),
    tool("system_info", "Battery, CPU, RAM, disk; speed_test=true runs an internet speed test (~10s).",
         include_apps=text("Also biggest memory apps (for slowness)", ["yes", "no"]), speed_test=BOOL),
    tool("look_at_screen", "Look at the screen (only when asked about it).",
         question=text("")),
    tool("lock_pc", "Lock the PC, only when clearly asked."),
    tool("daily_briefing", "ALWAYS for 'good morning'/'brief me'. Summarise in up to 4 sentences."),
    tool("get_news", "News headlines, optionally about a topic. Summarise only what they say.",
         topic=text(""), count=number("")),
    tool("get_weather", "Weather now, today and tomorrow. Empty city = user's location.", city=text("")),
    tool("change_volume", "Change the volume.", ["action"], action=text("", ["up", "down", "mute", "set"]),
         percent=number("Amount, or level for set (default 10)")),
    tool("set_reminder", "Reminder or timer. Work out seconds from now.",
         ["seconds_from_now", "text"], seconds_from_now=number(""), text=text("")),
    tool("cancel_reminder", "Cancel a reminder (or all).", which=text("Words or time"), everything=BOOL),
    tool("save_note", "Save a note.", ["text"], text=text("")),
    tool("recall", "Look back: past chats ('which song yesterday?'), notes (notes=true), or what was on "
         "screen (activity=true).", [], about=text(""),
         when=text("", ["today", "yesterday", "this week", "last week", "this month"]), notes=BOOL, activity=BOOL),
    tool("update_profile", "Change a setting only when clearly asked. wake_word: 2+ words. voice: an Edge "
         "id or orpheus-austin. language: tamil/english.",
         ["field", "value"], field=text("", ["name", "real_name", "city", "wake_word", "voice", "language", "chrome_account", "battery_full_at"]),
         value=text("")),
    tool("remember_fact", "Remember (or forget) a lasting fact about the user.", ["fact"], fact=text(""), forget=BOOL),
    tool("add_correction", "User says you mishear a word: save heard -> meant.",
         ["heard", "meant"], heard=text(""), meant=text("")),
    tool("whatsapp_chat", "Open a WhatsApp chat; message = their EXACT words only (copied things: paste_copied); "
         "send only if clearly asked.",
         ["name"], name=text(""), message=text(""), send=BOOL, paste_copied=BOOL),
    tool("whatsapp_call", "WhatsApp voice or video call someone (only when they say call). Never claim a call "
         "happened unless this says so.", ["name"], name=text(""), video=BOOL),
    tool("save_contact", "Save someone's phone number (for exact WhatsApp chats).",
         ["name", "phone"], name=text(""), phone=text("with country code")),
    tool("send_to_phone", "Send a message and/or a screenshot to the user's phone.", text=text(""), screenshot=BOOL),
    tool("go_offline", "Turn your mic off (offline) or back on (online).", offline=BOOL),
    tool("run_routine", "Run a saved routine (several actions at once), e.g. work mode, good night.",
         ["name"], name=text("")),
    tool("save_routine", "Create/change a routine ('when I say X, do A and B'); steps = tool calls; "
         "no steps = delete.", ["name"], name=text(""),
         steps={"type": "array", "items": {"type": "object", "properties": {
             "tool": {"type": "string"}, "args": {"type": "object"}}, "required": ["tool"]}}),
    tool("end_conversation", "User is done (bye, that's all, thanks)."),
    tool("shut_down", "Fully close M.I.N.D."),
]

# After these tools, the conversation ends (so playing music isn't heard as you talking)
ENDS_CONVERSATION = {"play_youtube"}

FUNCTIONS = {
    "play_youtube": play_youtube, "media_control": media_control,
    "open_url": open_url,
    "type_text": pc.type_text, "press_keys": pc.press_keys, "close_app": pc.close_app,
    "tab_action": tab_action, "floating_window": floating.window_tool, "window_action": pc.window_action, "open_hud": lambda: hud.open_hud() or "HUD opened.", "open_folder": pc.open_folder,
    "system_info": system_info, "lock_pc": pc.lock_pc, "look_at_screen": pc.look_at_screen,
    "daily_briefing": daily_briefing, "get_news": get_news,
    "open_app": open_app, "get_weather": get_weather,
    "change_volume": change_volume, "set_reminder": set_reminder, "cancel_reminder": cancel_reminder,
    "save_note": save_note, "recall": diary.recall,
    "update_profile": update_profile, "remember_fact": remember_fact, "add_correction": add_correction,
    "end_conversation": end_conversation, "shut_down": shut_down,
    "whatsapp_chat": whatsapp_chat, "save_contact": save_contact,
    "send_to_phone": send_to_phone,
    "go_offline": go_offline,
    "run_routine": run_routine, "save_routine": save_routine,
    "fix_app": fix_app, "find_files": pc.find_files, "open_file": pc.open_file,
    "screen_items": pc.screen_items, "click": pc.click, "scroll": pc.scroll,
    "copy": pc.copy, "paste": paste, "voice_lock": voice_lock, "whatsapp_call": whatsapp_call,
    "type_into": pc.type_into, "read_screen": pc.read_screen,
}

# ---------- Sending the brain only the tools it may need ----------
# The full tool list is ~85% of every request. Most requests only need one group ("play X" = music),
# so the brain gets just those groups: requests are 3-4x smaller, faster, and the free limit lasts
# much longer. If no group matches ("yes", "do it", Tamil...), the brain gets ALL tools, like before.
TOOL_GROUPS = [
    # (words that point to this group, its tools)
    (r"song|music|play|pause|resume|next|previous|skip|volume|louder|quieter|softer|mute|sound|lofi|video|youtube|track",
     ["play_youtube", "media_control", "change_volume", "tab_action"]),
    (r"open|search|google|website|site|tab|tabs|chatgpt|claude|gmail|browser|chrome|account|mail|url|\.com|reopen",
     ["open_url", "tab_action", "open_app", "open_folder", "press_keys"]),
    (r"open|close|app|apps|window|minimi[sz]e|maximi[sz]e|switch|type|write|press|shortcut|key|keys|enter|paste|quit|exit",
     ["open_app", "close_app", "window_action", "press_keys", "type_text", "tab_action"]),
    (r"project|projects|folder|folders|code|vs|downloads|documents|desktop",
     ["open_folder", "open_app", "find_files", "open_file"]),
    (r"file|files|pdf|pdfs|doc|docx|document|documents|excel|sheet|spreadsheet|ppt|slides|resume|cv|photo|photos|"
     r"picture|pictures|image|images|video|videos|zip|download|downloaded|saved|find|where|first|second|third|last one",
     ["find_files", "open_file", "open_folder"]),
    (r"fix|repair|reset|restart|broken|black|blank|frozen|stuck|hang|hanging|crash|crashed|crashing|issue|problem|"
     r"working|responding|error",
     ["fix_app", "open_app", "close_app", "system_info"]),
    (r"battery|cpu|ram|memory|disk|storage|slow|speed|internet|wifi|laptop|pc|computer|system|charge|charging",
     ["system_info"]),
    (r"weather|rain|raining|temperature|hot|cold|umbrella|forecast|news|headlines|morning|brief|briefing",
     ["get_weather", "get_news", "daily_briefing"]),
    (r"copy|copied|paste|clipboard|response|answer|reply|replied|said|link|url|selected|selection|notepad|text",
     ["copy", "paste", "open_app", "whatsapp_chat", "tab_action", "window_action"]),
    (r"scroll|scrolling|click|tap|press|select|choose|pick|button|link|links|video|videos|watch|skip|ad|ads|like|one|"
     r"subscribe|first|second|third|fourth|fifth|top|bottom|down|up|page|next|back|showing|options|menu",
     ["screen_items", "click", "scroll", "press_keys"]),
    (r"type|write|search|box|field|fill|enter|input|read|reading|article|page|says|say|summari[sz]e|summary|"
     r"explain|about|this|what's|whats",
     ["type_into", "read_screen", "look_at_screen"]),
    (r"screen|see|look|showing|watching|reading",
     ["look_at_screen", "recall"]),
    (r"remind|reminder|reminders|timer|alarm|minutes|hours|tomorrow|tonight|cancel",
     ["set_reminder", "cancel_reminder"]),
    (r"note|notes|remember|recall|yesterday|earlier|before|ago|did|doing|was|were|last|history|told",
     ["save_note", "recall", "remember_fact"]),
    (r"forget|call|name|voice|wake|live|city|mishear|misheard|correction|language|default|always|setting",
     ["remember_fact", "update_profile", "add_correction"]),
    (r"whatsapp|message|text|send|phone|contact|number|screenshot|chat|call|calling|video",
     ["whatsapp_chat", "whatsapp_call", "save_contact", "send_to_phone"]),
    (r"routine|routines|mode|night|movie|when",
     ["run_routine", "save_routine"]),
    (r"voice|voices|learn|recognise|recognize|only|everyone|everybody|anyone|family|tv",
     ["voice_lock", "update_profile"]),
    (r"lock|offline|online|mic|floating|reactor|hud|hub|dashboard|shut|bye|goodbye|stop|quiet|thanks|that's",
     ["lock_pc", "go_offline", "floating_window", "open_hud", "shut_down", "end_conversation"]),
]
TOOL_GROUPS = [(re.compile(r"\b(" + words + r")\b", re.I), names) for words, names in TOOL_GROUPS]
# Feelings: just talk like a friend (maybe offer a song), so a weak backup brain can't wander off
# into files or apps (it once searched files for "I'm mood off today")
MOOD = re.compile(r"\b(mood|sad|upset|tired|bored|boring|stressed|stress|angry|lonely|depressed|happy|excited|"
                  r"feel|feeling|feels|cry|crying|frustrated|annoyed|worried|anxious|sleepy|exhausted|"
                  r"miss|love|hate|rough|bad day|good day)\b", re.I)
ALWAYS = ["end_conversation"]  # cheap, and "that's all" can come with anything

def tools_for(text):
    # The tools the brain gets for this request (all of them if nothing points anywhere)
    if re.search(r"[஀-௿]", text):
        return TOOLS  # Tamil words aren't in the groups yet: send everything
    wanted = set(ALWAYS)
    if MOOD.search(text):
        wanted.add("play_youtube")  # cheering up with a song is fine
    for words, names in TOOL_GROUPS:
        if words.search(text):
            wanted.update(names)
    routine_names = [r for r in routines() if r.lower() in text.lower()]
    if routine_names:
        wanted.add("run_routine")
    if wanted == set(ALWAYS):
        return TOOLS  # nothing matched: send everything
    return [t for t in TOOLS if t["function"]["name"] in wanted]

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
OKAYS = ["Done!", "Got it.", "Sure thing.", "All set.", "There you go.", "Sorted.", "All yours."]

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
    "go_offline": lambda a, r: "Going offline. Double-tap the orb to wake me." if a.get("offline", True)
                  else "I'm back online.",
    "open_app": lambda a, r: app_line(r[7:].strip(" .")) if r.startswith("Opened ") else None,
    "open_folder": lambda a, r: pick(f"Here's {a.get('name', 'it')}. Let's build something!",
                                     f"{a.get('name', 'It')}'s open, happy coding.", f"Opened {a.get('name', 'it')} for you.")
                                if r.startswith("Opened") else None,
    "close_app": lambda a, r: (pick("Closed it.", "Gone!", "Closed, one less thing on screen.") if r.startswith("Closed")
                              else pick("Closed that tab.", "Tab's gone.") if r.startswith("Close:") else None),
    "floating_window": lambda a, r: floating_line(a, r),
    "copy": lambda a, r: pick("Copied it.", "Got it copied.") if r.startswith("Copied") else None,
    "type_into": lambda a, r: (pick("Searched it.", "Done, search is in.") if "pressed Enter" in r
                               else pick("Typed it in.", "It's in the box.")) if r.startswith("Typed") else None,
    "paste": lambda a, r: (pick("Pasted.", "Done, pasted it.") + (" Sent too." if "Enter" in r else ""))
                          if r.startswith("Pasted") else None,
    "open_file": lambda a, r: pick("Here it is.", "Opening it now.") if r.startswith("Opened") else None,
    "tab_action": lambda a, r: None if a.get("action") == "list" or r.startswith("No") else {
        "pause": pick("Paused.", "Paused it for you."), "play": pick("Playing again.", "And we're back."),
        "close": pick("Closed that tab.", "Tab's gone."), "close_all": "Closed them all.",
        "switch": pick("There it is.", "Switched.")}.get(a.get("action"), "Done."),
    "window_action": lambda a, r: None if r.startswith("No open") else {
        "minimize": pick("Tucked it away.", "Minimized."), "maximize": pick("Made it big.", "Full size now."),
        "focus": pick("There it is.", "Brought it up.")}.get(a.get("action"), "Done."),
    "whatsapp_chat": lambda a, r: (None if not r.startswith(("Opened", "Searched"))
                                   else ("Sent it." if "Enter" in r else "Pasted it in the chat, not sent yet.")
                                   if a.get("paste_copied") in (True, "true", "yes") and "Pasted" in r
                                   else None if a.get("paste_copied") in (True, "true", "yes")
                                   else pick("WhatsApp's ready.", "Chat's open.")),
    "run_routine": lambda a, r: pick("All set!", "Done, all set.") if r.startswith("Ran") else None,
    "save_routine": lambda a, r: (pick("Got it, routine saved.", "Saved! Just say the name.") if r.startswith("Saved")
                                  else "Deleted." if r.startswith("Deleted") else None),
    "remember_fact": lambda a, r: ("Forgotten." if a.get("forget") else pick("Got it, I'll remember that.", "Noted, I won't forget."))
                                  if not r.startswith("No") else None,
    "update_profile": None, "add_correction": None,
    "press_keys": None, "open_hud": lambda a, r: pick("There you go.", "Here's the big screen."),
    "lock_pc": lambda a, r: pick("Locking up. See you soon!", "Locked. Take a break!"), "open_url": None, "type_text": None,
    "end_conversation": lambda a, r: pick("Alright, I'm here if you need me.", "Cool, catch you later."),
    "shut_down": lambda a, r: "Shutting down. See you!",
}

def app_line(app):
    return pick(f"{app}'s up.", f"Here's {app}.", f"{app}, coming right up.")

def floating_line(args, result):
    if not result.startswith("Floating"):
        return None
    if args.get("action") == "hide":
        return pick("Hiding. Just ask if you want me back.", "Okay, out of your way.")
    way = args.get("position")
    if way in ("up", "down", "left", "right"):
        if args.get("far"):
            return pick(f"Moved it way {way}.", f"Pushed it well {way}. Better?")
        return pick(f"Moved it {way} a bit.", f"Nudged {way}. Better?")
    if args.get("action") == "move":
        return pick("Moved over there.", "New spot, nice.")
    return pick("I'm right here in the corner.", "Floating and ready.")

def quick_reply(name, args, result):
    # The line to say for a quick tool, or None if the brain should answer instead
    if name not in QUICK:
        return None
    make = QUICK[name]
    if make is None:
        return random.choice(OKAYS)  # a simple action with no special line
    return make(args, result)  # None = it didn't work: the brain explains (it used to say "Done!" anyway)
