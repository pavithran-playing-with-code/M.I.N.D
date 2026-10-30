# Getting to know you: once a day M.I.N.D reads the day's conversations (from the diary) and which
# apps/projects/sites you spent time on, and updates a small notebook about you: people, likes, habits,
# work, what's going on in your life, how you like it to talk. The live brain reads the notebook at the
# start of every talk, so after a few weeks it really knows you.
# Saved in knowledge.json (personal, git-ignored). Only app names, projects and site names are counted
# for time, never page titles, messages or what's in them.
import os
import re
import json
import time
import datetime
import threading
from memory import BASE_DIR
import diary

FILE = os.path.join(BASE_DIR, "knowledge.json")
TOPICS = {  # notebook sections: what goes in each (shown to the brain that writes it)
    "people": "people in their life and who they are (\"Jenny: friend\", \"Siva Chithappa: uncle\")",
    "likes": "things they love or dislike: songs, artists, food, games, shows",
    "habits": "when and how they usually do things (\"works on dFresh in the mornings\", \"lofi while coding\")",
    "work": "their projects and what they're building or fixing lately",
    "life": "what's going on in their life right now, with the date (\"interview on Fri 7 Nov\")",
    "style": "how they like Mind to talk or behave (\"short answers\", \"hates being asked to test\")",
}
MOST = 12          # items per section (old, less useful ones get dropped by the writer)
CATCH_UP_DAYS = 7  # days not learned yet (laptop off at night): learn them at the next start
lock = threading.Lock()

def load():
    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("about", {})
    data.setdefault("days", {})
    data.setdefault("usage", {})
    return data

book = load()

def save():
    with lock:
        temp = FILE + ".part"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(book, f, ensure_ascii=False, indent=1)
        os.replace(temp, FILE)

# ---------- Time spent: app, project or site, in minutes per day ----------
def what_kind(app, title):
    # "dfresh - App.jsx - Visual Studio Code" -> "VS Code: dfresh"; "Rathinamo - YouTube - Google Chrome"
    # -> "Chrome: YouTube"; other apps -> their name. Nothing personal (no page/message titles).
    title = re.sub(r"\s+[-–—]\s+(Google Chrome|Microsoft Edge)$", "", title)
    parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+", title) if p.strip()]
    if app == "Code":
        names = [p for p in parts if p != "Visual Studio Code"]
        project = names[-1] if names else ""
        return "VS Code: " + project[:30] if project else "VS Code"
    if app in ("chrome", "msedge"):
        site = parts[-1] if parts else ""
        return ("Chrome: " + site[:30]) if site and len(site) <= 30 else "Chrome"
    nice = {"WhatsApp.Root": "WhatsApp", "explorer": "File Explorer"}.get(app, app)
    return nice[:30]

def count_time():
    # Every 30 s: +0.5 min for whatever's in front, while they're actually using the laptop
    import pc
    import alerts
    while True:
        time.sleep(30)
        try:
            if alerts.idle_seconds() > 120 or not pc.activity:
                continue
            t, app, title = pc.activity[-1]
            day = datetime.date.today().isoformat()
            used = book["usage"].setdefault(day, {})
            kind = what_kind(app, title)
            used[kind] = used.get(kind, 0) + 0.5
        except Exception:
            pass

# ---------- Learning a day ----------
RULES = ("You keep a small private notebook about the owner of a voice assistant called Mind, so Mind can be "
         "a real friend who knows them. You get the notebook so far, one day's conversations with Mind, and "
         "how long they spent in which apps/projects/sites. Update the notebook and summarise the day.\n"
         "Sections:\n" + "\n".join(f"- {k}: {v}" for k, v in TOPICS.items()) + "\n"
         f"Rules: keep every useful old item unless the day shows it changed; add only what the day CLEARLY shows "
         f"(no guesses, nothing about Mind's own bugs or testing). Short items (max 15 words), max {MOST} per "
         "section, merge duplicates, drop 'life' items whose date has passed by over a week. Never keep passwords, "
         "codes, money or account numbers, or private details about other people beyond who they are.\n"
         "Answer with JSON only: {\"about\": {section: [items]}, \"summary\": \"one or two sentences: what "
         "they did and talked about that day\"}")

def turns_of(day):
    start = datetime.datetime.combine(day, datetime.time()).timestamp()
    end = start + 86400
    return [e for e in diary.entries() if start <= e["t"] < end]

