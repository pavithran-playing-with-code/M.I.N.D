# Notes you can see: a card on the HUD, a screen on the phone, and by voice ("Mind, note: call the bank").
#   - tick when done, pin the important ones, delete
#   - a note with a time in it ("pay rent on the 1st", "call Penny tomorrow evening") reminds you then, by itself
#   - a note left undone for a few days gets ONE gentle "still on your list?" (max one a day, daytime only)
# Saved in backend/my_notes.json (git-ignored). The old notes.txt lines are moved in once.
import datetime
import json
import os
import re
import threading
import time

from memory import safe_write

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(BASE_DIR, "my_notes.json")
OLD_FILE = os.path.join(BASE_DIR, "notes.txt")
NUDGE_AFTER_DAYS = 3     # undone this long (and no time in it) = one gentle reminder
NUDGE_HOURS = (10, 20)   # only between 10 AM and 8 PM
lock = threading.Lock()
version = {"v": 0}       # goes up on every change: the HUD and phone refresh their list

def load():
    try:
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        pass
    notes = []
    try:  # the old notes.txt ("25 Nov 2026 05:30 PM - text"), moved in once
        with open(OLD_FILE, encoding="utf-8") as f:
            for i, line in enumerate(l.strip() for l in f if l.strip()):
                stamp, _, text = line.partition(" - ")
                try:
                    made = datetime.datetime.strptime(stamp, "%d %b %Y %I:%M %p").timestamp()
                except ValueError:
                    made, text = time.time(), line
                notes.append(new_note(text, made, i))
    except OSError:
        pass
    return notes

def new_note(text, made=None, n=0):
    made = made or time.time()
    return {"id": f"n{int(made * 1000)}{n}", "text": text.strip()[:500], "done": False, "pinned": False,
            "made": made, "due": None, "reminded": False, "nudged": 0}

notes = load()

def save():
    version["v"] += 1
    safe_write(FILE, json.dumps(notes, indent=1, ensure_ascii=False))

def listed():
    # For the HUD and phone: pinned first, then undone (newest first), then done
    shown = sorted(notes, key=lambda n: (n["done"], not n["pinned"], -n["made"]))
    return {"v": version["v"], "notes": shown}

def find(which):
    # A note by its id, its number in the list ("2"), or its words ("the bank one")
    which = str(which or "").strip().lower()
    if not which:
        return None
    for n in notes:
        if n["id"] == which:
            return n
    order = listed()["notes"]
    number = re.fullmatch(r"#?(\d+)", which)
    if number and 0 < int(number.group(1)) <= len(order):
        return order[int(number.group(1)) - 1]
    words = [w for w in re.findall(r"\w+", which) if w not in ("the", "one", "note", "a", "my", "about", "that")]
    scored = [(sum(w in n["text"].lower() for w in words), not n["done"], n) for n in notes]
    best = max(scored, key=lambda s: (s[0], s[1]), default=None)
    return best[2] if best and best[0] else None

def when_text(ts):
    day = datetime.datetime.fromtimestamp(ts)
    today = datetime.date.today()
    name = "today" if day.date() == today else "tomorrow" if day.date() == today + datetime.timedelta(days=1) \
        else day.strftime("%a %d %b")
    return f"{name} {day.strftime('%I:%M %p').lstrip('0')}"

