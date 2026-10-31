# Settings: everything you can change in the HUD's Controls panel (or by voice, the change_setting tool).
# Each entry is one real switch: the code that it controls asks settings.on("...") or reads profile.json.
import difflib
import state
from memory import profile, save_profile

OFF_WORDS = ("off", "no", "false", "0", "disabled", "hide", "hidden")

def toggle(key, label, default=True, hint=""):
    return {"key": key, "label": label, "kind": "toggle", "default": default, "hint": hint}

def choice(key, label, default, options, hint=""):
    # options: [(saved value, what the panel shows)]
    return {"key": key, "label": label, "kind": "choice", "default": default, "hint": hint,
            "options": [{"value": v, "label": l} for v, l in options]}

def words(key, label, hint=""):
    return {"key": key, "label": label, "kind": "text", "default": "", "hint": hint}

def amount(key, label, default, low, high, hint=""):
    return {"key": key, "label": label, "kind": "number", "default": default, "low": low, "high": high, "hint": hint}

GROUPS = [
    ("HUD panels", [
        toggle("hud_info", "Info column", hint="The whole left column"),
        toggle("card_weather", "Weather card"),
        toggle("card_internet", "Internet card"),
        toggle("card_laptop", "Laptop card"),
        toggle("card_limits", "Free limits card"),
        toggle("hud_chat", "Conversation panel"),
        toggle("hints", "Example commands under the core"),
    ]),
    ("Look", [
        choice("theme", "Colour", "cyan", [("cyan", "Arc cyan"), ("gold", "Iron gold"), ("green", "Matrix green"),
                                          ("violet", "Violet"), ("white", "Ice white")]),
        choice("text_size", "Text size", "normal", [("small", "Small"), ("normal", "Normal"), ("large", "Large")]),
        toggle("aura", "Light orbits around the core"),
        toggle("motion", "Animations", hint="Off = spinning rings stop, easier on the laptop"),
        toggle("clock_24", "24-hour clock", default=False),
        toggle("clock_seconds", "Seconds on the clock"),
    ]),
    ("Floating reactor", [
        toggle("floating", "Show the reactor"),
        toggle("reactor_hide", "Hide it while the HUD is in front", hint="So it never sits on top of the HUD's buttons"),
    ]),
    ("Listening", [
        toggle("mic", "Microphone", hint="Off = offline, same as double-tapping the core"),
        toggle("duck_music", "Turn music down when I say Mind"),
        toggle("voice_lock", "Wake only for my voice", hint="Other people saying Mind are ignored"),
        toggle("talk_voice_check", "In a talk, answer only my voice", hint="Room talk and TV stay unanswered"),
        choice("patience", "Wait after I stop talking", "900", [("600", "Short"), ("900", "Normal"), ("1500", "Long")],
               hint="Longer = it cuts you off less, but answers later"),
        choice("talk_seconds", "Keep listening after a reply", "25",
               [("10", "10 s"), ("25", "25 s"), ("45", "45 s"), ("90", "90 s")], hint="No need to say Mind during this time"),
        words("wake_word", "Extra wake phrase", hint="Two words or more. Hey Mind always works"),
    ]),
    ("Voice and brain", [
        choice("live_voice", "Live voice", "Charon", [("Charon", "Charon (deep)"), ("Puck", "Puck (lively)"),
                                                      ("Fenrir", "Fenrir (strong)"), ("Orus", "Orus (firm)"),
                                                      ("Kore", "Kore (female)"), ("Aoede", "Aoede (female)")]),
        toggle("live", "Live brain", hint="Off = the slower backup brain does everything"),
    ]),
    ("Things it tells me", [
        choice("notifications", "App notifications", "full",
               [("full", "Read them out"), ("sender", "Only who it's from"), ("off", "Off")]),
        toggle("watch_prompts", "When an AI finishes my prompt", hint="Claude, ChatGPT, Gemini, Claude Code"),
        toggle("alert_battery", "Low battery"),
        toggle("alert_unplug", "Unplug the charger"),
        amount("battery_full_at", "Unplug reminder at (%)", 90, 50, 100),
        toggle("water_reminder", "Drink water"),
        toggle("alert_break", "Take a break"),
        toggle("alert_late", "It's getting late"),
        toggle("alert_morning", "Good morning"),
        toggle("alert_rain", "Rain coming"),
        toggle("alert_internet", "Internet down"),
        toggle("alert_wifi", "Weak Wi-Fi"),
        toggle("alert_memory", "Memory full"),
        toggle("alert_cpu", "CPU working too hard"),
        toggle("alert_disk", "Disk almost full"),
        toggle("night_quiet", "Quiet at night (11 PM to 7 AM)", hint="Urgent battery alerts still speak"),
        toggle("phone_alerts", "Send alerts to my phone too"),
    ]),
    ("Browser", [
        {"key": "chrome_account", "label": "Open links in this Chrome", "kind": "choice", "default": "", "options": None,
         "hint": "The HUD, songs and every link. Saying another account still works"},
    ]),
    ("About me", [
        words("name", "What it calls me"),
        words("city", "My city", hint="For weather when my location isn't known"),
    ]),
]
EVERY = {s["key"]: s for _, group in GROUPS for s in group}
LOOK = ("card_weather", "card_internet", "card_laptop", "card_limits", "hints", "aura", "motion", "theme",
        "text_size", "clock_24", "clock_seconds")  # what the HUD itself needs to draw

