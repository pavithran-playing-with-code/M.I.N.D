# M.I.N.D: start here. Run from the backend folder with:  python main.py
#
# Files:
#   memory.py  profile.json (what M.I.N.D knows about you)
#   ears.py    wake word + speech to text (offline)
#   voice.py   speaking out loud (say "stop" to interrupt)
#   brain.py   understanding you and choosing tools (Groq)
#   tools.py   everything M.I.N.D can do (apps, websites, weather, reminders...)
import sys
import time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # so symbols like ° don't crash printing

from memory import profile
from ears import calibrate, listen, wait_for_wake, wake_word
from voice import speak
from brain import think
from tools import reminder_due, due_reminders

def announce_reminders():
    for text in due_reminders():
        speak(f"Reminder: {text}")

def conversation():
    # Keep talking without the wake word until: 2 silences in a row,
    # you say you're done, or you ask to shut down. Returns False to close M.I.N.D.
    missed = 0
    while True:
        announce_reminders()
        text = listen()
        if not text:
            missed += 1
            if missed >= 2:
                print("(Conversation ended, nothing heard)")
                return True
            speak("Sorry, I didn't catch that.")
            continue
        missed = 0
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
calibrate()
welcome = f" Welcome back, {profile['name']}." if profile.get("name") else ""
speak(f"M.I.N.D online.{welcome} Say {wake_word()} when you need me.")

# Wait for the wake word, then have a conversation, then wait again
running = True
while running:
    woke = wait_for_wake(reminder_due)  # True = wake word, False = a reminder is due
    announce_reminders()
    if woke:
        speak("Yes?")
        running = conversation()
print("M.I.N.D offline.")
