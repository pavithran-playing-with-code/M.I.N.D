# M.I.N.D: start here. Run from the backend folder with:  python main.py
# Then the HUD opens at http://localhost:8000
#
# Files:
#   memory.py  profile.json (what M.I.N.D knows about you)
#   ears.py    wake word + speech to text
#   voice.py   speaking out loud (say "stop" or click the orb to interrupt)
#   brain.py   understanding you and choosing tools (Groq)
#   tools.py   everything M.I.N.D can do (apps, websites, weather, reminders...)
#   state.py   what M.I.N.D is doing right now (shared with the HUD)
#   server.py  web server for the HUD
#   info.py    battery, Wi-Fi, internet speed      alerts.py  speaks up by itself
#   autostart.py  "python autostart.py on" makes M.I.N.D start with Windows
import sys
import time
import random
import socket
import threading
import webbrowser
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # so symbols like ° don't crash printing

# Only one M.I.N.D at a time (two would fight over the mic). A Windows "mutex" is a name only one
# program can hold: we grab it the instant we start, before loading anything slow, so a quick
# double-click can't start two. If another M.I.N.D holds it, show its HUD (if it's ready) and leave.
import os
import ctypes
mind_lock = ctypes.windll.kernel32.CreateMutexW(None, False, "MIND_voice_assistant")
if ctypes.windll.kernel32.GetLastError() == 183:  # 183 = already exists
    print("M.I.N.D is already running.")
    try:
        socket.create_connection(("127.0.0.1", 8000), timeout=1).close()
        webbrowser.open("http://localhost:8000")
    except OSError:
        pass  # still starting up: its HUD will open by itself
    sys.exit()

# Write our process id, so the taskbar button knows M.I.N.D is on (and what to stop)
PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mind.pid")
with open(PID_FILE, "w") as f:
    f.write(str(os.getpid()))

# Show "on" on the taskbar button (glowing cyan), and "off" (grey) when M.I.N.D closes
import atexit
import taskbar
taskbar.show(True)
atexit.register(taskbar.show, False)
atexit.register(lambda: os.path.exists(PID_FILE) and os.remove(PID_FILE))

# Right after Windows starts, Wi-Fi may not be connected yet: wait up to a minute
for _ in range(30):
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2).close()
        break
    except OSError:
        print("Waiting for the internet...")
        time.sleep(2)

from memory import profile
from ears import calibrate, listen, wait_for_wake, wake_word, wake_words, phrase_listener, open_mic, close_mic, hear
from voice import speak, warm_up, STOP_WORDS
import brain
from brain import think
from tools import reminder_due, due_reminders, OKAYS
from memory import tamil_mode
import state
import server
import info
import alerts

# Things M.I.N.D always says: (English choices, Tamil choices). One is picked at random,
# so it doesn't sound like a robot saying the same line every time.
PHRASES = {
    "yes": (["Yeah?", "Hmm?", "What's up?", "I'm listening."], ["சொல்லுங்க?", "என்ன?", "ஹ்ம்ம், சொல்லுங்க."]),
    "reminder": (["Hey, reminder: "], ["ஞாபகம் இருக்கா? "]),
    "online": (["Hey, I'm up!", "M.I.N.D here, all set."], ["M.I.N.D ரெடி!"]),
    "welcome": (["Good to see you, {}."], ["வணக்கம் {}!"]),
    "hint": (["Just say {} when you need me."], ["தேவைப்பட்டா {} சொல்லுங்க."]),
    "sleep": (["Okay, going quiet. Say {} when you need me.", "Cool, I'll be here. Just say {}."],
              ["சரி, அமைதியா இருக்கேன். தேவைப்பட்டா {} சொல்லுங்க."]),
}

def phrase(key, *values):
    return random.choice(PHRASES[key][1 if tamil_mode() else 0]).format(*values)

# ---------- The sleep command ----------
# "Stop", "go to sleep", "bye", "stop stop, don't talk to me for a while"...
# M.I.N.D always goes back to waiting for the wake word, without asking the brain.
# (Only when the whole sentence is about stopping: "stop the music" still goes to the brain.)
SLEEP_WORDS = {"stop", "sleep", "quiet", "bye", "goodbye", "enough", "shut", "later", "silence",
               "நிறுத்து", "போதும்", "அப்புறம்"}
FILLER_WORDS = {"please", "mind", "hey", "hi", "now", "for", "a", "while", "ok", "okay", "go", "to",
                "be", "up", "that's", "thats", "all", "not", "dont", "don't", "do", "speak", "talk",
                "me", "with", "listening", "thanks", "thank", "you", "just", "bit", "little", "sir",
                "and", "the", "time", "being", "some", "minutes", "bro", "it", "so", "yeah", "no",
                "பேசாத", "சார்"}

