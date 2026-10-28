# Watches your AI prompts: Claude Code (VS Code / terminal), and Claude / ChatGPT / Gemini in Chrome.
# "Mind, is that prompt done?" -> prompt_status(), and it says by itself "Your Claude Code prompt
# in dfresh is done" when a long one finishes while you're looking at something else.
#  - Claude Code writes each session to ~/.claude/projects/<project>/<session>.jsonl; a finished turn
#    ends with stop_reason "end_turn", a working one with "tool_use" (VS Code hides its screen from
#    the screen-reader API, so the file is the only way to know).
#  - Web chats show a "Stop" button while they're writing. Only the tab in front of each Chrome window
#    can be read, so keep the chat in its own window.
import os
import re
import glob
import json
import time
import threading
import win32api
import win32gui
from memory import profile
import state

SESSIONS = os.path.expanduser(r"~\.claude\projects")
RECENT_HOURS = 6        # Claude Code sessions touched within this time are watched
TAIL_BYTES = 3_000_000  # only the end of a session file is read (they get big)
STUCK_SECONDS = 75      # one step this long = it may be waiting for your OK
LONG_RUN = 20           # only prompts that ran at least this long are announced
CHAT_SITES = {"claude.ai": "Claude", "chatgpt.com": "ChatGPT", "chat.openai.com": "ChatGPT",
              "gemini.google.com": "Gemini"}
STOP_BUTTON = re.compile(r"^stop( (response|responding|streaming|generating))?$", re.I)
ANSWER_BUTTONS = re.compile(r"^(copy|copy response|retry|good response|bad response|read aloud|regenerate|"
                            r"more actions|share|edit)$", re.I)
PAGE_JUNK = re.compile(r"can make mistakes|double-check|messages left|reset in|add files|"
                       r"voice mode|session:|notifications|scroll to bottom|finished the response", re.I)

# ---------- Claude Code ----------
cache = {}  # file -> (modified time, parsed status), so unchanged files aren't read again

def first_words(text, words=30):
    # The start of a reply, without markdown, for speaking
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [file.py](path) -> file.py
    text = re.sub(r"[*_`#>|]", "", text)
    text = " ".join(text.split())
    cut = text.split()
    return " ".join(cut[:words]) + ("..." if len(cut) > words else "")

def read_session(path):
    # {"title", "project", "status": running/done/stopped/error, "prompt", "reply", "since"}
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        lines = f.read().decode("utf-8", "ignore").splitlines()
    info = {"title": "", "project": "", "status": "", "prompt": "", "reply": "", "since": 0.0}
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:
            continue  # (the first line is usually cut in half)
        kind = entry.get("type")
        if kind == "ai-title":
            info["title"] = entry.get("aiTitle", "")
        elif kind == "last-prompt":
            info["prompt"] = entry.get("lastPrompt", "")
        if entry.get("isSidechain") or kind not in ("user", "assistant"):
            continue
        info["project"] = project_name(entry.get("cwd", "")) or info["project"]
        message = entry.get("message", {})
        content = message.get("content", [])
        if kind == "user":
            texts = [content] if isinstance(content, str) else [c.get("text", "") for c in content if c.get("type") == "text"]
            if not texts or entry.get("isMeta") or entry.get("isCompactSummary"):
                continue  # tool results and system notes aren't you typing
            if any("[Request interrupted" in t for t in texts):
                info["status"] = "stopped"
                continue
            info.update(status="running", reply="", since=stamp(entry))
        else:
            words = " ".join(c.get("text", "") for c in content if c.get("type") == "text").strip()
            if words:
                info["reply"] = words
            if entry.get("isApiErrorMessage"):
                info["status"] = "error"
            elif message.get("stop_reason") in ("end_turn", "stop_sequence"):
                info["status"] = "done"
            else:
                info["status"] = "running"
    return info

INNER_FOLDERS = {"backend", "frontend", "src", "app", "server", "client", "api", "web"}

def project_name(folder):
    # "...\M.I.N.D\backend" -> "M.I.N.D" (Claude Code often runs in a project's inner folder)
    parts = [p for p in re.split(r"[\\/]", folder) if p]
    while len(parts) > 1 and parts[-1].lower() in INNER_FOLDERS:
        parts.pop()
    return parts[-1] if parts else ""

