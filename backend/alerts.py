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
import settings
from memory import profile, save_profile, tamil_mode

CHECK_SECONDS = 60       # how often to check everything
STARTUP_QUIET = 90       # no alerts in the first 90 seconds after M.I.N.D starts
RAIN_EVERY = 15          # check the rain forecast every 15 checks (15 minutes)

said = {}                # alert name -> when it was last said
internet = {"down_since": None, "told": False}
memory_high_since = None

def say(key, english, tamil, cooldown_hours, urgent=False, phone=True):
    # Queue an alert, unless it was said recently or it's quiet hours (urgent ones still speak)
    if time.time() - said.get(key, 0) < cooldown_hours * 3600 or not settings.alert_on(key):
        return
    if quiet_hours() and not urgent:
        return
    said[key] = time.time()
    line = tamil if tamil_mode() else english
    print("(Alert)", line)
    state.alerts.append(line)
    if phone and settings.on("phone_alerts"):
        import telegram_bot
        telegram_bot.notify("🔔 " + line)  # also on your phone, if it's connected

def quiet_hours():
    # No alerts at night ("quiet_hours" in profile.json, default 11 PM to 7 AM)
    if not settings.on("night_quiet"):
        return False
    start, end = profile.get("quiet_hours", [23, 7])
    hour = datetime.datetime.now().hour
    return hour >= start or hour < end

# ---------- Battery ----------
last_level = None  # battery % at the last check (None = just started)

def check_battery():
    global last_level
    battery = psutil.sensors_battery()
    if not battery:
        return
    level = round(battery.percent)
    was, last_level = last_level, level
    if battery.power_plugged:
        # Plugged in: the "please charge" warnings can come again next time
        for step in (5, 10, 15, 20):
            said.pop(f"battery_{step}", None)
        # "Unplug" reminder when it REACHES your level while M.I.N.D runs (default 90 %, better for the
        # battery than charging to 100; "battery_full_at" in profile.json). Not at every restart.
        enough = int(profile.get("battery_full_at", 90))
        if level >= enough and was is not None and was < enough:
            say("battery_full", f"Battery's at {level} percent, you can unplug the charger.",
                f"பேட்டரி {level} சதவீதம் ஆயிடுச்சு, சார்ஜர் எடுத்துடலாம்.", 12)
        return
    said.pop("battery_full", None)
    # "Please charge" keeps coming as it drops: at 20 and 15 %, then urgent at 10 and 5 %
    for step in (5, 10, 15, 20):
        if level <= step:
            if step <= 10:
                say(f"battery_{step}", f"Battery's at {level} percent! Plug in the charger now, or the laptop will shut down.",
                    f"பேட்டரி {level} சதவீதம் தான் இருக்கு! உடனே சார்ஜ் போடுங்க.", 6, urgent=True)
            else:
                say(f"battery_{step}", f"Battery's at {level} percent, please plug in the charger.",
                    f"பேட்டரி {level} சதவீதம் தான், சார்ஜ் போடுங்க.", 6)
            break

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
use = {"since": None, "last": time.time()}  # (starting M.I.N.D isn't "coming back": no good-morning speech at start)

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

# ---------- Laptop working hard ("getting hot") ----------
# Windows doesn't let normal apps read the CPU temperature, so this watches how busy the CPU is:
# over 85 % for 3 minutes makes laptops hot and loud. It names the app doing it.
cpu = {"busy_since": None, "last": None}

def cpu_load():
    # % busy since the last check (its own measurement, so other checks don't disturb it)
    now = psutil.cpu_times()
    total, idle = sum(now), now.idle
    last, cpu["last"] = cpu["last"], (total, idle)
    if not last or total <= last[0]:
        return 0
    return 100 * (1 - (idle - last[1]) / (total - last[0]))

def busiest_app():
    apps = []
    for p in psutil.process_iter(["name"]):
        try:
            p.cpu_percent(None)
            apps.append(p)
        except psutil.Error:
            pass
    time.sleep(1)
    use = {}
    for p in apps:
        try:
            name = (p.info["name"] or "").removesuffix(".exe")
            if name and name not in ("System Idle Process", "System", "Idle"):
                use[name] = use.get(name, 0) + p.cpu_percent(None)
        except psutil.Error:
            pass
    return max(use, key=use.get) if use else ""

def check_cpu():
    load = cpu_load()
    if load < 85:
        cpu["busy_since"] = None
        return
    cpu["busy_since"] = cpu["busy_since"] or time.time()
    if time.time() - cpu["busy_since"] >= 3 * 60:
        app = busiest_app()
        name = profile.get("name", "Sir")
        say("cpu", f"Your laptop's working really hard, {name}, the CPU is at {round(load)} percent"
            + (f", mostly {app}" if app else "") + ". It'll heat up; closing it would help.",
            f"லேப்டாப் ரொம்ப சூடாகுது, CPU {round(load)} சதவீதம்" + (f", {app} தான் காரணம்" if app else "") + ".",
            1, phone=False)

# ---------- Low disk space ----------
def check_disk():
    free = psutil.disk_usage("C:\\").free / 2**30
    if free < 10:
        say("disk", f"Only {free:.0f} GB left on your C drive. Emptying the Recycle Bin or old Downloads would help.",
            f"C drive-ல {free:.0f} GB தான் இருக்கு, Recycle Bin-ஐ காலி பண்ணுங்க.", 24)

# ---------- Drink water ----------
# Every 2 hours of real use (only minutes you're at the laptop count), 9 AM to 11 PM.
# "water_reminder": "off" in profile.json (or by voice) turns it off.
WATER_EVERY_MINUTES = 120
water = {"minutes": 0}
WATER_LINES = ["Time for a glass of water, {}.", "Quick water break, {}? You've been at it a while.",
               "Hey {}, drink some water."]

def check_water():
    if str(profile.get("water_reminder", "on")).lower() in ("off", "no", "false"):
        return
    if idle_seconds() < 5 * 60:
        water["minutes"] += CHECK_SECONDS / 60
    if water["minutes"] >= WATER_EVERY_MINUTES and 9 <= datetime.datetime.now().hour < 23:
        water["minutes"] = 0
        import random
        say("water", random.choice(WATER_LINES).format(profile.get("name", "Sir")),
            "கொஞ்சம் தண்ணி குடிங்க!", 1.5, phone=False)

# ---------- Weak Wi-Fi ----------
# The owner's connection is the main reason M.I.N.D is ever slow; a weak signal for 5 minutes is worth saying.
wifi_weak = {"since": None}

def check_wifi():
    import info
    net = info.wifi()
    if not net or net.get("signal") is None or net["signal"] >= 35:
        wifi_weak["since"] = None
        return
    wifi_weak["since"] = wifi_weak["since"] or time.time()
    if time.time() - wifi_weak["since"] >= 5 * 60:
        say("wifi_weak", f"Your Wi-Fi signal is weak, only {net['signal']} percent. Moving closer to {net['name']} "
            "will make me faster.", f"Wi-Fi சிக்னல் {net['signal']} சதவீதம் தான், கொஞ்சம் கிட்ட போங்க.",
            2, phone=False)

# ---------- Background loop ----------
def start():
    def loop():
        time.sleep(STARTUP_QUIET)  # let "Hi Sir, Mind online." be the only thing said at start
        count = 0
        while True:
            checks = [check_battery, check_internet, check_memory, check_human, check_cpu, check_water, check_wifi]
            if count % 30 == 0:
                checks.append(check_disk)  # disk space changes slowly: every 30 minutes
            for check in checks:
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
