# Gmail: "Mind, any important mails?", "read the second one", "any mail from Penny?", "open it".
# Free and simple: Gmail's own IMAP door with an APP PASSWORD (no Google Cloud project, never expires).
# Needs in backend/.env:   GMAIL_ADDRESS=you@gmail.com   GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
# Several accounts: repeat the two lines for each one (pairs are read in order; _2, _3 names work too).
# (make the app password at https://myaccount.google.com/apppasswords ; needs 2-Step Verification on).
# Reading never marks mail as read. Writing = a Gmail draft first; sending and deleting (to Trash) only
# happen when their own words say send / delete (see mail_action below).
import email
import email.header
import email.policy
import email.utils
import html
import imaplib
import os
import re
import smtplib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

import state

CHECK_SECONDS = 120          # new important mail is looked for every 2 minutes
ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
last_list = []               # the mails from the last check_mail, so "read the second one" works
failed = []                  # [(account, error)] from the last search
lock = threading.Lock()      # one search at a time (each account gets its own connection)

def accounts():
    # [(address, app password)] from .env, in order. The same two names may repeat (one pair per account).
    # An address with no password yet is skipped.
    pairs, current = [], None
    try:
        with open(ENV, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        name, _, value = line.partition("=")
        name, value = name.strip().upper(), value.strip().strip('"').strip("'")
        if re.fullmatch(r"GMAIL_ADDRESS(_\d+)?", name):
            current = [value, ""]
            pairs.append(current)
        elif re.fullmatch(r"GMAIL_APP_PASSWORD(_\d+)?", name) and current is not None:
            current[1] = value.replace(" ", "")
    return [(a, p) for a, p in pairs if "@" in a and p]

def ready():
    return bool(accounts())

def account_for(words):
    # "tiger", "office mail" -> the accounts whose address has that word (all of them when none match)
    every = accounts()
    said = [w for w in re.findall(r"[a-z0-9]{3,}", (words or "").lower())
            if w not in ("gmail", "mail", "com", "account", "my", "the", "inbox")]
    picked = [(a, p) for a, p in every if any(w in a.lower() for w in said)]
    return picked or every

NOT_SET_UP = ("Gmail isn't connected yet. Tell them: make an app password at myaccount.google.com/apppasswords "
              "and put GMAIL_ADDRESS and GMAIL_APP_PASSWORD in backend/.env (repeat both for more accounts).")

def connect(address, password):
    box = imaplib.IMAP4_SSL("imap.gmail.com", timeout=15)
    box.login(address, password)
    return box

FOLDERS = {"\\All": '"[Gmail]/All Mail"', "\\Junk": '"[Gmail]/Spam"', "\\Trash": '"[Gmail]/Trash"',
           "\\Drafts": '"[Gmail]/Drafts"', "\\Sent": '"[Gmail]/Sent Mail"'}

def folder_with(box, flag):
    # Gmail's own folders (All Mail, Spam, Trash, Drafts) have other names in other languages; their flag doesn't
    status, folders = box.list()
    for line in folders or []:
        line = line.decode(errors="ignore")
        if re.search(re.escape(flag) + r"[ )]", line):
            return line.rsplit(' "/" ', 1)[-1]
    return FOLDERS[flag]

def all_mail_folder(box):
    return folder_with(box, "\\All")

def words(value):
    # "=?UTF-8?B?...?=" headers -> plain text
    try:
        return str(email.header.make_header(email.header.decode_header(value or ""))).strip()
    except Exception:
        return (value or "").strip()

def body_text(message):
    # The readable text of a mail (plain text, else the HTML with its tags taken out)
    try:
        part = message.get_body(("plain", "html"))
        content = part.get_content() if part else ""
        if part and part.get_content_type() == "text/html":
            content = re.sub(r"(?is)<(script|style).*?</\1>", " ", content)
            content = re.sub(r"(?s)<br\s*/?>|</p>|</div>|</tr>", "\n", content)
            content = html.unescape(re.sub(r"(?s)<[^>]+>", " ", content))
    except Exception:
        content = ""
    content = re.sub(r"[ \t ‌͏]+", " ", content)
    return re.sub(r"\n\s*\n+", "\n", content).strip()

def fetch(box, uids, account, folder="INBOX", peek_bytes=60000):
    # uids -> [{account, from, name, subject, when, text, link}]. Reading only (BODY.PEEK = stays unread).
    # All of them in ONE request (one by one took a round trip each: a 25-mail list was slow)
    if not uids:
        return []
    status, data = box.uid("fetch", b",".join(u if isinstance(u, bytes) else str(u).encode() for u in uids),
                           f"(UID FLAGS X-GM-THRID BODY.PEEK[]<0.{peek_bytes}>)")
    parts = {}
    for item in (data or []) if status == "OK" else []:
        if isinstance(item, tuple):
            number = re.search(rb"UID (\d+)", item[0])
            if number:
                parts[number.group(1)] = item
    found = []
    for uid in uids:
        item = parts.get(uid if isinstance(uid, bytes) else str(uid).encode())
        if not item:
            continue
        thread = re.search(rb"X-GM-THRID (\d+)", item[0])
        unread = b"\\Seen" not in item[0]
        message = email.message_from_bytes(item[1], policy=email.policy.default)
        name, sender = email.utils.parseaddr(words(message.get("From")))
        try:
            when = email.utils.parsedate_to_datetime(message.get("Date")).astimezone()
        except Exception:
            when = None
        found.append({"uid": uid.decode() if isinstance(uid, bytes) else uid, "account": account,
                      "folder": folder, "unread": unread, "message_id": message.get("Message-ID", ""),
                      "references": message.get("References", ""), "reply_to": message.get("Reply-To", ""),
                      "name": name or sender, "from": sender,
                      "subject": words(message.get("Subject")) or "(no subject)", "when": when,
                      "text": body_text(message),
                      "link": ("https://mail.google.com/mail/?authuser=" + account + "#all/" +
                               format(int(thread.group(1)), "x")) if thread else "https://mail.google.com/"})
    return found

def search_one(address, password, query, limit=5, everywhere=False, peek=60000):
    # Gmail's own search words work here ("is:unread is:important", "from:penny newer_than:7d")
    # (Gmail's normal search leaves out Spam and Trash, so "in:spam" / "in:trash" open those folders themselves)
    box = connect(address, password)
    try:
        if re.search(r"\bin:spam\b", query):
            folder, query = folder_with(box, "\\Junk"), re.sub(r"\bin:spam\b", "", query).strip()
        elif re.search(r"\bin:trash\b", query):
            folder, query = folder_with(box, "\\Trash"), re.sub(r"\bin:trash\b", "", query).strip()
        else:
            folder = all_mail_folder(box) if everywhere else "INBOX"
        box.select(folder, readonly=True)
        if query:
            status, data = box.uid("search", None, "X-GM-RAW", '"' + query.replace('"', "") + '"')
        else:
            status, data = box.uid("search", None, "ALL")
        uids = (data[0].split() if status == "OK" and data and data[0] else [])[-limit:][::-1]
        return fetch(box, uids, address, folder, peek)
    finally:
        try:
            box.logout()
        except Exception:
            pass

def search(query, limit=6, everywhere=False, chosen=None, peek=60000):
    # Every chosen account at once (side by side), newest first. Accounts that fail go in `failed`.
    global failed
    chosen = chosen or accounts()
    found, failed = [], []
    with lock, ThreadPoolExecutor(max(1, len(chosen))) as pool:
        jobs = [(a, pool.submit(search_one, a, p, query, limit, everywhere, peek)) for a, p in chosen]
        for address, job in jobs:
            try:
                found += job.result(timeout=40)
            except Exception as e:
                failed.append((address, e))
    found.sort(key=lambda m: m["when"].timestamp() if m["when"] else 0, reverse=True)
    return found[:limit]

def ago(when):
    if not when:
        return ""
    minutes = (time.time() - when.timestamp()) / 60
    if minutes < 60:
        return f"{max(1, int(minutes))} min ago"
    if minutes < 24 * 60:
        return f"{int(minutes // 60)} h ago"
    return when.strftime("%d %b")

def short(text, size):
    text = " ".join(text.split())
    return text if len(text) <= size else text[:size].rsplit(" ", 1)[0] + "..."

def problem_lines():
    return [f"Couldn't read {a}: " + ("Gmail refused the sign-in (app password wrong or removed)."
                                     if isinstance(e, imaplib.IMAP4.error) else "no answer (internet?).")
            for a, e in failed]

def check_mail(search_words="", which="", open_it=False, account="", show=False):
    # The brain's tool. which = "1"/"second"/"latest" -> that mail in full; open_it = open it in Gmail (Chrome);
    # account = a word of one account's address ("tiger"); empty = every account
    global last_list
    if not ready():
        return NOT_SET_UP
    if show in (True, "true", "yes"):
        return show_panel()
    if which or open_it:
        mail = pick(which or "1")
        if not mail:
            return "No mail to pick: list them first (check_mail with search words)."
        if open_it:
            import tools
            problem = tools.open_page(mail["link"])
            return problem or f"Opened '{mail['subject']}' in Gmail."
        return (f"In {mail['account']}: from {mail['name']} <{mail['from']}>, {ago(mail['when'])}. "
                f"Subject: {mail['subject']}\n" + short(mail["text"], 2500)
                + "\n(Say what it's about in 2-3 sentences, not word for word, unless asked.)")
    query = (search_words or "").strip()
    everywhere = bool(query) and "in:inbox" not in query
    chosen = account_for(account) if account else accounts()
    names = ", ".join(a for a, _ in chosen)
    if not query:
        # "any important mails?": unread important first, else any unread from the last 2 days
        last_list = search("is:unread is:important newer_than:3d", 8, chosen=chosen)
        title = "Unread important mail"
        if not last_list and len(failed) < len(chosen):
            last_list = search("is:unread newer_than:2d", 8, chosen=chosen)
            title = "Unread mail (none marked important)"
    else:
        last_list = search(query, 8, everywhere, chosen)
        title = f"Mail matching '{query}'"
    if not last_list:
        return " ".join(problem_lines() + [("Nothing unread right now" if not query else f"No mail matching '{query}'")
                                           + f" (checked {names})."])
    many = len(chosen) > 1
    lines = [f"{title} in {names} (newest first):"]
    for n, mail in enumerate(last_list, 1):
        where = f"[{mail['account'].split('@')[0]}] " if many else ""
        lines.append(f"{n}. {where}{mail['name']}: {mail['subject']} ({ago(mail['when'])}) - {short(mail['text'], 140)}")
    lines += problem_lines()
    lines.append("(Tell them who and what in a few words each; they can say 'read the 2nd' or 'open it'.)")
    return "\n".join(lines)

ORDER = {"first": 1, "1st": 1, "latest": 1, "newest": 1, "last": 1, "top": 1, "second": 2, "2nd": 2, "third": 3,
         "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6, "seventh": 7, "eighth": 8}

def pick(which):
    if not last_list:
        return None
    which = str(which).lower().strip()
    number = re.search(r"\d+", which)
    spot = int(number.group()) if number else next((n for w, n in ORDER.items() if w in which), 0)
    if 1 <= spot <= len(last_list):
        return last_list[spot - 1]
    for mail in last_list:  # by sender or subject words ("the one from Penny")
        if which and (which in mail["name"].lower() or which in mail["subject"].lower() or which in mail["from"]):
            return mail
    return None

# ---------- Writing, sending, deleting, marking read ----------
# Safety: sending and deleting only happen when THEIR OWN words say so (state.last_user_text), like the other
# risky tools. Every new mail is saved as a Gmail draft first; "send it" sends the draft (and removes it from
# Drafts, Gmail keeps the sent copy). Delete = move to Trash (Gmail empties Trash after 30 days, so it can be undone).
SEND_WORDS = re.compile(r"(?i)\b(send|sent|shoot|fire it off|go ahead|அனுப்பு)")
DELETE_WORDS = re.compile(r"(?i)\b(delete|trash|bin|remove|get rid|throw)")
DRAFT_MINUTES = 30
pending = {}                 # the last draft: {message, account, password, made, summary}

def their_words():
    return (state.last_user_text or "").lower()

def password_of(address):
    return next((p for a, p in accounts() if a.lower() == address.lower()), "")

def with_box(address, folder, job):
    # Open one account's folder for changes (not read-only), run job(box), close it
    box = connect(address, password_of(address))
    try:
        box.select(folder)
        return job(box)
    finally:
        try:
            box.logout()
        except Exception:
            pass

def find_address(name, address):
    # "Penny" -> the address of the person they last mailed with that name (their own mail, newest first)
    if "@" in name:
        return name.strip()
    first = name.lower().split()[0] if name.split() else ""
    for mail in search_one(address, password_of(address), f"from:{first}", 5, True):
        if first and first in (mail["name"] + " " + mail["from"]).lower():
            return mail["from"]
    return ""

def mail_action(action, which="", to="", subject="", body="", account=""):
    # The brain's tool for changing mail: draft (new or a reply to a listed mail), send, delete, mark_read
    if not ready():
        return NOT_SET_UP
    action = (action or "").lower()
    if action in ("delete", "mark_read"):
        mail = pick(which or "1")
        if not mail:
            return "Which mail? List them first (check_mail)."
        if action == "delete":
            if not DELETE_WORDS.search(their_words()):
                return "Not deleted: they didn't say delete. Ask them first."
            with_box(mail["account"], mail["folder"],
                     lambda box: box.uid("STORE", mail["uid"], "+X-GM-LABELS", "(\\Trash)"))
            last_list.remove(mail)
            return f"Moved '{mail['subject']}' from {mail['name']} to Trash (it can be brought back from Trash for 30 days)."
        with_box(mail["account"], mail["folder"], lambda box: box.uid("STORE", mail["uid"], "+FLAGS", "(\\Seen)"))
        return f"Marked '{mail['subject']}' as read."
    if action == "draft":
        return make_draft(which, to, subject, body, account)
    if action == "send":
        return send_draft(which, to, subject, body, account)
    return "Actions: draft, send, delete, mark_read."

def compose(reply_to, to, subject, body, account):
    # A new mail (to a name or address) or a reply to a listed mail -> (message, sending account), or why not
    if reply_to:
        sender = reply_to["account"]
        address = email.utils.parseaddr(reply_to["reply_to"])[1] or reply_to["from"]
        subject = subject or (reply_to["subject"] if reply_to["subject"].lower().startswith("re:")
                              else "Re: " + reply_to["subject"])
    else:
        every = accounts()
        sender = next((a for a, _ in every if account and a.lower() == account.lower()), None) \
            or (account_for(account) if account else every)[0][0]
        address = find_address(to, sender) if to else ""
        if not address:
            return (f"I don't know {to or 'who'}'s mail address. Ask them for it." if to else "Who is it to?")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, address, subject or "(no subject)"
    message["Date"] = email.utils.formatdate(localtime=True)
    message["Message-ID"] = email.utils.make_msgid(domain="mind.local")
    if reply_to and reply_to["message_id"]:
        message["In-Reply-To"] = reply_to["message_id"]
        message["References"] = (reply_to["references"] + " " + reply_to["message_id"]).strip()
    message.set_content(body.strip())
    return message, sender

def smtp_send(message, sender):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
        smtp.login(sender, password_of(sender))
        smtp.send_message(message)

def make_draft(which, to, subject, body, account):
    if not body.strip():
        return "What should the mail say? Ask them, then write it in their style."
    made = compose(pick(which) if which else None, to, subject, body, account)
    if isinstance(made, str):
        return made
    message, sender = made
    address = message["To"]
    box = connect(sender, password_of(sender))
    try:
        status, answer = box.append(folder_with(box, "\\Drafts"), "(\\Draft)",
                                    imaplib.Time2Internaldate(time.time()), message.as_bytes())
    finally:
        try:
            box.logout()
        except Exception:
            pass
    if status != "OK":
        return f"Gmail didn't save the draft ({answer})."
    pending.clear()
    pending.update({"message": message, "account": sender, "made": time.time()})
    return (f"Draft saved in {sender}'s Gmail Drafts (NOT sent). To: {address}. Subject: {message['Subject']}.\n"
            f"Body: {body.strip()[:600]}\n(Tell them who it's to and the gist, and ask: send it?)")

def folder_with_flag(address, flag):
    box = connect(address, password_of(address))
    try:
        return folder_with(box, flag)
    finally:
        try:
            box.logout()
        except Exception:
            pass

def send_draft(which, to, subject, body, account):
    if not SEND_WORDS.search(their_words()):
        return "Not sent: they didn't say send. Ask 'send it?' first."
    if body.strip() and (to or which):
        made = make_draft(which, to, subject, body, account)  # (a new mail they asked to send right away)
        if not pending or not made.startswith("Draft saved"):
            return made
    if not pending or time.time() - pending["made"] > DRAFT_MINUTES * 60:
        return "No draft waiting to be sent. Write it first (mail_action draft)."
    message, sender = pending["message"], pending["account"]
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
        smtp.login(sender, password_of(sender))
        smtp.send_message(message)
    # (Gmail keeps its own copy in Sent; the draft we saved is removed so it isn't left behind)
    def drop_draft(box):
        status, data = box.uid("search", None, "HEADER", "Message-ID", message["Message-ID"])
        for uid in (data[0].split() if status == "OK" and data and data[0] else []):
            box.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        box.expunge()
    try:
        with_box(sender, folder_with_flag(sender, "\\Drafts"), drop_draft)
    except Exception:
        pass
    pending.clear()
    return f"Sent from {sender} to {message['To']}: '{message['Subject']}'."

# ---------- The Mail panel (HUD and phone app) ----------
# Buttons there are the user's own clear clicks, so they don't need the spoken "send"/"delete" words.
VIEWS = {"important": ("is:unread is:important newer_than:14d", False), "unread": ("is:unread", False),
         "inbox": ("newer_than:30d", False), "spam": ("in:spam", False), "sent": ("in:sent newer_than:30d", True)}
cards = {}                   # id -> the mail behind a card (so a click acts on exactly that mail)

def card(mail):
    key = f"{mail['account']}|{mail['folder']}|{mail['uid']}"
    cards[key] = mail
    if len(cards) > 400:
        for old in list(cards)[:100]:
            cards.pop(old, None)
    return {"id": key, "account": mail["account"], "name": mail["name"], "from": mail["from"],
            "subject": mail["subject"], "when": mail["when"].isoformat() if mail["when"] else "",
            "ago": ago(mail["when"]), "snippet": short(mail["text"], 160), "unread": mail.get("unread", False),
            "link": mail["link"]}

def show_panel():
    # The Mail panel on the HUD ("Mind, open my mail", Ctrl + M); it stays up for an hour
    import showcase
    showcase.put_on_hud({"kind": "mail", "title": "Mail"}, minutes=60)
    return "Opened the Mail panel on the HUD."

def panel_list(view="important", words="", account=""):
    # The list for the panel: a view (important / unread / inbox / spam / sent) or search words, all accounts
    global last_list
    if not ready():
        return {"ready": False, "accounts": [], "mails": [], "problem": NOT_SET_UP.split(" Tell them:")[0]}
    every = accounts()
    chosen = [(a, p) for a, p in every if a == account] or every
    if words.strip():
        query, everywhere = words.strip(), "in:spam" not in words and "in:trash" not in words
    else:
        query, everywhere = VIEWS.get(view, VIEWS["important"])
    found = search(query, 25, everywhere, chosen, peek=12000)  # (12 KB each is enough for a preview)
    last_list = found[:8]  # (so "read the second one" by voice means the same list)
    return {"ready": True, "accounts": [a for a, _ in every], "mails": [card(m) for m in found],
            "problems": problem_lines()}

def panel_open(key):
    # One mail in full (and marked as read, like opening it in Gmail)
    mail = cards.get(key)
    if not mail:
        return {"problem": "That mail is no longer in the list. Refresh."}
    def whole(box):
        status, data = box.uid("fetch", mail["uid"], "(BODY.PEEK[]<0.400000>)")
        box.uid("STORE", mail["uid"], "+FLAGS", "(\\Seen)")
        return data[0][1] if status == "OK" and data and isinstance(data[0], tuple) else b""
    raw = with_box(mail["account"], mail["folder"], whole)
    text = body_text(email.message_from_bytes(raw, policy=email.policy.default)) if raw else mail["text"]
    mail["unread"] = False
    return {**card(mail), "text": text[:20000]}

def panel_act(key, action):
    mail = cards.get(key)
    if not mail:
        return {"problem": "That mail is no longer in the list. Refresh."}
    flag = {"delete": ("+X-GM-LABELS", "(\\Trash)"), "read": ("+FLAGS", "(\\Seen)"),
            "unread": ("-FLAGS", "(\\Seen)")}.get(action)
    if not flag:
        return {"problem": "Unknown action."}
    with_box(mail["account"], mail["folder"], lambda box: box.uid("STORE", mail["uid"], *flag))
    if action in ("read", "unread"):
        mail["unread"] = action == "unread"
    if action == "delete":
        cards.pop(key, None)
    return {"ok": True, "said": {"delete": "Moved to Trash (undo in Gmail for 30 days).", "read": "Marked as read.",
                                 "unread": "Marked as unread."}[action]}

def panel_send(to="", subject="", body="", reply_id="", account="", draft=False):
    # Send (or save as a draft) from the panel: a new mail, or a reply to the open one
    if not body.strip():
        return {"problem": "Write something first."}
    reply_to = cards.get(reply_id) if reply_id else None
    if reply_id and not reply_to:
        return {"problem": "That mail is no longer in the list. Refresh."}
    made = compose(reply_to, to, subject, body, account)
    if isinstance(made, str):
        return {"problem": made}
    message, sender = made
    if draft:
        box = connect(sender, password_of(sender))
        try:
            box.append(folder_with(box, "\\Drafts"), "(\\Draft)", imaplib.Time2Internaldate(time.time()),
                       message.as_bytes())
        finally:
            try:
                box.logout()
            except Exception:
                pass
        return {"ok": True, "said": f"Saved in {sender.split('@')[0]}'s Drafts."}
    smtp_send(message, sender)
    print(f"(Mail sent from the panel: {sender} -> {message['To']})")
    return {"ok": True, "said": f"Sent to {message['To']}."}

# ---------- New important mail: said out loud + phone ----------
seen = {}                    # account -> newest unread important mail number already known

def watch():
    import alerts
    time.sleep(alerts.STARTUP_QUIET + 30)
    failures = 0
    while True:
        try:
            if ready() and not state.muted:
                every = accounts()
                for address, password in every:
                    fresh = search_one(address, password, "is:unread is:important newer_than:1d", 5)
                    newest = max([int(m["uid"]) for m in fresh] or [0])
                    if address in seen:  # (the first look only remembers what's there: no flood at start)
                        where = f" in {address.split('@')[0]}" if len(every) > 1 else ""
                        for mail in reversed([m for m in fresh if int(m["uid"]) > seen[address]]):
                            alerts.say(f"mail_{address}_{mail['uid']}",
                                       f"New mail{where} from {mail['name']}: {short(mail['subject'], 90)}.",
                                       f"{mail['name']}-கிட்ட இருந்து புது மெயில்: {short(mail['subject'], 90)}.", 24)
                    seen[address] = max(seen.get(address, 0), newest)
            failures = 0
        except Exception as e:
            failures += 1
            if failures in (1, 10):
                print("(Gmail check failed:", str(e)[:120] + ")")
        time.sleep(CHECK_SECONDS * min(failures + 1, 5))

def start():
    threading.Thread(target=watch, daemon=True, name="gmail").start()
