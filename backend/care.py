# Mind notices you: gentle check-ins, like a friend sitting next to you.
#   - a rough patch: builds keep failing, or you sound stressed (louder/faster than usual) several times
#   - lunch: still working at 2 PM without a real break since noon
#   - end of day: after a long coding day, a short "nice work" with what you did
# At most MAX_A_DAY of these a day, GAP_MINUTES apart, never at night (quiet hours) and never spoken on a call
# (alerts.say + main already handle calls). Switch: Control Center > "Check on me" (alert_care).
import datetime
import random
import time

import alerts
import memory
from memory import profile, save_profile

MAX_A_DAY = 3
GAP_MINUTES = 60
ROUGH_WINDOW = 30 * 60   # look at the last 30 minutes for a rough patch
ROUGH_FAILS = 3          # this many failed terminal runs in that window
ROUGH_TONES = 2          # or sounding stressed this many times
LUNCH_BREAK = 20 * 60    # away this long between 12 and 2:30 = you had lunch
WRAP_CODING = 120        # minutes of coding today before an end-of-day "nice work"

failures, tones = [], []
lunch = {"day": None, "had_break": False}

def note_failure():
    # terminals.py: a long command finished with an error
    failures.append(time.time())
    del failures[:-10]

def note_tone(hints):
    # ears.judge_tone: you said something to Mind louder/faster than usual
    if "louder" in hints or "faster" in hints:
        tones.append(time.time())
        del tones[:-10]

def recent(times):
    return sum(time.time() - t < ROUGH_WINDOW for t in times)

def allowed():
    # Today's count and spacing (kept in profile so a restart doesn't repeat them)
    today = str(datetime.date.today())
    log = profile.get("care", {})
    if log.get("day") != today:
        log = {"day": today, "count": 0, "last": 0, "said": []}
    ok = log["count"] < MAX_A_DAY and time.time() - log["last"] > GAP_MINUTES * 60
    return ok, log

def tell(kind, lines, tamil):
    ok, log = allowed()
    if not ok or kind in log["said"]:
        return False
    line = random.choice(lines)
    alerts.said.pop("care_" + kind, None)
    alerts.say("care_" + kind, line, tamil, 0, phone=False)
    if alerts.said.get("care_" + kind):  # (it was queued: not switched off / quiet hours)
        log.update(count=log["count"] + 1, last=time.time())
        log["said"].append(kind)
        profile["care"] = log
        save_profile()
        return True
    return False

def coding_today():
    # (minutes coding today, the top project) from the 30-second time counts
    try:
        import learn
        used = learn.book["usage"].get(datetime.date.today().isoformat(), {})
    except Exception:
        return 0, ""
    code = {k[len("VS Code: "):]: m for k, m in used.items() if k.startswith("VS Code: ")}
    top = max(code, key=code.get) if code else ""
    return sum(code.values()), top

def nice(minutes):
    hours, mins = int(minutes // 60), int(minutes % 60)
    if hours and mins >= 15:
        return f"{hours} and a half hours" if 15 <= mins < 45 else f"{hours + 1} hours"
    return f"{hours} hours" if hours else f"{mins} minutes"

def check():
    if alerts.idle_seconds() > 5 * 60:
        # Away: between 12 and 2:30 PM a 20-minute gap counts as lunch
        now = datetime.datetime.now()
        if 12 <= now.hour < 15 and alerts.idle_seconds() >= LUNCH_BREAK:
            lunch.update(day=str(now.date()), had_break=True)
        return
    me = memory.call_me()
    now = datetime.datetime.now()
    today = str(now.date())
    if lunch["day"] != today:
        lunch.update(day=today, had_break=False)

    # A rough patch
    if recent(failures) >= ROUGH_FAILS or recent(tones) >= ROUGH_TONES:
        if tell("rough", [
                f"Hey {me}, that one's been fighting you for a while. Maybe step away for two minutes? "
                "Fresh eyes fix bugs. (ASK: Want me to put on something chill?)",
                f"{me}, rough patch, huh? Take a breath, grab some water, it'll click. "
                "(ASK: Want some music while you work it out?)"],
                "கொஞ்சம் கஷ்டமா போகுது போல. ரெண்டு நிமிஷம் break எடுங்க, அப்புறம் சரியாயிடும்."):
            failures.clear(); tones.clear()
            return

    # Lunch: 2:00-3:30 PM, at the laptop since before noon, no real break
    if 14 <= now.hour < 15 or (now.hour == 15 and now.minute < 30):
        since = alerts.use.get("since")
        if not lunch["had_break"] and since and since < now.replace(hour=12, minute=0).timestamp():
            if tell("lunch", [f"{me}, it's past 2 and you haven't stepped away since noon. Did you eat? "
                              "Go grab lunch, I'll keep an eye on things.",
                              f"Lunch check, {me}! Don't skip it, the code will still be here."],
                    "மணி 2 ஆச்சு, சாப்பிட்டீங்களா? போய் சாப்பிட்டு வாங்க."):
                return

    # End of day: after 7 PM, after a long coding day
    if 19 <= now.hour < 23:
        minutes, top = coding_today()
        if minutes >= WRAP_CODING:
            what = f", mostly on {top}" if top else ""
            tell("wrap", [f"Solid day, {me}: about {nice(minutes)} of coding{what}. Don't forget to rest tonight.",
                          f"{me}, you put in {nice(minutes)} of code today{what}. Good work. Wrap up when you can."],
                 f"இன்னைக்கு {nice(minutes)} code பண்ணீங்க, நல்ல வேலை! கொஞ்சம் rest எடுங்க.")
