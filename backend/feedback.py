# "Mind, send feedback: the reactor is too big" / "Mind, report a bug: ..."
# Opens a ready-filled GitHub issue on the public M.I.N.D repo (they press "Create", needs a free GitHub
# account) and copies the same text, so they can also just paste it to VVP on WhatsApp.
# Only their words + version + Windows + recent ERROR lines go in: never conversations, keys or names.
import os
import platform
import re
import urllib.parse
import updater

LOG = os.path.join(updater.BACKEND, "logs", "mind_log.txt")
ERROR = re.compile(r"Traceback|Error|Exception|failed|crash", re.I)
PRIVATE = re.compile(r"You( \(typed\))?:|M\.I\.N\.D( \(live\))?:|Phone|@|key|password|token", re.I)

def recent_errors(lines=15):
    # The last error lines from today's log (nothing anyone said: those lines are skipped)
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-3000:]
    except OSError:
        return []
    found = [line.rstrip()[:200] for line in tail if ERROR.search(line) and not PRIVATE.search(line)]
    return found[-lines:]

def report(text, kind="idea"):
    version = updater.local().get("version", "dev")
    errors = recent_errors() if kind == "bug" else []
    body = f"{text}\n\n---\nM.I.N.D version: {version}\nWindows: {platform.release()} ({platform.version()})"
    if errors:
        body += "\n\nRecent errors:\n```\n" + "\n".join(errors) + "\n```"
    return body

def send_feedback(text, kind="idea"):
    # The tool
    text = (text or "").strip()
    if len(text) < 3:
        return "Not sent: ask them what they'd like to tell (the bug or idea, in their own words)."
    kind = "bug" if kind == "bug" else "idea"
    body = report(text, kind)
    title = ("Bug: " if kind == "bug" else "Idea: ") + text[:70]
    url = (f"https://github.com/{updater.REPO}/issues/new?"
           + urllib.parse.urlencode({"title": title, "body": body[:6000]}))
    import pc
    pc.open_in_browser(url)
    try:
        pc.set_clipboard(f"{title}\n\n{body}")
    except Exception:
        pass
    print(f"(Feedback opened: {title})")
    return ("Opened a ready-filled report on GitHub (they press 'Create'; GitHub asks them to sign in first if needed) "
            "and copied it, so they can also paste it to VVP on WhatsApp. Say that in one short line.")
