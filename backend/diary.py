# Diary: M.I.N.D's long-term memory of your conversations: what you asked, what it did and
# what it said, so "what song did you play yesterday?" works days later.
# Saved in conversations.jsonl (personal, git-ignored), one line per turn, kept for 90 days.
# Only turns that were said TO M.I.N.D are saved (it heard "mind", you typed, or used the phone).
import os
import re
import json
import time
import datetime
import threading
from memory import BASE_DIR

FILE = os.path.join(BASE_DIR, "conversations.jsonl")
KEEP_DAYS = 90
SHOW = 12  # most turns given to the brain at once
lock = threading.Lock()

# Words that don't help find a conversation ("what did you ... yesterday")
FILLER = {"what", "which", "who", "when", "where", "did", "do", "does", "you", "your", "i", "me", "my", "we",
          "the", "a", "an", "was", "is", "were", "that", "this", "about", "to", "of", "in", "on", "for",
          "and", "or", "it", "we", "us", "say", "said", "tell", "told", "ask", "asked", "talk", "talked"}

def write(you, did, said):
    entry = {"t": round(time.time()), "you": you, "did": "; ".join(did), "said": said}
    try:
        with lock, open(FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        print("Couldn't save to the diary:", e)

def entries():
    try:
        with open(FILE, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return []

def trim():
    # Forget turns older than KEEP_DAYS (runs once at start)
    old = time.time() - KEEP_DAYS * 86400
    items = entries()
    keep = [e for e in items if e["t"] >= old]
    if len(keep) < len(items):
        with lock, open(FILE, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in keep)

def period(when):
    # (start, end) timestamps for "today", "yesterday", "this week", "last week", "this month"
    now = datetime.datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = today - datetime.timedelta(days=today.weekday())
    starts = {
        "today": (today, now),
        "yesterday": (today - datetime.timedelta(days=1), today),
        "this week": (monday, now),
        "last week": (monday - datetime.timedelta(days=7), monday),
        "this month": (today.replace(day=1), now),
    }
    start, end = starts.get(when, (now - datetime.timedelta(days=KEEP_DAYS), now))
    return start.timestamp(), end.timestamp() + 1

def day_name(t):
    day = datetime.date.fromtimestamp(t)
    today = datetime.date.today()
    if day == today:
        name = "Today"
    elif day == today - datetime.timedelta(days=1):
        name = "Yesterday"
    else:
        name = day.strftime("%a %d %b")
    return f"{name} {datetime.datetime.fromtimestamp(t).strftime('%I:%M %p').lstrip('0')}"

def recall(about="", when="", notes=False):
    # The recall tool: past conversations (or saved notes) about something and/or from a time
    if notes in (True, "true", "yes"):
        return read_notes(about)
    start, end = period(when)
    items = [e for e in entries() if start <= e["t"] < end]
    words = [w for w in re.findall(r"\w+", about.lower()) if w not in FILLER]
    if words:
        def score(e):
            text = f"{e['you']} {e['did']} {e['said']}".lower()
            return sum(w in text for w in words)
        found = [e for e in items if score(e)]
        # Best matches first, but if the words don't match (e.g. "song" vs "Rathinamo"),
        # give the brain the latest turns from that time so it can work it out itself
        items = sorted(found, key=score, reverse=True)[:SHOW] if found else items[-SHOW:]
    else:
        items = items[-SHOW:]
    if not items:
        return f"No conversations found{' ' + when if when else ''}."
    items.sort(key=lambda e: e["t"])
    lines = []
    for e in items:
        line = f"{day_name(e['t'])}: you said \"{e['you'][:120]}\""
        if e["did"]:
            line += f"; done: {e['did'][:120]}"
        line += f"; I said \"{e['said'][:100]}\""
        lines.append(line)
    return "Past conversations:\n" + "\n".join(lines)

def read_notes(about=""):
    from tools import NOTES_FILE
    try:
        with open(NOTES_FILE, encoding="utf-8") as f:
            notes = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        notes = []
    words = [w for w in re.findall(r"\w+", about.lower()) if w not in FILLER and w != "notes"]
    if words:
        notes = [n for n in notes if any(w in n.lower() for w in words)] or notes
    if not notes:
        return "There are no notes yet."
    return f"{len(notes)} notes. Latest:\n" + "\n".join(notes[-5:])

trim()
