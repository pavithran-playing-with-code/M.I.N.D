# Limits: how much of Groq's free daily allowance is left, for the HUD's "Free limits" card.
# Every Groq answer says how many requests are left today; we keep the latest numbers.
import time
import threading

NAMES = {  # what to call each Groq model on the HUD
    "openai/gpt-oss-120b": "Brain (main)",
    "openai/gpt-oss-20b": "Brain (backup)",
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
    if left is None or limit is None:
        return
    with lock:
        entry = usage.setdefault(model, {"busy_until": 0})
        entry.update(left=int(left), limit=int(limit))

def note_busy(model, seconds):
    # Groq said "wait": only show it on the HUD if it's a long wait (the daily limit, not a short pause)
    if seconds < 60:
        return
    with lock:
        usage.setdefault(model, {"left": 0, "limit": 0})["busy_until"] = time.time() + seconds

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
