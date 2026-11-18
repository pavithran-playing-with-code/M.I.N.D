# The Life dashboard ("Mind, show my week"): one HUD screen of the last days.
# Coding hours per project, where the time went (apps / sites), the day's rhythm (which half-hours were used:
# first and last use = up and to bed), how many things they asked Mind, voice mood, and their mail.
# Everything comes from what M.I.N.D already counts on this laptop (learn.py, diary.py, gmail.py): nothing new
# goes online except the Gmail check, and nothing here is saved anywhere.
import datetime
import re
import threading
import time

adding = threading.Lock()

def days_back(days):
    today = datetime.date.today()
    return [today - datetime.timedelta(days=n) for n in range(days - 1, -1, -1)]

def nice_name(kind):
    kind = re.sub(r"^Chrome: \(\d+\)\s*", "Chrome: ", kind)  # "(12) YouTube" = YouTube
    return kind.replace("Chrome: ", "").replace("VS Code: ", "")

def summary(days=7):
    # The quick part (all from this laptop, ~instant)
    import learn
    days = max(1, min(int(days or 7), 31))
    dates = days_back(days)
    rows, totals, projects = [], {}, {}
    for d in dates:
        key = d.isoformat()
        used = learn.book["usage"].get(key, {})
        coding = {}
        for kind, minutes in used.items():
            if learn.SKIP_KINDS.match(kind) or nice_name(kind) in ("localhost_/live",):
                continue
            name = nice_name(kind)
            totals[name] = totals.get(name, 0) + minutes
            if kind.startswith("VS Code: "):
                coding[name] = coding.get(name, 0) + minutes
                projects[name] = projects.get(name, 0) + minutes
        hours = learn.book.get("hours", {}).get(key)
        active = [i for i, m in enumerate(hours or []) if m > 0]
        rows.append({"day": key, "label": d.strftime("%a"), "date": d.strftime("%d %b"),
                     "laptop": round(sum(m for k, m in used.items() if not learn.SKIP_KINDS.match(k))),
                     "coding": {k: round(v) for k, v in coding.items()},
                     "rhythm": hours or None,
                     "first": slot_time(active[0]) if active else "", "last": slot_time(active[-1] + 1) if active else "",
                     "asked": len(learn.turns_of(d)), "mood": learn.book.get("mood", {}).get(key, {})})
    top = sorted(totals.items(), key=lambda x: -x[1])[:8]
    coding_total = sum(projects.values())
    mood = {}
    for row in rows:
        for k, n in row["mood"].items():
            mood[k] = mood.get(k, 0) + n
    return {"days": rows, "top": [{"name": k, "minutes": round(v)} for k, v in top],
            "projects": [{"name": k, "minutes": round(v)} for k, v in sorted(projects.items(), key=lambda x: -x[1])[:6]],
            "coding_total": round(coding_total), "laptop_total": sum(r["laptop"] for r in rows),
            "asked_total": sum(r["asked"] for r in rows), "mood": mood, "since": dates[0].strftime("%d %b")}

def slot_time(slot):
    hour, half = divmod(slot % 48, 2)
    return f"{(hour % 12) or 12}:{'30' if half else '00'} {'AM' if hour < 12 else 'PM'}"

# ---------- Mail part (asks Gmail, a few seconds) ----------
MONEY = re.compile(r"(?:rs\.?|inr|₹)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", re.I)
SPENT = re.compile(r"\b(debited|spent|paid|withdrawn|purchase|sent to|transferred to|dr\.?)\b", re.I)
GOT = re.compile(r"\b(credited|received|refund|cr\.?|deposited)\b", re.I)
BANKISH = re.compile(r"(bank|upi|a/c|account|card|transaction|txn)", re.I)

def mail_part(days=7):
    import gmail
    if not gmail.ready():
        return {"ready": False}
    days = max(1, min(int(days or 7), 31))
    since = (datetime.date.today() - datetime.timedelta(days=days - 1))
    per_day = {d.isoformat(): 0 for d in days_back(days)}
    accounts = {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as pool:  # (all accounts and the money search side by side: was 20 s one by one)
        spending = pool.submit(money, days)
        for job in [pool.submit(count_one, a, p, since, per_day, accounts) for a, p in gmail.accounts()]:
            job.result()
        found = spending.result()
    return {"ready": True, "per_day": per_day, "accounts": accounts, "money": found}

def count_one(address, password, since, per_day, accounts):
    # One account's mails per day since `since` (INTERNALDATE only: no mail is opened) + its unread count
    import gmail
    try:
        box = gmail.connect(address, password)
        try:
            box.select("INBOX", readonly=True)
            status, data = box.uid("search", None, "SINCE", since.strftime("%d-%b-%Y"))
            uids = data[0].split() if status == "OK" and data and data[0] else []
            count = 0
            if uids:
                status, info = box.uid("fetch", b",".join(uids), "(INTERNALDATE)")
                for item in info or []:
                    text = item.decode(errors="ignore") if isinstance(item, bytes) else ""
                    when = re.search(r'INTERNALDATE "([^"]+)"', text)
                    if when:
                        day = datetime.datetime.strptime(when.group(1)[:11], "%d-%b-%Y").date().isoformat()
                        if day in per_day:
                            with adding:  # (the accounts are counted side by side)
                                per_day[day] += 1
                            count += 1
            status, data = box.uid("search", None, "UNSEEN")
            unread = len(data[0].split()) if status == "OK" and data and data[0] else 0
            accounts[address.split("@")[0]] = {"received": count, "unread": unread}
        finally:
            try:
                box.logout()
            except Exception:
                pass
    except Exception as e:
        accounts[address.split("@")[0]] = {"problem": str(e)[:80]}

def money(days):
    # Bank alert mails of these days: amounts debited / credited (a guide only: some banks write it differently)
    import gmail
    found = gmail.search(f"(debited OR credited OR spent OR \"UPI\") newer_than:{days}d", 40, True, peek=8000)
    spent, got, items = 0.0, 0.0, []
    for mail in found:
        text = mail["subject"] + " " + mail["text"][:800]
        if not BANKISH.search(text):
            continue
        amount = MONEY.search(text)
        if not amount:
            continue
        value = float(amount.group(1).replace(",", ""))
        out = SPENT.search(text)
        into = GOT.search(text)
        if out and (not into or out.start() < into.start()):
            spent += value
            kind = "spent"
        elif into:
            got += value
            kind = "got"
        else:
            continue
        items.append({"kind": kind, "amount": value, "from": mail["name"][:30], "when": mail["when"].strftime("%d %b") if mail["when"] else ""})
    return {"spent": round(spent), "got": round(got), "items": items[:8]}

def life_dashboard(days=7):
    # The brain's tool: show it on the HUD, and give the brain a short summary to say
    import showcase
    days = max(1, min(int(days or 7), 31))
    data = summary(days)
    showcase.put_on_hud({"kind": "life", "title": "Your last day" if days == 1 else f"Your last {days} days",
                         "days": days, "at": time.time()}, minutes=30)
    top = ", ".join(f"{p['name']} {p['minutes'] // 60}h{p['minutes'] % 60:02d}" for p in data["projects"][:3])
    return (f"Life dashboard is on the HUD. Last {days} days: {data['laptop_total'] // 60} h on the laptop, "
            f"{data['coding_total'] // 60} h coding ({top or 'no coding counted'}), asked Mind "
            f"{data['asked_total']} things. Say 1-2 friendly sentences about it, no list.")
