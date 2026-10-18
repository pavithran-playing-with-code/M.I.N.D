# Limits: how much of Groq's free daily allowance is left, for the HUD's "Free limits" card.
# Every Groq answer says how many requests are left today; we keep the latest numbers.
import time
import threading

NAMES = {  # what to call each Groq model on the HUD
    "openai/gpt-oss-120b": "Brain (main)",
    "openai/gpt-oss-20b": "Brain (backup)",
    "gemini-3.5-flash-lite": "Brain (Gemini Lite)",
    "gemini-3.1-flash-lite": "Brain (Gemini Lite 2)",
    "gemini-3.5-flash": "Brain (Gemini)",
    "qwen/qwen3.8-27b": "Brain (backup 2)",
    "whisper-large-v3": "Hearing",
    "orpheus": "Voice (Austin)",
}
lock = threading.Lock()
usage = {}  # model -> {"left": requests left today, "limit": per day, "busy_until": time it's free again}

def note(model, headers):
    # Read the "requests left today" numbers from a Groq answer
    left = headers.get("x-ratelimit-remaining-requests")
    limit = headers.get("x-ratelimit-limit-requests")
    with lock:
        entry = usage.setdefault(model, {"busy_until": 0})
        if left is not None and limit is not None:
            entry.update(left=int(left), limit=int(limit))
        entry["busy_until"] = 0  # it just answered, so it's not resting

def note_busy(model, seconds):
    # Groq said "wait": only show it on the HUD if it's a long wait (the daily limit, not a short pause)
    if seconds < 60:
        return
    with lock:
        usage.setdefault(model, {"left": 0, "limit": 0})["busy_until"] = time.time() + seconds

def resting(model):
    # True if this model said "wait" a while ago and isn't free again yet
    with lock:
        return usage.get(model, {}).get("busy_until", 0) > time.time()

def snapshot():
    now = time.time()
    with lock:
        rows = []
        for model, name in NAMES.items():
            entry = usage.get(model)
            if not entry:
                continue
            busy = entry.get("busy_until", 0) > now
            rows.append({"name": name, "left": entry.get("left"), "limit": entry.get("limit"),
                         "busy_until": time.strftime("%I:%M %p", time.localtime(entry["busy_until"])) if busy else None})
        return rows
