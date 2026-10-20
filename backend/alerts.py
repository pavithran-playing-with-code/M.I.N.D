# Alerts: M.I.N.D speaks up by itself, like Jarvis would:
# low battery, internet down/back, rain coming, memory almost full.
# Runs in the background and puts lines in state.alerts; main.py says them out loud.
import time
import ctypes
import json
import socket
import datetime
import threading
import urllib.request
from urllib.parse import quote_plus
import psutil
import state
from memory import profile, save_profile, tamil_mode

CHECK_SECONDS = 60       # how often to check everything
RAIN_EVERY = 15          # check the rain forecast every 15 checks (15 minutes)

said = {}                # alert name -> when it was last said
internet = {"down_since": None, "told": False}
memory_high_since = None

def say(key, english, tamil, cooldown_hours, urgent=False, phone=True):
    # Queue an alert, unless it was said recently or it's quiet hours (urgent ones still speak)
    if time.time() - said.get(key, 0) < cooldown_hours * 3600:
        return
    if quiet_hours() and not urgent:
        return
    said[key] = time.time()
    line = tamil if tamil_mode() else english
    print("(Alert)", line)
    state.alerts.append(line)
    if phone:
        import telegram_bot
        telegram_bot.notify("🔔 " + line)  # also on your phone, if it's connected

def quiet_hours():
    # No alerts at night ("quiet_hours" in profile.json, default 11 PM to 7 AM)
    start, end = profile.get("quiet_hours", [23, 7])
    hour = datetime.datetime.now().hour
    return hour >= start or hour < end

# ---------- Battery ----------
def check_battery():
    battery = psutil.sensors_battery()
    if not battery:
        return
    level = round(battery.percent)
    if battery.power_plugged:
        # Plugged in: warnings can come again next time
        said.pop("battery_low", None)
        said.pop("battery_very_low", None)
        if level >= 100:
            say("battery_full", "Battery's full, you can unplug the charger.",
                "பேட்டரி ஃபுல்லா ஆயிடுச்சு, சார்ஜர் எடுத்துடலாம்.", 12)
        return
    said.pop("battery_full", None)
    if level <= 10:
        say("battery_very_low", f"Battery's at {level} percent! Plug in now or the laptop will shut down.",
            f"பேட்டரி {level} சதவீதம் தான் இருக்கு! உடனே சார்ஜ் போடுங்க.", 1, urgent=True)
    elif level <= 20:
        say("battery_low", f"Heads up, battery's at {level} percent. Might want to plug in.",
            f"பேட்டரி {level} சதவீதம் தான், சார்ஜ் போடுங்க.", 12)

# ---------- Internet ----------
def online():
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        return True
    except OSError:
        return False

def check_internet():
    if online():
        if internet["told"]:
            say("internet_back", "Internet's back.", "இன்டர்நெட் திரும்ப வந்துடுச்சு.", 0)
        internet.update(down_since=None, told=False)
        return
    internet["down_since"] = internet["down_since"] or time.time()
    # Only after a whole minute, so short blips don't cause alerts
    if not internet["told"] and time.time() - internet["down_since"] > 60:
        said.pop("internet_down", None)
        say("internet_down", "Heads up, your internet just went down.",
            "இன்டர்நெட் போயிடுச்சு.", 0)
        internet["told"] = True

# ---------- Rain ----------
city_place = {}  # city name -> (lat, lon), so we don't look it up every time

def where():
    # The HUD's exact location, or the city from profile.json
    if state.location:
        return state.location["lat"], state.location["lon"]
    city = profile.get("city", "")
    if not city:
        return None
    if city not in city_place:
        found = get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + quote_plus(city))
        top = found.get("results", [None])[0]
        if not top:
            return None
        city_place[city] = (top["latitude"], top["longitude"])
    return city_place[city]

def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)

def check_rain():
    spot = where()
    if not spot:
        return
    data = get_json(f"https://api.open-meteo.com/v1/forecast?latitude={spot[0]}&longitude={spot[1]}"
                    "&timezone=auto&current=precipitation&minutely_15=precipitation&forecast_minutely_15=8")
    if data["current"]["precipitation"] >= 0.3:
        return  # already raining
    now = datetime.datetime.now()
    for when, mm in zip(data["minutely_15"]["time"], data["minutely_15"]["precipitation"]):
        minutes = (datetime.datetime.fromisoformat(when) - now).total_seconds() / 60
        if 0 < minutes <= 60 and mm >= 0.3:
            minutes = max(15, round(minutes / 15) * 15)
            say("rain", f"Looks like rain in about {minutes} minutes. Bring in anything that's outside.",
                f"இன்னும் {minutes} நிமிஷத்துல மழை வரும் போல, வெளியே இருக்கறத உள்ள எடுத்துடுங்க.", 3)
            return

