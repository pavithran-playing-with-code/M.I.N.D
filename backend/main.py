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

class DailyLog:
    # Everything M.I.N.D prints ALSO goes, with the time, into logs/mind_log.txt (opens in Notepad):
    # ONE file with the last 7 days (each day starts with a "===== 2026-10-20 =====" line), kept across
    # restarts, to look back at how the week went and improve M.I.N.D.
    # (Talk that wasn't for M.I.N.D is never printed, so it's never saved either.)
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    path = os.path.join(folder, "mind_log.txt")
    KEEP_DAYS = 7
    def __init__(self, screen):
        self.screen, self.new_line = screen, True
        os.makedirs(self.folder, exist_ok=True)
        self.day = self.tidy()
        self.file = open(self.path, "a", encoding="utf-8", buffering=1)
    def tidy(self):
        # Moves old one-file-per-day logs in, drops days older than a week. Returns the last day in the file.
        try:
            for name in sorted(os.listdir(self.folder)):
                if re.fullmatch(r"mind_\d{4}-\d{2}-\d{2}\.txt", name):
                    old = os.path.join(self.folder, name)
                    with open(old, encoding="utf-8") as f, open(self.path, "a", encoding="utf-8") as out:
                        out.write(f"\n===== {name[5:15]} =====\n" + f.read())
                    os.remove(old)
            if not os.path.exists(self.path):
                return None
            with open(self.path, encoding="utf-8") as f:
                lines = f.readlines()
            cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - self.KEEP_DAYS * 86400))
            days = [(i, line[6:16]) for i, line in enumerate(lines) if line.startswith("===== ")]
            first = next((i for i, day in days if day > cutoff), len(lines))
            if first:
                with open(self.path, "w", encoding="utf-8") as f:
                    f.writelines(lines[first:])
            return days[-1][1] if days and days[-1][1] > cutoff else None
        except Exception:
            return None
    def write(self, text):
        self.screen.write(text)
        try:
            today = time.strftime("%Y-%m-%d")
            if today != self.day:  # a new day: a header line
                self.day = today
                self.file.write(f"\n===== {today} ({time.strftime('%A')}) =====\n")
                self.new_line = True
            for piece in text.splitlines(keepends=True):
                if self.new_line:
                    self.file.write(time.strftime("[%I:%M:%S %p] "))
                self.file.write(piece)
                self.new_line = piece.endswith("\n")
        except Exception:
            pass  # the log file must never break M.I.N.D
        return len(text)
    def flush(self):
        self.screen.flush()
    def __getattr__(self, name):
        return getattr(self.screen, name)

sys.stdout = sys.stderr = DailyLog(sys.stdout)

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
import floating
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
    "online": (["Mind online.", "Mind online, Sir.", "Mind's on. Ready when you are."], ["Mind ரெடி சார்!"]),
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
GREETING = re.compile(r"^\W*(?:hey|hi|hai|hello|ok|okay|yo|ஹே|ஹாய்)[\s,.!-]+[^\s,.!?]+[\s,.!?-]*", re.I)

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
    elif len(ears.last_wake.split()) > 1 and GREETING.match(text):
        # The listener heard "hey mind" and Whisper wrote a greeting + some word ("Hey man, ...").
        # Without the greeting it's someone else talking (Tamil chat once opened a WhatsApp chat)
        command = text[GREETING.match(text).end():]
    else:
        if text:
            print("(Heard talking without 'mind', ignored)")
        return None
    if not text.strip(" .,!?"):
        return None  # nothing clear was heard: stay quiet (it used to say "Hmm?")
    print(f"You: {text}")
    state.add_message("you", text)
    ears.judge_tone()  # how it sounded (louder/faster than usual...)
    return command.strip(" .,!?")

WAIT_SECONDS = 1.5  # thinking longer than this? say "One sec." so you know it's working

own_voice_until = 0.0  # while "One sec." plays, the mic hears M.I.N.D itself: don't treat it as "stop"

def say_quietly(line):
    # A short line in the background ("One sec."), without stopping the thinking
    import voice
    def play():
        global own_voice_until
        try:
            own_voice_until = time.time() + 3
            path, *rest = voice.make_audio(line)
            voice.play_file(path, *rest)
            state.add_message("mind", line)
            while voice.file_playing():
                time.sleep(0.05)
        except Exception as e:
            print("Couldn't say:", line, e)
        finally:
            own_voice_until = time.time() + 0.4  # a moment for the room echo to die down
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
            if time.time() < own_voice_until:
                rec.Reset()  # that was M.I.N.D's own "One sec.", not you
                heard = ""
            if state.take_click() or state.muted or any(w in heard for w in words):
                brain.cancelled.set()
                print("(Cancelled the thinking)")
                return None
    finally:
        close_mic(stream)
    return result.get("answer", ("", None))

quiet_now = False  # True after "stop" / "bye" / interrupting: don't listen for follow-ups

def respond(text):
    # Answer one thing you said. Returns False if you asked M.I.N.D to shut down.
    global quiet_now
    quiet_now = False
    if wants_sleep(text):
        # "Mind, stop": go silent right away (no reply) and wait for "mind" again
        print("(Going quiet)")
        quiet_now = True
        return True
    state.set_status("thinking")
    start = time.time()
    result = think_or_cancel(text)
    if result is None:
        quiet_now = True  # you cancelled: stay quiet
        return True
    reply, action = result
    print(f"   (thought in {time.time() - start:.1f}s, by {brain.MODELS[brain.active][0]})")
    if reply and speak(reply):
        quiet_now = True  # you stopped it talking ("stop" / orb tap)
    if action in ("end", "shutdown"):
        quiet_now = True  # "bye", music started...
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
    if profile.get("floating"):
        floating.show(profile.get("floating_position", "bottom-right"), profile.get("floating_offset", (0, 0)))  # the floating window, if you had it on
else:
    print("HUD not built yet. From the M.I.N.D folder run: npm run build")

calibrate()
# Get everyday lines ready in the background so they play instantly
everyday = OKAYS + [line.format(wake_word()) for key in ("yes", "sleep") for line in PHRASES[key][1 if tamil_mode() else 0]]
everyday += [line for key in ("wait", "online") for line in PHRASES[key][1 if tamil_mode() else 0]]
everyday += server.OFF_LINES + ["Done.", "There you go.", "Closed.", "Opened WhatsApp.", "Okay, never mind.", "Alright, cancelled.",
             "Turning it up.", "Louder it is.", "Turning it down.", "Bringing it down a bit.", "Next one coming up.",
             "Skipping!", "Got it, I'll remind you.", "Noted!", "Alright, I'm here if you need me.", "Cool, catch you later."]
speak(phrase("online"))  # "Mind online."
warm_up(everyday)  # after it, so the two don't make the same line at the same time

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
        # ("no, not depression, dfresh"). Not after "stop", "bye" or interrupting it.
        while running and not quiet_now and not state.has_input() and not state.muted:
            more = listen(should_stop=lambda: state.has_typed() or state.muted, start_timeout=FOLLOW_UP_SECONDS)
            if not more or len(re.sub(r"\W", "", more)) < 3:
                break  # nothing, or just a noise like "DL"
            called = CALLED.search(more)
            running = respond(more[called.end():].strip(" .,!?") if called and called.start() == 0 else more)
    while running and state.has_input():
        running = handle_waiting_input()  # you talked over the reply

state.set_status("offline")
telegram_bot.say_off()  # "shut down" by voice: tell your phone
print("M.I.N.D offline.")
time.sleep(1)  # give the HUD a moment to show "offline"
