# Watches your AI prompts: Claude Code (VS Code / terminal), and Claude / ChatGPT / Gemini in Chrome.
# "Mind, is that prompt done?" -> prompt_status(), and it says by itself "Your Claude Code prompt
# in dfresh is done" when a long one finishes while you're looking at something else.
#  - Claude Code writes each session to ~/.claude/projects/<project>/<session>.jsonl; a finished turn
#    ends with stop_reason "end_turn", a working one with "tool_use" (VS Code hides its screen from
#    the screen-reader API, so the file is the only way to know).
#  - Web chats: the M.I.N.D Chrome extension reports every tab (even hidden ones). Without it, only the
#    tab in front of each Chrome window can be read (a "Stop" button = still writing); Claude's own
#    "reply finished" notification covers a hidden Claude tab (notices.py -> from_notification).
import os
import re
import glob
import json
import time
import threading
import win32gui
from memory import profile
import state

SESSIONS = os.path.expanduser(r"~\.claude\projects")
RECENT_HOURS = 6        # Claude Code sessions touched within this time are watched
TAIL_BYTES = 3_000_000  # only the end of a session file is read (they get big)
STUCK_SECONDS = 75      # one step this long = it may be waiting for your OK
LONG_RUN = 3           # prompts that ran at least this long are announced when you're on another tab
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
    # Labels the page reads out but you don't need: "Claude responded:", file cards "dFresh v2 Code · HTML", "Shared a file,"
    text = re.sub(r"^\s*(Claude|ChatGPT|Gemini) (responded|said)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\S[^.·\n]{0,60}\bCode\s*·\s*\w+\b|\bShared (a|\d+) files?,?", " ", text, flags=re.I)
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
    started = {}  # steps started that have no result yet: id -> how long that kind of step may take
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
            for part in content if isinstance(content, list) else []:
                if part.get("type") == "tool_result":
                    started.pop(part.get("tool_use_id"), None)  # (that step is finished)
            texts = [content] if isinstance(content, str) else [c.get("text", "") for c in content if c.get("type") == "text"]
            if not texts or entry.get("isMeta") or entry.get("isCompactSummary"):
                continue  # tool results and system notes aren't you typing
            if any("[Request interrupted" in t for t in texts):
                info["status"] = "stopped"
                continue
            info.update(status="running", reply="", since=stamp(entry))
            started.clear()
        else:
            words = " ".join(c.get("text", "") for c in content if c.get("type") == "text").strip()
            if words:
                info["reply"] = words
            for part in content if isinstance(content, list) else []:
                if part.get("type") == "tool_use":
                    started[part.get("id")] = step_time(part)
            if entry.get("isApiErrorMessage"):
                info["status"] = "error"
            elif message.get("stop_reason") in ("end_turn", "stop_sequence"):
                info["status"] = "done"
            else:
                info["status"] = "running"
    # Only a step that STARTED and has no result yet can be waiting for your OK. Between steps Claude is just
    # thinking ("Mulling..."), which can take minutes; that used to be called "stuck" (playroom, 3 Nov).
    info["patience"] = max(started.values()) if started else None
    return info

LONG_TOOLS = {"Agent", "Task", "Workflow"}  # helpers that run for many minutes by design

SHELL_TOOLS = {"Bash", "PowerShell"}
SHELL_LIMIT = 120  # a command with no time limit of its own may run this long

def step_time(part):
    # How long this one step may run before "it might need your OK" (a long test isn't a question)
    ask = part.get("input") or {}
    if part.get("name") in LONG_TOOLS:
        return 15 * 60
    if part.get("name") in SHELL_TOOLS and not ask.get("run_in_background"):
        limit = ask["timeout"] / 1000 if isinstance(ask.get("timeout"), (int, float)) else SHELL_LIMIT
        return limit + 15
    return STUCK_SECONDS

INNER_FOLDERS = {"backend", "frontend", "src", "app", "server", "client", "api", "web"}