def learn_day(day):
    # Reads one finished day and updates the notebook. Returns True when done (or nothing to learn).
    import brain
    turns = turns_of(day)
    used = book["usage"].get(day.isoformat(), {})
    if not turns and sum(used.values()) < 10:
        book["days"][day.isoformat()] = ""  # nothing that day
        return True
    talk = "\n".join(f"{datetime.datetime.fromtimestamp(e['t']):%I:%M %p} they: {e['you'][:200]}"
                     + (f" | done: {e['did'][:120]}" if e.get("did") else "") + f" | Mind: {e['said'][:150]}"
                     for e in turns[-150:])
    top = sorted(used.items(), key=lambda x: -x[1])[:12]
    usage = ", ".join(f"{k} {round(v)} min" for k, v in top if v >= 5) or "not counted"
    ask = (f"Notebook so far:\n{json.dumps(book['about'], ensure_ascii=False)}\n\n"
           f"Day: {day:%A %d %B %Y}\nTime spent: {usage}\nConversations with Mind:\n{talk or '(none)'}")
    answer = brain.write(RULES, ask, seconds=60)
    found = re.search(r"\{.*\}", answer or "", re.S)
    if not found:
        return False  # the writers are busy: try again later
    try:
        result = json.loads(found.group(0), strict=False)
    except ValueError:
        return False
    about = result.get("about") or {}
    book["about"] = {k: [str(i)[:120] for i in about.get(k, [])][:MOST] for k in TOPICS if about.get(k)}
    book["days"][day.isoformat()] = str(result.get("summary", ""))[:300]
    return True

def catch_up():
    # Learns every finished day of the last week that wasn't learned yet (oldest first)
    today = datetime.date.today()
    learned = False
    for back in range(CATCH_UP_DAYS, 0, -1):
        day = today - datetime.timedelta(days=back)
        if day.isoformat() in book["days"]:
            continue
        if not learn_day(day):
            break  # try again in a while
        learned = True
        print(f"(Learned from {day:%a %d %b}: {book['days'][day.isoformat()][:100]})")
    # Forget usage older than 60 days
    old = (today - datetime.timedelta(days=60)).isoformat()
    book["usage"] = {d: u for d, u in book["usage"].items() if d >= old}
    book["days"] = {d: s for d, s in book["days"].items() if d >= old}
    if learned:
        save()

def keep_learning():
    # A finished day is learned after midnight, or at the next start if the laptop was off
    time.sleep(60)  # (start-up first)
    while True:
        try:
            catch_up()
            save()  # (also keeps today's time counts)
        except Exception as e:
            print("(Learning failed:", str(e)[:100] + ")")
        time.sleep(600)

def start():
    threading.Thread(target=count_time, daemon=True).start()
    threading.Thread(target=keep_learning, daemon=True).start()

# ---------- What the live brain is told ----------
def notes():
    # The notebook as a few lines for the start of a talk, plus the last few days in one line each
    lines = []
    names = {"people": "People", "likes": "Likes", "habits": "Habits", "work": "Work", "life": "Going on",
             "style": "How they like you"}
    for key, items in book["about"].items():
        if items:
            lines.append(f"{names.get(key, key)}: " + "; ".join(items))
    recent = [(d, s) for d, s in sorted(book["days"].items())[-3:] if s]
    for d, s in recent:
        lines.append(f"{datetime.date.fromisoformat(d):%a %d %b}: {s}")
    return "\n".join(lines)

def day_summaries(start, end):
    # For recall ("what did I do last week?"): the learned one-line summaries of those days
    return [(d, s) for d, s in sorted(book["days"].items())
            if s and start <= datetime.datetime.fromisoformat(d).timestamp() < end]

def forget(words):
    # "Forget that I like X": drops notebook items that share most of the words
    def stems(text):  # "loves" and "love" match (first 4 letters), filler words don't count
        return {w[:4] for w in re.findall(r"\w+", text.lower())
                if len(w) > 2 and w not in diary.FILLER | {"forget", "remember", "anymore"}}
    want = stems(words)
    removed = []
    for key, items in book["about"].items():
        for item in list(items):
            have = stems(item)
            if want and len(want & have) >= max(1, len(want) * 0.6):
                items.remove(item)
                removed.append(item)
    if removed:
        save()
    return removed