def wants_sleep(text):
    words = [w.strip(".,!?;:\"'") for w in text.lower().split()]
    words = [w for w in words if w]
    return (any(w in SLEEP_WORDS for w in words)
            and all(w in SLEEP_WORDS or w in FILLER_WORDS for w in words))

def announce_reminders():
    # Due reminders, then alerts (low battery, rain coming...)
    for text in due_reminders():
        speak(phrase("reminder") + text)
    while state.alerts:
        speak(state.alerts.popleft())

def next_input():
    # What you said over M.I.N.D, or a typed command from the HUD, or else what you say now
    text = state.take_heard()
    if text:
        return text
    text = state.take_typed()
    if text:
        print("You (typed):", text)
        state.add_message("you", text)
        return text
    text = listen(should_stop=lambda: state.has_typed() or state.muted)
    if text is None:  # you typed while it was listening
        return next_input()
    return text

def think_or_cancel(text):
    # Think in the background; meanwhile, a tap on the orb, "stop" or going offline cancels it.
    # Returns (reply, action), or None if you cancelled.
    result = {}
    job = threading.Thread(target=lambda: result.update(answer=think(text)), daemon=True)
    job.start()
    words = STOP_WORDS + wake_words()
    rec = phrase_listener(words)
    stream = open_mic()
    state.take_click()  # forget old clicks
    try:
        while job.is_alive():
            heard = hear(rec, stream)  # listens a quarter second
            if state.take_click() or state.muted or any(w in heard for w in words):
                brain.cancelled.set()
                print("(Cancelled the thinking)")
                return None
    finally:
        close_mic(stream)
    return result.get("answer", ("", None))

def conversation():
    # Keep talking without the wake word until: 2 silences in a row,
    # you say you're done, or you ask to shut down. Returns False to close M.I.N.D.
    missed = 0
    while True:
        if state.muted:
            return True  # went offline
        announce_reminders()
        text = next_input()
        if not text:
            # Nothing (or only noise) heard: stay quiet and keep listening, like Jarvis would
            missed += 1
            if missed >= 2:
                print("(Conversation ended, nothing heard)")
                return True
            continue
        missed = 0
        if wants_sleep(text):
            speak(phrase("sleep", wake_word()))
            print("(Sleeping until the wake word)")
            return True
        state.set_status("thinking")
        start = time.time()
        result = think_or_cancel(text)
        if result is None:
            speak(random.choice(["Okay, never mind.", "Alright, cancelled."]))
            continue
        reply, action = result
        print(f"   (thought in {time.time() - start:.1f}s)")
        if not reply:
            # That wasn't meant for M.I.N.D (talking to someone, song lyrics): stay quiet
            print("(Not for me, staying quiet)")
            missed += 1
            if missed >= 2:
                print("(Conversation ended)")
                return True
            continue
        speak(reply)
        if action == "shutdown":
            return False
        if action == "end":
            print("(Conversation ended)")
            return True

# ---------- Start ----------
server.start()
info.auto_speed_test(profile.get("speed_test_minutes", 60))
alerts.start()
if server.hud_ready():
    print(f"HUD: http://localhost:{server.PORT}")
    webbrowser.open(f"http://localhost:{server.PORT}")
else:
    print("HUD not built yet. From the M.I.N.D folder run: npm run build")

calibrate()
# Get everyday lines ready in the background so they play instantly
everyday = OKAYS + [line.format(wake_word()) for key in ("yes", "sleep") for line in PHRASES[key][1 if tamil_mode() else 0]]
everyday += ["Turning it up.", "Louder it is.", "Turning it down.", "Bringing it down a bit.", "Next one coming up.",
             "Skipping!", "Got it, I'll remind you.", "Noted!", "Alright, I'm here if you need me.", "Cool, catch you later."]
warm_up(everyday)
welcome = " " + phrase("welcome", profile["name"]) if profile.get("name") else ""
speak(phrase("online") + welcome + " " + phrase("hint", wake_word()))

# Wait for the wake word (or an orb click / typed command), talk, then wait again
running = True
while running:
    if state.muted:
        # Offline: mic off until you double-tap the orb again (reminders and alerts wait too)
        state.set_status("muted")
        time.sleep(0.3)
        continue
    woke = wait_for_wake(lambda: reminder_due() or state.alerts or state.has_input() or state.muted)
    announce_reminders()
    if woke and not state.has_input():
        speak(phrase("yes"))
    if woke or state.has_input():
        running = conversation()

state.set_status("offline")
print("M.I.N.D offline.")
time.sleep(1)  # give the HUD a moment to show "offline"
