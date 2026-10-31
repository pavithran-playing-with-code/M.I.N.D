# The HUD's layout, your own arrangement: where each widget is, how big, minimized to an edge icon or hidden,
# and your world clocks. Kept in workspace.json (not in the code), so it's the same every time the HUD opens.
import json
import os
import threading
import time
import state
from memory import BASE_DIR, profile

FILE = os.path.join(BASE_DIR, "workspace.json")
MODES = ("open", "dock", "hidden")
INFO_CARDS = ("weather", "internet", "laptop", "limits")
EDGES = ("left", "right", "top", "bottom")
lock = threading.Lock()
data = {"v": 1, "widgets": {}, "clocks": [], "order": []}

def load():
    try:
        with open(FILE, encoding="utf-8") as f:
            data.update(clean(json.load(f)))
    except (OSError, ValueError):
        pass
    # (the old "hide this panel" list becomes hidden widgets)
    for part in profile.get("hud_hidden", []):
        for name in INFO_CARDS if part == "info" else [part]:
            data["widgets"].setdefault(name, {"mode": "hidden"})

def clean(new):
    # Only what the layout may hold, so a bad save can't break the HUD
    widgets = {}
    for name, w in (new.get("widgets") or {}).items():
        if not isinstance(w, dict) or len(str(name)) > 40:
            continue
        kept = {k: min(1.5, max(-0.5, float(w[k]))) for k in ("x", "y", "w", "h", "pos") if isinstance(w.get(k), (int, float))}
        if w.get("mode") in MODES:
            kept["mode"] = w["mode"]
        if w.get("edge") in EDGES:
            kept["edge"] = w["edge"]
        widgets[str(name)] = kept
    clocks = [{"id": str(c.get("id"))[:40], "city": str(c.get("city", ""))[:40], "tz": str(c.get("tz", ""))[:60], "h24": bool(c.get("h24"))}
              for c in (new.get("clocks") or []) if isinstance(c, dict) and c.get("id")][:24]
    order = [str(o)[:40] for o in (new.get("order") or [])][:60]
    return {"v": int(new.get("v") or 1), "widgets": widgets, "clocks": clocks, "order": order}

def save():
    try:
        with open(FILE + ".part", "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(FILE + ".part", FILE)
    except OSError as e:
        print("Couldn't save the HUD layout:", e)

def replace(new):
    # The HUD sends the whole layout after each change
    with lock:
        data.update(clean(new))
        data["v"] += 1
        save()
        return data["v"]

def changed():
    with lock:
        data["v"] += 1
        save()

def mode_of(name):
    return data["widgets"].get(name, {}).get("mode", "open")

def set_mode(names, mode):
    for name in names:
        data["widgets"].setdefault(name, {})["mode"] = mode
    changed()

def reset():
    data.update(widgets={}, order=[])
    changed()

WORDS = {"chat": "chat", "conversation": "chat", "comms": "chat", "weather": "weather", "internet": "internet", "wifi": "internet",
         "speed": "internet", "laptop": "laptop", "battery": "laptop", "limits": "limits", "free limits": "limits",
         "clock": "clock", "time": "clock", "logo": "brand", "name": "brand", "brand": "brand",
         "windows": "windows", "tabs": "windows", "screen": "screen", "info": "info"}

def find_clock(city):
    want = city.strip().lower()
    return next((c for c in data["clocks"] if want and (want in c["city"].lower() or c["city"].lower() in want)), None)

def hud_widget(action, name="", city="", hours=""):
    # Tool: "add a London clock in 24 hours", "remove the Tokyo clock", "minimize the chat", "show the weather", "reset my HUD"
    action = action.lower().strip()
    if action == "reset":
        reset()
        return "HUD layout back to the start. Your clocks stay."
    if action == "add_clock":
        place = (city or name).strip()
        if not place:
            return "Which city?"
        found = find_clock(place)
        if found:
            if hours:
                found["h24"] = "24" in str(hours)
            data["widgets"].setdefault(found["id"], {})["mode"] = "open"
            changed()
            return f"The {found['city']} clock is on the HUD."
        clock = {"id": f"clock-{int(time.time() * 1000)}", "city": place.title(), "tz": "", "h24": "24" in str(hours)}
        data["clocks"].append(clock)
        changed()
        return f"Added a {clock['city']} clock to the HUD ({'24' if clock['h24'] else '12'}-hour). You can drag it anywhere."
    if action == "remove_clock":
        found = find_clock(city or name)
        if not found:
            return f"There's no {city or name} clock. Clocks: " + (", ".join(c["city"] for c in data["clocks"]) or "none")
        data["clocks"].remove(found)
        data["widgets"].pop(found["id"], None)
        changed()
        return f"Removed the {found['city']} clock."
    clock = find_clock(name)
    if clock:
        names = [clock["id"]]
    else:
        word = WORDS.get(name.lower().replace("the ", "").replace(" card", "").replace(" panel", "").strip())
        if not word:
            return f"No widget called {name}. Widgets: weather, internet, laptop, limits, chat, clock, logo, windows, or a city clock."
        names = list(INFO_CARDS) if word == "info" else [word]
    mode = {"hide": "hidden", "show": "open", "minimize": "dock"}.get(action)
    if not mode:
        return "Actions: add_clock, remove_clock, hide, show, minimize, reset."
    set_mode(names, mode)
    return {"hidden": "Hidden: ", "open": "Showing: ", "dock": "Minimized to an edge icon: "}[mode] + name + "."

load()
