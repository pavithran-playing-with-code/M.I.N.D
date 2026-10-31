# Are you on a call? While you are, M.I.N.D doesn't listen and doesn't speak (it saves what it wanted to say).
# The sound system knows which app has the microphone open right now, and call apps show a call window.
# A call on your PHONE can't be seen from the laptop: for that, ears.py notices when you've been talking
# without saying "Mind", and "Mind, I'm on a call" (do_not_disturb) makes it quiet for as long as you say.
import time
import threading
import win32gui
import audio
import state
from memory import profile

NOT_CALLS = ("wispr", "audiodg", "svchost", "rundll32", "soundrecorder", "speechux")  # (dictation and Windows itself use the mic too)
CHECK_EVERY = 3
checked = {"at": 0.0, "call": ""}

def call_window():
    found = []
    def check(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            # (exactly these: a chat merely called "video call ideas" isn't a call)
            if title in ("video call", "voice call") or title.startswith(("zoom meeting", "meet - ")):
                found.append(title)
    win32gui.EnumWindows(check, None)
    return found[0] if found else ""

def what_call():
    # The call going on, in a few words, or "" if there's none
    window = call_window()
    if window:
        return window[:40]
    for app in audio.mic_apps():
        if not any(word in app for word in NOT_CALLS):
            return app.removesuffix(".exe")
    return ""

def in_call():
    if str(profile.get("call_quiet", True)).lower() in ("false", "off", "no"):
        return False
    if time.time() - checked["at"] > CHECK_EVERY:
        checked["at"] = time.time()
        try:
            checked["call"] = what_call()
        except Exception as e:
            print("Couldn't check for a call:", str(e)[:100])
    return bool(checked["call"])

# ---------- "Mind, I'm on a call" ----------
quiet_until = {"at": 0.0}

def do_not_disturb(minutes=30, off=False):
    # Tool: no listening, no talking for this long. Waits a moment, so its short reply can still be said.
    if off in (True, "true", "yes"):
        quiet_until["at"] = 0.0
        state.muted = False
        return "Quiet time is over: listening again."
    minutes = max(1, min(240, int(float(minutes or 30))))
    quiet_until["at"] = time.time() + minutes * 60
    def go_quiet():
        import settings
        settings.set_mic(False)
    threading.Timer(4, go_quiet).start()
    return f"Quiet for {minutes} minutes: no listening or talking. Say so in very few words. The core double-tap brings M.I.N.D back sooner."

def quiet_time_over():
    # main.py asks: was this quiet time, and has it ended?
    if quiet_until["at"] and time.time() >= quiet_until["at"]:
        quiet_until["at"] = 0.0
        return True
    return False