# ---------- Working out a time from the words (typed notes; the voice brain passes its own) ----------
TIME_WORDS = re.compile(r"\b(today|tonight|tomorrow|morning|evening|afternoon|night|noon|monday|tuesday|wednesday|"
                        r"thursday|friday|saturday|sunday|weekend|next week|\d{1,2}(:\d\d)?\s*(am|pm)|at \d|on the \d|"
                        r"\d+(st|nd|rd|th)|in \d+ (min|minute|hour|day)|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.I)
WHEN_RULES = """Find WHEN this note should remind its owner. Now is {now}.
Reply with JSON only: {{"at": "YYYY-MM-DD HH:MM"}} or {{"at": null}} if the note has no time or date in it.
A date with no time = 9:00 that morning. "morning" 9:00, "afternoon" 14:00, "evening" 18:00, "tonight"/"night" 20:00.
A time already past today = that time tomorrow."""

def work_out_time(note):
    # Background: a typed note with time words gets its reminder time from a quick free writer
    if not TIME_WORDS.search(note["text"]):
        return
    try:
        import brain
        now = datetime.datetime.now().strftime("%A %Y-%m-%d %H:%M")
        answer = brain.write(WHEN_RULES.format(now=now), note["text"], seconds=12, writers=brain.QUICK_WRITERS) or ""
        found = re.search(r"\{.*\}", answer, re.S)
        at = json.loads(found.group(0)).get("at") if found else None
        if at:
            due = datetime.datetime.strptime(at, "%Y-%m-%d %H:%M").timestamp()
            if due > time.time():
                with lock:
                    note["due"] = due
                    save()
    except Exception as e:
        print("(Couldn't work out a time for the note:", str(e)[:80] + ")")

# ---------- Changing notes (HUD, phone and voice all come here) ----------
def change(action, which="", text="", remind_in_seconds=None):
    action = (action or "add").lower().strip()
    with lock:
        if action == "add":
            if not text.strip():
                return "Nothing to note."
            note = new_note(text)
            if remind_in_seconds not in (None, "", 0, "0"):
                try:
                    note["due"] = time.time() + float(remind_in_seconds)
                except (TypeError, ValueError):
                    pass
            notes.append(note)
            save()
            if note["due"] is None:
                threading.Thread(target=work_out_time, args=(note,), daemon=True).start()
            return note
        if action == "clear_done":
            gone = [n for n in notes if n["done"]]
            notes[:] = [n for n in notes if not n["done"]]
            save()
            return f"Cleared {len(gone)} done notes."
        note = find(which)
        if not note:
            return None
        if action in ("done", "tick"):
            note["done"] = True
        elif action in ("undo", "not_done"):
            note["done"] = False
        elif action == "pin":
            note["pinned"] = not note["pinned"]
        elif action == "edit" and text.strip():
            note.update(text=text.strip()[:500], due=None, reminded=False)
            threading.Thread(target=work_out_time, args=(note,), daemon=True).start()
        elif action == "delete":
            notes.remove(note)
        elif action == "remind" and remind_in_seconds not in (None, ""):
            note.update(due=time.time() + float(remind_in_seconds), reminded=False)
        save()
        return note

def tool(action="add", text="", which="", remind_in_seconds=None):
    # The voice tool: "note: call the bank", "what's on my notes?", "tick off the bank one", "remind me about it tomorrow"
    action = (action or "add").lower().strip()
    if action == "list":
        open_ = [n for n in listed()["notes"] if not n["done"]]
        if not open_:
            return "No open notes."
        lines = [f"{i + 1}. {n['text']}" + (f" (reminds {when_text(n['due'])})" if n["due"] and not n["reminded"] else "")
                 + (" [pinned]" if n["pinned"] else "") for i, n in enumerate(open_[:15])]
        return f"{len(open_)} open notes (also on the HUD Notes card):\n" + "\n".join(lines)
    result = change(action, which, text, remind_in_seconds)
    if result is None:
        return f"No note matches '{which}'. Say 'what's on my notes' to hear them."
    if isinstance(result, str):
        return result
    if action == "add":
        due = f" I'll remind them {when_text(result['due'])}." if result["due"] else ""
        return f"Noted: {result['text']}.{due} It's on the HUD Notes card."
    if action == "delete":
        return f"Deleted the note: {result['text']}"
    return f"Done: {action} -> {result['text']}" + (f" (reminds {when_text(result['due'])})" if result["due"] else "")

# ---------- Reminding (checked every 15 s) ----------
def check():
    import alerts
    import memory
    me = memory.call_me()
    now = time.time()
    with lock:
        for n in notes:
            if n["due"] and not n["reminded"] and not n["done"] and n["due"] <= now:
                n["reminded"] = True
                save()
                alerts.said.pop("note_" + n["id"], None)
                alerts.say("note_" + n["id"], f"{me}, from your notes: {n['text']}",
                           f"உங்க notes-ல: {n['text']}", 0, urgent=True)
    hour = datetime.datetime.now().hour
    if not NUDGE_HOURS[0] <= hour < NUDGE_HOURS[1] or alerts.idle_seconds() > 300:
        return
    today = str(datetime.date.today())
    from memory import profile, save_profile
    if profile.get("notes_nudged") == today:
        return  # one gentle nudge a day at most
    old = [n for n in notes if not n["done"] and not n["due"] and now - n["made"] > NUDGE_AFTER_DAYS * 86400
           and now - n["nudged"] > NUDGE_AFTER_DAYS * 86400]
    if old:
        n = min(old, key=lambda x: x["made"])
        days = int((now - n["made"]) // 86400)
        with lock:
            n["nudged"] = now
            save()
        profile["notes_nudged"] = today
        save_profile()
        alerts.say("notenudge", f"{me}, you noted '{n['text'][:90]}' {days} days ago. (ASK: Still on your list, or is it done?)",
                   f"{days} நாள் முன்னாடி '{n['text'][:90]}'-னு note பண்ணீங்க. முடிஞ்சதா?", 0, phone=False)

def keep_checking():
    def loop():
        time.sleep(30)
        while True:
            try:
                check()
            except Exception as e:
                print("Notes check failed:", e)
            time.sleep(15)
    threading.Thread(target=loop, daemon=True).start()
