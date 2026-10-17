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
import webbrowser
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # so symbols like ° don't crash printing

from memory import profile
from ears import calibrate, listen, wait_for_wake, wake_word
from voice import speak
from brain import think
from tools import reminder_due, due_reminders
from memory import tamil_mode
import state
import server

# Things M.I.N.D always says, in English and Tamil
PHRASES = {
    "yes": ("Yes?", "சொல்லுங்க சார்?"),
    "reminder": ("Reminder: ", "நினைவூட்டல்: "),
    "online": ("M.I.N.D online.", "M.I.N.D ரெடி."),
    "welcome": ("Welcome back, {}.", "வணக்கம் {}."),
    "hint": ("Say {} when you need me.", "தேவைப்படும்போது {} சொல்லுங்க."),
}

def phrase(key, *values):
    return PHRASES[key][1 if tamil_mode() else 0].format(*values)

def announce_reminders():
    for text in due_reminders():
        speak(phrase("reminder") + text)

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
if server.hud_ready():
    print(f"HUD: http://localhost:{server.PORT}")
    webbrowser.open(f"http://localhost:{server.PORT}")
else:
    print("HUD not built yet. From the M.I.N.D folder run: npm run build")

calibrate()
welcome = " " + phrase("welcome", profile["name"]) if profile.get("name") else ""
speak(phrase("online") + welcome + " " + phrase("hint", wake_word()))

# Wait for the wake word (or an orb click / typed command), talk, then wait again
running = True
while running:
    woke = wait_for_wake(lambda: reminder_due() or state.has_input())
    announce_reminders()
    if woke and not state.has_input():
        speak(phrase("yes"))
    if woke or state.has_input():
        running = conversation()

state.set_status("offline")
print("M.I.N.D offline.")
time.sleep(1)  # give the HUD a moment to show "offline"
