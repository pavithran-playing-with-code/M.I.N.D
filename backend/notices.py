# Notifications: when an app (WhatsApp, Gmail in Chrome, Teams...) shows a Windows notification,
# M.I.N.D says it out loud: "Sir, WhatsApp: Jenny says are you free tonight?"
# Read with Windows' own notification listener (pip winrt packages, free). Nothing is saved.
# Not said: when that app is already in front of you, when M.I.N.D is offline (mic off),
# apps in QUIET_APPS. AI chat notifications go to the prompt watcher ("Claude is done").
# profile "notifications": "full" (who + message, default), "sender" (only who), "off".
import asyncio
import re
import threading
import time

import win32gui
import win32process
import psutil

import state
from memory import profile

CHECK_EVERY = 2      # seconds
GROUP_SECONDS = 4    # several messages from one app this close together = one announcement
QUIET_APPS = {"snipping tool", "feedback hub", "settings", "windows security", "microsoft store", "m.i.n.d"}
AI_SITES = re.compile(r"claude\.ai|chatgpt\.com|chat\.openai\.com|gemini\.google\.com", re.I)
APP_PROCESS = {"whatsapp": "whatsapp", "google chrome": "chrome", "microsoft edge": "msedge",
               "microsoft teams": "teams", "outlook": "outlook", "telegram": "telegram"}

def setting():
    value = str(profile.get("notifications", "full")).lower()
    return "off" if value in ("off", "no", "false") else value

def read_all():
    # [(id, app name, [texts])] of the notifications in Windows' notification centre now
    from winrt.windows.ui.notifications.management import UserNotificationListener
    from winrt.windows.ui.notifications import NotificationKinds, KnownNotificationBindings

    async def get():
        found = await UserNotificationListener.current.get_notifications_async(NotificationKinds.TOAST)
        out = []
        for note in found:
            try:
                app = note.app_info.display_info.display_name if note.app_info else ""
                binding = note.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
                texts = [t.text for t in binding.get_text_elements()] if binding else []
            except Exception:
                app, texts = "", []
            out.append((note.id, app, texts))
        return out
    return asyncio.run(get())

def front_app():
    # The app in front (process name without .exe) and its window title
    front = win32gui.GetForegroundWindow()
    try:
        name = psutil.Process(win32process.GetWindowThreadProcessId(front)[1]).name().lower()
    except Exception:
        name = ""
    return name.replace(".exe", ""), win32gui.GetWindowText(front).lower()

def looking_at(app, texts):
    # Is that app already in front? (WhatsApp open = you see the message yourself)
    process, title = front_app()
    want = APP_PROCESS.get(app.lower(), app.lower().split()[0] if app else "")
    if not want or want not in process:
        return False
    if want in ("chrome", "msedge"):
        # a website's notification: only if its tab is the one showing (its site name in the title)
        site = site_name(texts)
        return bool(site) and site.lower() in title
    return True

AI_NAMES = re.compile(r"\b(claude|chatgpt|gemini)\b", re.I)

def is_ai_chat(app, texts):
    # A Claude/ChatGPT/Gemini website notification. Windows often hides the site line ("claude.ai")
    # from us, so for a browser the AI's name in the title or message counts too ("Claude responded")
    if any(AI_SITES.search(t or "") for t in texts):
        return True
    return app.lower() in ("google chrome", "microsoft edge") and any(AI_NAMES.search(t or "") for t in texts)

def site_name(texts):
    # Chrome adds the website as the last line ("web.whatsapp.com") -> "WhatsApp"
    for text in texts[::-1]:
        match = re.search(r"([\w-]+)\.(com|in|org|net|io|ai|app|co)\b", text or "")
        if match:  # "web.whatsapp.com": the part just before ".com"
            return match.group(1).capitalize()
    return ""

def describe(app, notes):
    # One spoken line for one or more notifications from one app
    texts = notes[-1]
    site = site_name(texts) if app.lower() in ("google chrome", "microsoft edge") else ""
    source = site or app or "An app"
    body = [t for t in texts if t and not re.search(r"\.(com|in|org|net|io|ai|app|co)\b", t)]
    who, message = (body[0], " ".join(body[1:])) if len(body) > 1 else ("", " ".join(body))
    words = message.split()
    message = " ".join(words[:15]) + ("..." if len(words) > 15 else "")
    if len(notes) > 1:
        return f"Sir, {len(notes)} new notifications from {source}" + (f", the latest from {who}." if who else ".")
    if setting() == "sender" or not message:
        return f"Sir, new {source} notification" + (f" from {who}." if who else ".")
    return f"Sir, {source}: " + (f"{who} says {message}" if who else message)

seen = set()
waiting = {}  # app -> [texts of each new notification], said after GROUP_SECONDS
first_at = {}

def check(first=False):
    for note_id, app, texts in read_all():
        if note_id in seen:
            continue
        seen.add(note_id)
        if first or setting() == "off" or state.muted:
            continue  # (old ones at start aren't news)
        if app.lower() in QUIET_APPS:
            continue
        if is_ai_chat(app, texts):
            # Claude's website pops this up when a reply finishes in a HIDDEN tab, the one case the
            # prompt watcher can't see: it says "Claude is done" in its own way
            import watcher
            watcher.from_notification(texts)
            continue
        if looking_at(app, texts):
            continue
        waiting.setdefault(app, []).append(texts)
        first_at.setdefault(app, time.time())
    for app in list(waiting):
        if time.time() - first_at[app] >= GROUP_SECONDS:
            line = describe(app, waiting.pop(app))
            first_at.pop(app)
            print("(Notification)", line)
            import watcher
            watcher.chime()
            state.alerts.append(line)

def loop():
    first = True
    while True:
        try:
            check(first)
            first = False
        except Exception as error:
            print("(Notification reader problem:", error, ")")
            time.sleep(60)  # (e.g. Windows said no: try again later, don't flood the log)
        time.sleep(CHECK_EVERY)

def start():
    threading.Thread(target=loop, daemon=True).start()
