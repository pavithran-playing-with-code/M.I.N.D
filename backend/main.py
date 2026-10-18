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
import sys
import time
import random
import webbrowser
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # so symbols like ° don't crash printing

from memory import profile
from ears import calibrate, listen, wait_for_wake, wake_word
from voice import speak, warm_up
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
    text = listen(should_stop=state.has_typed)
    if text is None:  # you typed while it was listening
        return next_input()
    return text

def conversation():
    # Keep talking without the wake word until: 2 silences in a row,
    # you say you're done, or you ask to shut down. Returns False to close M.I.N.D.
    missed = 0
    while True:
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
        reply, action = think(text)
        print(f"   (thought in {time.time() - start:.1f}s)")
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
    woke = wait_for_wake(lambda: reminder_due() or state.alerts or state.has_input())
    announce_reminders()
    if woke and not state.has_input():
        speak(phrase("yes"))
    if woke or state.has_input():
        running = conversation()

state.set_status("offline")
print("M.I.N.D offline.")
time.sleep(1)  # give the HUD a moment to show "offline"