def is_on(value):
    return str(value).strip().lower() not in OFF_WORDS

def get(key):
    if key in ("hud_info", "hud_chat"):
        return key[4:] not in profile.get("hud_hidden", [])
    if key == "mic":
        return not state.muted
    spec = EVERY[key]
    value = profile.get(key)
    if value in (None, "") and spec["kind"] != "text":
        value = spec["default"]
    if spec["kind"] == "toggle":
        return is_on(value)
    return "" if value is None else str(value) if spec["kind"] != "number" else value

def on(key):
    return bool(get(key))

def options_for(spec):
    if spec["key"] != "chrome_account":
        return spec.get("options")
    import pc
    found = [{"value": folder, "label": f"{name} ({email})" if email else name} for folder, name, email in pc.chrome_profiles()]
    return [{"value": "", "label": "The Chrome I used last"}] + sorted(found, key=lambda o: o["label"].lower())

def panel():
    # What the Controls panel shows
    groups = []
    for title, group in GROUPS:
        items = [{**{k: v for k, v in s.items() if k != "default"}, "options": options_for(s), "value": get(s["key"])}
                 for s in group]
        groups.append({"title": title, "items": items})
    return groups

def look():
    return {key: get(key) for key in LOOK}

def change(key, value):
    # Saves one setting and makes it take effect now. Returns (worked?, what happened).
    spec = EVERY.get(key)
    if not spec:
        return False, f"There's no setting called {key}."
    if spec["kind"] == "toggle":
        value = is_on(value)
    elif spec["kind"] == "choice":
        allowed = [o["value"] for o in options_for(spec)]
        said = str(value).strip().lower()
        for o in options_for(spec):
            if said in (o["value"].lower(), o["label"].lower()) or (said and said in o["label"].lower()):
                value = o["value"]
                break
        if value not in allowed:
            return False, f"{spec['label']} can't be {value}."
    elif spec["kind"] == "number":
        try:
            value = int(float(value))
        except (TypeError, ValueError):
            return False, f"{spec['label']} needs a number."
        if not spec["low"] <= value <= spec["high"]:
            return False, f"{spec['label']} must be between {spec['low']} and {spec['high']}."
    else:
        value = str(value).strip()
        if not value:
            return False, f"{spec['label']} can't be empty."
    refused = apply(key, value)
    if refused:
        return False, refused
    save_profile()
    return True, f"{spec['label']}: {describe(spec, value)}."

def describe(spec, value):
    if spec["kind"] == "toggle":
        return "on" if value else "off"
    for o in options_for(spec) or []:
        if o["value"] == value:
            return o["label"]
    return str(value)

def apply(key, value):
    # The settings that need more than saving. Returns a message if it was refused.
    if key in ("hud_info", "hud_chat"):
        hidden = set(profile.get("hud_hidden", []))
        (hidden.discard if value else hidden.add)(key[4:])
        profile["hud_hidden"] = sorted(hidden)
    elif key == "mic":
        set_mic(value)
    elif key == "floating":
        import floating
        floating.window_tool("show" if value else "hide")
    elif key == "wake_word" and len(value.split()) < 2:
        return "A wake phrase needs at least two words, or it wakes up by accident."
    else:
        profile[key] = value
    return None

def set_mic(on_now):
    # Mic on/off. Going offline also ends a Live talk: its mic is separate, and it used to keep listening.
    state.muted = not on_now
    if state.muted:
        import live_brain
        live_brain.stop_talk()

def alert_on(key):
    # alerts.py's alert names ("battery_15", "wifi_weak", "battery_full") -> their switch here
    if key == "battery_full":
        return on("alert_unplug")
    setting = "alert_" + key.split("_")[0]
    return on(setting) if setting in EVERY else True

def names():
    return [key for key in EVERY]

def find(name):
    # A setting from what was said ("the weather card", "dark mode"): its key, label, or something close
    said = name.strip().lower().replace(" ", "_")
    if said in EVERY:
        return said
    labels = {s["label"].lower(): key for key, s in EVERY.items()}
    close = difflib.get_close_matches(name.strip().lower(), labels, n=1, cutoff=0.6)
    return labels[close[0]] if close else None

def change_setting(name, value=""):
    # Tool: "Mind, hide the weather card", "turn off water reminders", "make it gold", "open settings"
    if name.strip().lower() in ("open", "controls", "settings", "panel"):
        open_panel()
        return "Controls panel opened on the HUD."
    key = find(name)
    if not key:
        return f"No setting called {name}. They are: " + ", ".join(names())
    return change(key, value)[1]

def open_panel():
    import hud
    state.controls_open += 1
    hud.open_hud()