def project_name(folder):
    # "...\M.I.N.D\backend" -> "M.I.N.D" (Claude Code often runs in a project's inner folder)
    parts = [p for p in re.split(r"[\\/]", folder) if p]
    for depth in range(len(parts), 1, -1):  # the project's main folder (has .git): "...\M.I.N.D\extension" -> M.I.N.D
        if os.path.isdir(os.path.join(os.sep.join(parts[:depth]) + os.sep, ".git")):
            return parts[depth - 1]
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
        if info["status"] == "running" and info.get("patience") and time.time() - modified > info["patience"]:
            info["status"] = "waiting"  # one step for a long time: likely asking for your OK
        if info["status"]:
            found.append(info)
    return sorted(found, key=lambda s: -s["modified"])

# ---------- Claude / ChatGPT / Gemini in Chrome ----------
def page_address(hwnd):
    import pc
    uia = pc.automation()  # first: it rebuilds the helper below if a Windows update broke it
    from comtypes.gen.UIAutomationClient import IUIAutomationValuePattern
    bar = uia.ElementFromHandle(hwnd).FindFirst(4, uia.CreatePropertyCondition(30003, 50004))  # 50004 = edit box
    try:
        return bar.GetCurrentPattern(10002).QueryInterface(IUIAutomationValuePattern).CurrentValue  # 10002 = value
    except Exception:
        return ""

def web_chats(with_reply=False):
    # Chats from the M.I.N.D Chrome extension (every tab, even in the background), plus
    # chats in front of Chrome windows read with the screen-reader API (profiles without the extension)
    import pc
    import browser
    chats = [{"key": c["key"], "where": c.get("site", "Claude"), "hwnd": None, "ext": True,
              "title": c.get("title", ""), "project": "", "active": c.get("active"),
              "status": "running" if c.get("running") else "done",
              "prompt": c.get("prompt", ""), "reply": c.get("reply", ""),
              "question": c.get("question", "")} for c in browser.chats()]
    known = {c["title"] for c in chats}
    for hwnd in pc.chrome_windows():
        title = win32gui.GetWindowText(hwnd)
        if not title or title in pc.MIND_WINDOWS:
            continue
        if re.sub(r"\s*-\s*(Claude|ChatGPT|Gemini|Google Chrome).*$", "", title) in known:
            continue  # the extension already reports this one
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
    want = re.sub(r"\b(cloud|clawed|clod|claud)\b", "claude", where.lower().strip())  # how Whisper hears "Claude"
    jobs = []
    code = any(w in want for w in ("code", "vs", "terminal"))
    site = any(w in want for w in ("claude", "chat", "gpt", "gemini"))
    if not want or code or not site:  # "Claude" alone = the website, "Claude Code"/"VS Code" = the editor
        jobs += claude_code_sessions()[:4]
    if not want or not code:
        jobs += web_chats(with_reply=True)
    if want:
        words = [w for w in want.replace("vs code", "claude code").split() if not (code and w == "claude")]
        named = [j for j in jobs if any(w in (j["where"] + " " + j.get("project", "") + " " + j.get("title", "")).lower()
                                        for w in words)]
        if not named:  # a misheard name: watch everything rather than nothing
            jobs = claude_code_sessions()[:4] + web_chats(with_reply=True)
        else:
            jobs = named
    if not jobs:
        return ("No AI prompts found: no Claude Code session in the last few hours, and no Claude/ChatGPT/Gemini "
                "chat found (a chat in a hidden tab is only seen in Chrome profiles with the M.I.N.D extension).")
    # Finished long ago = old news (it once mixed "done 38 min ago" into a running chat's answer)
    fresh = [j for j in jobs if j["status"] in ("running", "waiting")
             or time.time() - j.get("modified", time.time()) < 15 * 60]
    jobs = fresh or jobs[:1]
    jobs.sort(key=lambda j: j["status"] not in ("running", "waiting"))  # running ones first
    busy = [j for j in jobs if j["status"] in ("running", "waiting")]
    for job in busy:
        asked.add(job["key"])  # you asked: say it when it finishes, even if you're looking at it
    verdict = ("STILL RUNNING (not done yet). I'll say it out loud when it finishes." if busy
               else "DONE (nothing is running).")
    return verdict + "\n" + "\n".join(describe(j) for j in jobs[:5])

# ---------- Saying it by itself ----------
seen = {}      # job key -> (status, when it started running)
asked = set()  # prompts you asked about while running: always told when they finish
announced = []  # the last announcements (newest last): which chat, so the live brain can go back to it

