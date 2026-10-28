# State: what M.I.N.D is doing right now, shared with the HUD (the web page).
# The HUD reads it through server.py, and sends typed commands and orb clicks back.
import time
import threading
from collections import deque

lock = threading.Lock()
status = "starting"           # starting / waiting / listening / thinking / speaking / offline
level = 0.0                   # how loud the mic is right now, 0 to 1 (makes the orb react)
messages = deque(maxlen=100)  # the chat log
next_id = 0
typed = deque()               # commands typed in the HUD, waiting to be handled
heard = deque()               # things you said while M.I.N.D was talking, waiting to be handled
clicked = threading.Event()   # the orb was clicked
location = None               # {"lat", "lon", "name"} from the HUD (your browser's location)
muted = False                 # "offline": mic off (double-tap the orb to switch)
tone = ""                     # how your last words sounded, e.g. "louder and faster than usual"
last_user_text = ""           # what you last asked (risky clicks must be in your own words)
learn_voice = False           # "learn my voice" was asked: main.py runs it after the reply
alerts = deque()              # things M.I.N.D wants to say by itself (low battery, rain...)
showcase = None               # pictures/info shown on the HUD like a hologram (showcase.py)

def hidden_parts():
    # HUD panels the user hid ("info", "chat"), remembered in profile.json
    from memory import profile
    return profile.get("hud_hidden", [])

def set_status(new_status):
    global status
    status = new_status

def set_level(new_level):
    global level
    level = new_level

def add_message(who, text):
    # who: "you", "mind" or "tool"
    global next_id
    with lock:
        next_id += 1
        messages.append({"id": next_id, "who": who, "text": text,
                         "time": time.strftime("%I:%M %p")})

def snapshot():
    with lock:
        return {"status": status, "level": round(level, 3), "messages": list(messages), "muted": muted,
                "showcase": showcase, "hidden": hidden_parts()}

# ---------- From the HUD ----------
def type_command(text):
    typed.append(text)

def has_typed():
    return bool(typed)

def take_typed():
    return typed.popleft() if typed else None

def has_input():
    # Is anything (typed or said over M.I.N.D) waiting to be handled?
    return bool(typed or heard)

def take_heard():
    return heard.popleft() if heard else None

def toggle_mute():
    global muted
    muted = not muted
    return muted

def click():
    clicked.set()

def take_click():
    # True once per click
    if clicked.is_set():
        clicked.clear()
        return True
    return False