def stamp(entry):
    # The entry's time as seconds (Claude Code writes "2026-10-28T09:15:02.123Z")
    try:
        import calendar
        return min(time.time(), calendar.timegm(time.strptime(entry["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")))
    except Exception:
        return time.time()

def claude_code_sessions():
    # Every Claude Code session used recently, newest first
    found = []
    for path in glob.glob(os.path.join(SESSIONS, "*", "*.jsonl")):
        try:
            modified = os.path.getmtime(path)
        except OSError:
            continue
        if time.time() - modified > RECENT_HOURS * 3600:
            continue
        if path not in cache or cache[path][0] != modified:
            try:
                cache[path] = (modified, read_session(path))
            except Exception:
                continue
        info = dict(cache[path][1], key=path, where="Claude Code", modified=modified)
        if info["status"] == "running" and time.time() - modified > STUCK_SECONDS:
            info["status"] = "waiting"  # one step for a long time: likely asking for your OK
        if info["status"]:
            found.append(info)
    return sorted(found, key=lambda s: -s["modified"])

# ---------- Claude / ChatGPT / Gemini in Chrome ----------
def page_address(hwnd):
    import pc
    from comtypes.gen.UIAutomationClient import IUIAutomationValuePattern
    uia = pc.automation()
    bar = uia.ElementFromHandle(hwnd).FindFirst(4, uia.CreatePropertyCondition(30003, 50004))  # 50004 = edit box
    try:
        return bar.GetCurrentPattern(10002).QueryInterface(IUIAutomationValuePattern).CurrentValue  # 10002 = value
    except Exception:
        return ""

def web_chats(with_reply=False):
    # Chat pages open in front of a Chrome window: running (Stop button showing) or done
    import pc
    chats = []
    for hwnd in pc.chrome_windows():
        title = win32gui.GetWindowText(hwnd)
        if not title or title in pc.MIND_WINDOWS:
            continue
        address = page_address(hwnd).lower()
        site = next((name for host, name in CHAT_SITES.items() if host in address), "")
        if not site:
            continue
        try:
            buttons = [name for *_, name, kind, _ in pc.clickables(hwnd, unique=False)]
        except Exception:
            continue
        running = any(STOP_BUTTON.match(name) for name in buttons)
        chat = {"key": f"web:{hwnd}:{address.split('?')[0]}", "where": site, "hwnd": hwnd,
                "title": re.sub(r"\s*-\s*(Claude|ChatGPT|Gemini|Google Chrome).*$", "", title),
                "project": "", "status": "running" if running else "done", "prompt": "", "reply": ""}
        if with_reply and not running:
            chat["reply"] = last_answer_text(hwnd)
        chats.append(chat)
    return chats

def last_answer_text(hwnd):
    # The end of the latest answer: the last long line above the latest answer's buttons
    # (Copy / Retry / Good response...). Below those is the box you type in, which isn't the answer.
    import pc
    try:
        lines = [" ".join(l.split()) for l in pc.page_text(hwnd).splitlines()]
    except Exception:
        return ""
    buttons = [i for i, l in enumerate(lines) if ANSWER_BUTTONS.match(l)]
    if buttons:
        end = buttons[-1]
        while end - 1 in buttons or (end > 0 and not lines[end - 1]):  # go to the first button of that row
            end -= 1
        lines = lines[:end]
    lines = [l for l in lines if len(l) >= 40 and not PAGE_JUNK.search(l)]
    return lines[-1] if lines else ""

# ---------- The prompt_status tool ----------
def ago(seconds):
    minutes = int(seconds // 60)
    return "just now" if minutes < 1 else f"{minutes} min ago" if minutes < 60 else f"{minutes // 60} h ago"

def describe(job):
    name = job["where"] + (f" in {job['project']}" if job.get("project") else "")
    name += f" ('{job['title'][:50]}')" if job.get("title") else ""
    line = f"{name}: "
    status = job["status"]
    if status == "running":
        line += "still running" + (f", for {ago(time.time() - job['since']).replace(' ago', '')}" if job.get("since") else "")
    elif status == "waiting":
        line += f"stuck on one step for {ago(time.time() - job['modified']).replace(' ago', '')}, probably waiting for their OK"
    elif status == "done":
        line += "done" + (f" {ago(time.time() - job['modified'])}" if job.get("modified") else "")
    elif status == "stopped":
        line += "they stopped it"
    else:
        line += "it hit an error"
    if job.get("prompt"):
        line += f". Prompt: {first_words(job['prompt'], 15)}"
    if job.get("reply") and status != "running":
        line += f". Reply starts: {first_words(job['reply'])}"
    return line

def prompt_status(where=""):
    # where: "", "claude code"/"vs code", "claude", "chatgpt", "gemini", or a project/chat name
    want = where.lower().strip()
    jobs = []
    if not want or any(w in want for w in ("code", "vs", "terminal")) or "chat" not in want:
        jobs += claude_code_sessions()[:4]
    if not want or not any(w in want for w in ("code", "vs", "terminal")):
        jobs += web_chats(with_reply=True)
    if want:
        named = [j for j in jobs if any(w in (j["where"] + " " + j.get("project", "") + " " + j.get("title", "")).lower()
                                        for w in want.replace("vs code", "claude code").split())]
        if not named:
            others = "; ".join(describe(j) for j in jobs[:3])
            return f"Nothing matching '{where}' (a chat in a background tab can't be seen)." + (f" Others: {others}" if others else "")
        jobs = named
    if not jobs:
        return ("No AI prompts found: no Claude Code session in the last few hours, and no Claude/ChatGPT/Gemini "
                "chat in front of a Chrome window (a chat in a background tab can't be seen).")
    jobs.sort(key=lambda j: j["status"] not in ("running", "waiting"))  # running ones first
    return "\n".join(describe(j) for j in jobs[:5])

# ---------- Saying it by itself ----------
seen = {}  # job key -> (status, when it started running)

def looking_at(job):
    # True if that chat/project is the window in front right now (then you can see it yourself)
    front = win32gui.GetForegroundWindow()
    if job.get("hwnd"):
        return front == job["hwnd"]
    title = win32gui.GetWindowText(front).lower()
    return bool(job.get("project")) and job["project"].lower() in title and "visual studio code" in title

def away_minutes():
    return (win32api.GetTickCount() - win32api.GetLastInputInfo()) / 60000

def check(first=False):
    jobs = claude_code_sessions()[:6]
    try:
        jobs += web_chats()
    except Exception:
        pass
    for job in jobs:
        key, status = job["key"], job["status"]
        old_status, started = seen.get(key, ("", 0.0))
        if status == "running" and old_status != "running":
            started = job.get("since") or time.time()
        seen[key] = (status, started)
        if first or old_status not in ("running", "waiting") or status == old_status:
            continue
        if status == "running" or time.time() - started < LONG_RUN or looking_at(job):
            continue
        tell(job)

def tell(job):
    name = "Claude Code" + (f" in {job['project']}" if job.get("project") else "") if job["where"] == "Claude Code" else job["where"]
    if job["status"] == "waiting":
        line = f"{name} has been on one step for a while. It might need your OK."
    elif job["status"] == "done":
        line = f"{name} finished your prompt."
        if job["where"] != "Claude Code":
            job["reply"] = last_answer_text(job["hwnd"])
        if job.get("reply"):
            line += " It says: " + first_words(job["reply"], 14)
    else:
        return  # stopped by you, or an error (it shows on screen)
    print("(Prompt watcher)", line)
    state.alerts.append(line)
    if away_minutes() > 3:  # not at the laptop: tell the phone too
        import telegram_bot
        telegram_bot.notify("🤖 " + line)

def loop():
    first = True
    while True:
        # "watch_prompts": "off" in profile.json (or "Mind, stop telling me about prompts") turns it off
        if str(profile.get("watch_prompts", "on")).lower() not in ("off", "no", "false"):
            try:
                check(first)
                first = False
            except Exception as error:
                print("(Prompt watcher problem:", error, ")")
        time.sleep(4)

def start():
    threading.Thread(target=loop, daemon=True).start()
