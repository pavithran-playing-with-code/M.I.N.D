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
import os
import sys
import time
import re
import random
import socket
import threading
import webbrowser
if sys.stdout is None:
    # Running in the background (no window): write what M.I.N.D prints to mind.log instead
    log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mind.log"), "w",
               encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = sys.stderr = log
else:
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
        import hud
        hud.open_hud()
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
import hud
taskbar.show(True)
atexit.register(taskbar.show, False)
atexit.register(hud.close_hud)  # close the HUD window when M.I.N.D closes
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
import ears
from ears import calibrate, listen, wait_for_wake, wake_word, wake_words, phrase_listener, open_mic, close_mic, hear, to_text
from voice import speak, warm_up, STOP_WORDS
import brain
from brain import think
from tools import reminder_due, due_reminders, OKAYS
from memory import tamil_mode
import state
import server
import info
import alerts
import telegram_bot

# Things M.I.N.D always says: (English choices, Tamil choices). One is picked at random,
# so it doesn't sound like a robot saying the same line every time.
PHRASES = {
    "yes": (["What do you need, Sir?", "Yes, Sir?", "Tell me, Sir."], ["சொல்லுங்க சார்?", "என்ன வேணும் சார்?"]),
    "wait": (["One sec.", "Let me check.", "On it."], ["ஒரு நிமிஷம்.", "பாக்குறேன்."]),
    "reminder": (["Hey, reminder: "], ["ஞாபகம் இருக்கா? "]),
    "online": (["I'm up.", "Ready, Sir.", "Online."], ["ரெடி சார்!"]),
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
        telegram_bot.notify("⏰ Reminder: " + text)  # also on your phone, if it's connected
        speak(phrase("reminder") + text)
    while state.alerts:
        speak(state.alerts.popleft())

FOLLOW_UP_SECONDS = 6  # how long M.I.N.D keeps listening after it answers

# ---------- "Mind" must be said ----------
# M.I.N.D only answers when you say its name: "Mind, play a song", "Hey mind, what's the time",
# or "Hey mind" ... "Yeah?" ... and then the command. Anything else is ignored (and costs nothing).
# "Mind" the way Whisper may write it (accents differ: "Hey mine", "Hey Maind", மைண்ட், மைன்ட்...)
CALLED = re.compile(r"\b(?:(?:hey|hi|hai|hello|ok|okay|yo)[\s,]+)?(?:mind|mynd|maind|mine|myind)\b[\s,.!?-]*"
                    r"|(?:ஹே\s*)?மை(?:ண்|ன்)(?:ட்|டு)?[\s,.!?-]*", re.I)
# A greeting plus one word at the start ("Hey man, ...", "Hi Mai, ...") = how you called M.I.N.D
GREETING = re.compile(r"^\W*(?:hey|hi|hai|hello|ok|okay)\W+\w+\W*", re.I)

# How Whisper may write a plain "Mind" at the start, when the listener heard "mind"
MIND_LIKE = {"mind", "mine", "mined", "mint", "mynd", "maind", "mand", "myind", "maine"}

def squash(word):
    return re.sub(r"[^a-z]", "", word.lower())

def command_from(sound):
    # What you said after "mind". None = not said to M.I.N.D (ignore it), "" = only "mind" was said.
    text = to_text(sound, show=False)  # not logged unless it was said to M.I.N.D
    called = CALLED.search(text)
    if called:
        command = text[called.end():]
    elif ears.last_wake == "mind" and text.split() and squash(text.split()[0]) in MIND_LIKE:
        command = text.split(None, 1)[1] if len(text.split()) > 1 else ""
    elif ears.last_wake in ("hey mind", "hi mind") or len(ears.last_wake.split()) > 1:
        # The listener clearly heard "hey mind" but Whisper spelled it differently ("Hey man, ...")
        greeting = GREETING.match(text)
        command = text[greeting.end():] if greeting else text
    else:
        if text:
            print("(Heard talking without 'mind', ignored)")
        return None
    if not text.strip(" .,!?"):
        return None  # nothing clear was heard: stay quiet (it used to say "Hmm?")
    print(f"You: {text}")
    state.add_message("you", text)
    return command.strip(" .,!?")

WAIT_SECONDS = 1.5  # thinking longer than this? say "One sec." so you know it's working

def say_quietly(line):
    # A short line in the background ("One sec."), without stopping the thinking
    import voice
    def play():
        try:
            voice.play_file(*voice.make_audio(line))
            state.add_message("mind", line)
        except Exception as e:
            print("Couldn't say:", line, e)
    threading.Thread(target=play, daemon=True).start()

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
        started = time.time()
        said_wait = False
        while job.is_alive():
            if not said_wait and time.time() - started > WAIT_SECONDS:
                said_wait = True
                say_quietly(phrase("wait"))
            heard = hear(rec, stream)  # listens a quarter second
            if state.take_click() or state.muted or any(w in heard for w in words):
                brain.cancelled.set()
                print("(Cancelled the thinking)")
                return None
    finally:
        close_mic(stream)
    return result.get("answer", ("", None))

def respond(text):
    # Answer one thing you said. Returns False if you asked M.I.N.D to shut down.
    if wants_sleep(text):
        speak(phrase("sleep", wake_word()))
        return True
    state.set_status("thinking")
    start = time.time()
    result = think_or_cancel(text)
    if result is None:
        speak(random.choice(["Okay, never mind.", "Alright, cancelled."]))
        return True
    reply, action = result
    print(f"   (thought in {time.time() - start:.1f}s)")
    if reply:
        speak(reply)
    return action != "shutdown"

def handle_waiting_input():
    # Things that don't need "mind": typed in the HUD, or said while talking over M.I.N.D
    text = state.take_heard()
    if text is None:
        text = state.take_typed()
        if text is None:
            return True
        print("You (typed):", text)
        state.add_message("you", text)
    return respond(text)

# ---------- Start ----------
server.start()
info.auto_speed_test(profile.get("speed_test_minutes", 60))
info.auto_location()  # where you are, from Windows (the HUD never has to ask)
alerts.start()
telegram_bot.start()  # phone control (if TELEGRAM_BOT_TOKEN is in .env)
if server.hud_ready():
    print(f"HUD: http://localhost:{server.PORT}")
    hud.open_hud()  # its own app window (reused if already open)
else:
    print("HUD not built yet. From the M.I.N.D folder run: npm run build")

calibrate()
# Get everyday lines ready in the background so they play instantly
everyday = OKAYS + [line.format(wake_word()) for key in ("yes", "sleep") for line in PHRASES[key][1 if tamil_mode() else 0]]
everyday += ["Turning it up.", "Louder it is.", "Turning it down.", "Bringing it down a bit.", "Next one coming up.",
             "Skipping!", "Got it, I'll remind you.", "Noted!", "Alright, I'm here if you need me.", "Cool, catch you later."]
warm_up(everyday)
welcome = " " + phrase("welcome", profile["name"]) if profile.get("name") else ""
speak(phrase("online"))  # just a word or two

# Wait for "mind" (or an orb tap / typed command), answer, then wait again
running = True
while running:
    if state.muted:
        # Offline: mic off until you double-tap the orb again (reminders and alerts wait too)
        state.set_status("muted")
        time.sleep(0.3)
        continue
    sound = wait_for_wake(lambda: reminder_due() or state.alerts or state.has_input() or state.muted)
    announce_reminders()
    if state.has_input():
        running = handle_waiting_input()
    elif sound is not None:
        text = command_from(sound) if sound else ""  # b"" = the orb was tapped
        if text is None:
            continue  # "mind" wasn't said: not for us
        if not text:
            # Just "hey mind": ask, then take one command without needing "mind" again
            speak(phrase("yes"))
            text = listen(should_stop=lambda: state.has_typed() or state.muted)
            if not text:
                continue
        running = respond(text)
        # Follow-ups: for a few seconds after answering, you don't need to say "mind" again
        # ("no, not depression, dfresh")
        while running and not state.has_input() and not state.muted:
            more = listen(should_stop=lambda: state.has_typed() or state.muted, start_timeout=FOLLOW_UP_SECONDS)
            if not more:
                break
            called = CALLED.search(more)
            running = respond(more[called.end():].strip(" .,!?") if called and called.start() == 0 else more)
    while running and state.has_input():
        running = handle_waiting_input()  # you talked over the reply

state.set_status("offline")
telegram_bot.say_off()  # "shut down" by voice: tell your phone
print("M.I.N.D offline.")
time.sleep(1)  # give the HUD a moment to show "offline"