def recent_announcements(hours=2):
    # [{at, line, where, title, project}] said in the last few hours, newest last (at most 5)
    since = time.time() - hours * 3600
    return [a for a in announced if a["at"] >= since][-5:]

def looking_at(job):
    # True if that chat/project is the window in front right now (then you can see it yourself)
    front = win32gui.GetForegroundWindow()
    if job.get("hwnd"):
        return front == job["hwnd"]
    if job.get("ext"):  # a chat tab: in front of its window, and that window in front
        return bool(job.get("active")) and bool(job["title"]) and job["title"].lower() in win32gui.GetWindowText(front).lower()
    title = win32gui.GetWindowText(front).lower()
    return bool(job.get("project")) and job["project"].lower() in title and "visual studio code" in title

def away_minutes():
    import alerts
    return alerts.idle_seconds() / 60

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
        if first or old_status not in ("running", "waiting") or status == old_status or status == "running":
            continue
        if job["key"] in asked:
            asked.discard(job["key"])
        elif time.time() - started < LONG_RUN or looking_at(job):
            continue
        tell(job)

def tell(job):
    name = "Claude Code" + (f" in {job['project']}" if job.get("project") else "") if job["where"] == "Claude Code" else job["where"]
    if job["status"] == "waiting":
        line = f"Sir, {name} has been on one step for a while. It might need your OK."
    elif job["status"] == "done":
        if job.get("hwnd"):
            job["reply"] = last_answer_text(job["hwnd"])
        reply = (job.get("reply") or "").strip()
        question = (job.get("question") or "").strip()
        asked_about = question if question and question != "a question" else first_words(reply, 12) if reply.endswith(("?", ":")) else ""
        if asked_about:
            # it stopped to ask you something (a question box, or "...before I search:")
            line = f"Sir, {name} is asking you something: {asked_about}"
        else:
            line = f"Sir, {name} is done."
            if reply:
                line += " It says: " + first_words(reply, 10)
    else:
        return  # stopped by you, or an error (it shows on screen)
    print("(Prompt watcher)", line)
    chime()  # a little sound first, so it doesn't get missed
    state.alerts.append(line)
    # Remembered for the live brain: "continue in that chat you just told me about" (it opened a new
    # Claude chat instead, because it never heard this announcement)
    announced.append({"at": time.time(), "line": line, "where": job["where"],
                      "title": job.get("title", ""), "project": job.get("project", "")})
    del announced[:-20]  # (only the last few matter)
    if away_minutes() > 3:  # not at the laptop: tell the phone too
        import telegram_bot
        telegram_bot.notify("🤖 " + line)

def from_notification(texts):
    # A Chrome notification from claude.ai/chatgpt.com/gemini (title, message, site): the reply
    # finished in a tab you can't see (another tab is showing), so the screen reading missed it
    site = next((t for t in texts[::-1] if t and re.search(r"claude\.ai|chatgpt\.com|openai\.com|gemini\.google", t, re.I)), "")
    named = (site or " ".join(texts)).lower()  # (the site line is often hidden: then the AI's name in the text)
    where = next((name for host, name in CHAT_SITES.items() if host.split(".")[0] in named
                  or name.lower() in named), "Claude")
    body = [t for t in texts if t and t != site]
    title = body[0] if body and body[0].lower() != where.lower() else ""
    reply = " ".join(body[1:]) if len(body) > 1 else ""
    if re.fullmatch(r"\s*(\w+ )?(responded|replied|is done|finished)\.?\s*", reply or "x", re.I):
        reply = ""  # just "Claude responded": nothing worth reading out
    # Already said by the screen reading in the last 20 s (same chat): don't say it twice
    if any(a["where"] == where and time.time() - a["at"] < 20 for a in announced):
        return
    tell({"where": where, "status": "done", "title": title, "reply": reply})