# ---------- Memory ----------
def check_memory():
    # Almost full for 5 minutes in a row
    global memory_high_since
    if psutil.virtual_memory().percent < 93:
        memory_high_since = None
        return
    memory_high_since = memory_high_since or time.time()
    if time.time() - memory_high_since > 5 * 60:
        say("memory", "Your memory's almost full. Closing a few Chrome tabs would speed things up.",
            "மெமரி கிட்டத்தட்ட ஃபுல், சில Chrome tabs மூடினா வேகமா ஆகும்.", 2)

# ---------- Human touches: breaks, late nights, good morning ----------
# Based on when you last touched the keyboard or mouse. Spoken on the laptop only (not sent to the phone).
BREAK_AFTER_HOURS = 2    # using the laptop this long without a break: suggest one
BREAK_MINUTES = 10       # away this long = you had a break (start counting again)
MORNING_AWAY_HOURS = 4   # back after this long, in the morning = "good morning"
use = {"since": None, "last": 0}  # last = 0: just started (counts as being away, e.g. the laptop was off)

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def idle_seconds():
    # Seconds since you last pressed a key or moved the mouse
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000

def short_weather():
    # "29 degrees and partly cloudy" (or "" if it can't be found)
    try:
        spot = where()
        data = get_json(f"https://api.open-meteo.com/v1/forecast?latitude={spot[0]}&longitude={spot[1]}"
                        "&current=temperature_2m,weather_code")["current"]
        from tools import weather_words
        words = weather_words(data["weather_code"]).lower()
        feel = {"clear sky": "clear", "foggy": "foggy", "drizzle": "drizzly", "rain": "rainy", "snow": "snowy",
                "rain showers": "showery", "thunderstorms": "stormy"}.get(words, words)  # "and drizzle" -> "and drizzly"
        return f"{round(data['temperature_2m'])} degrees and {feel}"
    except Exception:
        return ""

def check_human():
    now = time.time()
    idle = idle_seconds()
    if idle > BREAK_MINUTES * 60:
        use["since"] = None  # away or on a break: the next stretch starts fresh
        return
    away = now - idle - use["last"]  # how long you were gone before this
    use["last"] = now - idle
    hour = datetime.datetime.now().hour
    name = profile.get("name", "Sir")
    if use["since"] is None:
        use["since"] = now
        today = str(datetime.date.today())
        if away > MORNING_AWAY_HOURS * 3600 and 5 <= hour < 12 and profile.get("greeted") != today:
            profile["greeted"] = today  # once a day, even if M.I.N.D restarts
            save_profile()
            weather = short_weather()
            say("morning", f"Good morning, {name}! " + (f"It's {weather} outside. " if weather else "")
                + "Say mind, good morning for your briefing.",
                f"குட் மார்னிங் {name}! " + (f"வெளியே {weather}. " if weather else ""), 6, urgent=True, phone=False)
    elif now - use["since"] >= BREAK_AFTER_HOURS * 3600:
        use["since"] = now  # suggest again after another stretch
        hours = BREAK_AFTER_HOURS
        say("break", f"You've been at it for {hours} hours straight, {name}. Maybe stretch for a minute?",
            f"{hours} மணி நேரமா தொடர்ந்து வேலை பாக்குறீங்க, கொஞ்சம் break எடுங்க.", 1, urgent=True, phone=False)
    if 0 <= hour < 4:
        say("late", f"It's past {hour if hour else 12}, {name}. Don't stay up too late!",
            "ரொம்ப லேட் ஆயிடுச்சு, சீக்கிரம் தூங்குங்க!", 6, urgent=True, phone=False)

# ---------- Background loop ----------
def start():
    def loop():
        count = 0
        while True:
            for check in (check_battery, check_internet, check_memory, check_human):
                try:
                    check()
                except Exception as e:
                    print(f"Alert check {check.__name__} failed:", e)
            if count % RAIN_EVERY == 0 and online():
                try:
                    check_rain()
                except Exception as e:
                    print("Rain check failed:", e)
            count += 1
            time.sleep(CHECK_SECONDS)
    threading.Thread(target=loop, daemon=True).start()