def chime():
    try:
        import winsound
        winsound.PlaySound("SystemNotification", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass

def check_extension():
    # Says once (every 6 h at most) if the M.I.N.D extension got turned off in a Chrome profile
    import browser
    for folder, name, on in browser.installed():
        if not on and time.time() - warned.get(folder, 0) > 6 * 3600:
            warned[folder] = time.time()
            line = f"Sir, the Mind extension is turned off in your {name} Chrome. Want me to open the extensions page?"
            print("(Prompt watcher)", line)
            state.alerts.append(line)

warned = {}  # profile folder -> when we last said its extension is off

def loop():
    first = True
    rounds = 0
    while True:
        rounds += 1
        if rounds % 75 == 1:  # about every 5 minutes
            try:
                check_extension()
            except Exception as error:
                print("(Extension check problem:", error, ")")
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

# ---------- Handing text to Claude Code ("Mind, put what Claude said into dfresh's Claude Code") ----------
# Claude Code's own VS Code link (vscode://anthropic.claude-code/open?session=..&prompt=..) opens that session with
# the text already in its box. It is NOT sent: you read it and press Enter yourself. Nothing is typed into your code.
PASTE_INTRO = re.compile(r"\b(paste|copy|send|give)\b.*(claude code|this|below|message|prompt)|:\s*$", re.I)
AFTER_BLOCK = ("when it", "when you", "once it", "once you", "after it", "after that", "then send", "let me know")
LINK_LIMIT = 1900  # longer links may not open: then it goes on the clipboard instead

def block_to_paste(page):
    # From a chat page's text: the lines after the last "Paste this to Claude Code ...:" line,
    # up to "When it reports..." (the words meant for you, not for Claude Code)
    lines = [l.strip() for l in page.splitlines() if l.strip()]
    starts = [i for i, l in enumerate(lines) if PASTE_INTRO.search(l) and re.search(r"\bpaste\b", l, re.I)]
    if not starts:
        return ""
    picked = []
    for line in lines[starts[-1] + 1:]:
        if line.lower().startswith(AFTER_BLOCK) or line.lower() in ("copy", "retry", "edit", "reply"):
            break
        picked.append(line)
    return "\n".join(picked).strip()

def session_for(project):
    # The newest Claude Code session of that project: (session id, its title, the project's real name)
    import difflib
    sessions = [s for s in claude_code_sessions() if s.get("project")]
    names = {s["project"].lower(): s["project"] for s in sessions}
    close = difflib.get_close_matches(project.lower().replace(" ", ""), names, n=1, cutoff=0.6)
    wanted = close[0] if close else next((n for n in names if project.lower() in n), "")
    for s in sessions:
        if s["project"].lower() == wanted:
            return os.path.basename(s["key"]).removesuffix(".jsonl"), s.get("title", ""), s["project"]
    return None

def vscode_window(project):
    # That project's VS Code window ("main.py - dfresh - Visual Studio Code")
    found = []
    def check(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if win32gui.IsWindowVisible(hwnd) and title.endswith("Visual Studio Code") and project.lower() in title.lower():
            found.append(hwnd)
    win32gui.EnumWindows(check, None)
    return found[0] if found else 0

def to_claude_code(project, text="", from_chat=False):
    # The send_to_claude_code tool
    import pc
    from urllib.parse import quote
    if from_chat or not text.strip():
        hwnd = pc.target_window()
        text = block_to_paste(pc.page_text(hwnd)) if hwnd else ""
        if not text:
            return "Couldn't find a 'paste this to Claude Code' part in the chat on screen. Ask them which text."
    found = session_for(project)
    if not found:
        return f"No recent Claude Code session for '{project}' (only the last {RECENT_HOURS} hours count)."
    session, title, name = found
    window = vscode_window(name)
    if not window:
        return f"{name} isn't open in VS Code. Open it first (open_folder), then try again."
    pc.bring_to_front(window)  # (VS Code opens the link in the window used last)
    time.sleep(0.5)
    link = f"vscode://anthropic.claude-code/open?session={session}&prompt={quote(text)}"
    if len(link) > LINK_LIMIT:
        pc.set_clipboard(text)
        os.startfile(f"vscode://anthropic.claude-code/open?session={session}")
        return (f"Opened {name}'s Claude Code ('{title}'). The text was too long for its box, so it's copied: "
                "tell them to press Ctrl+V there, check it, then Enter. Not sent.")
    os.startfile(link)
    return (f"Put it in {name}'s Claude Code box ('{title}'), NOT sent: they check it and press Enter. "
            f"It starts: {first_words(text, 12)}")
