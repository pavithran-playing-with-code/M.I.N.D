# Terminal watcher: when a long command finishes in a terminal window (Windows Terminal, PowerShell, cmd,
# also SSH sessions to a server), M.I.N.D says "Sir, the admin-panel build is done." (and tells the phone).
# How: every few seconds it reads the visible text of each terminal window (the screen-reader API, read-only).
# Output lines at the bottom = a command is running; the prompt coming back ("root@...:/x/admin-panel#",
# "PS C:\...>") = it finished. Only commands that ran LONG_RUN seconds or more are announced.
# Not covered: VS Code's own terminal (VS Code hides its text from the screen-reader API), and Windows
# Terminal tabs that aren't the one showing (only the showing tab can be read).
import ctypes
import re
import threading
import time
from ctypes import wintypes
import memory

CHECK_SECONDS = 3
LONG_RUN = 15                # seconds: shorter commands are never announced
CLASSES = ("CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass")   # Windows Terminal, old console

# A prompt line: bash/zsh "user@host:/path#" or "...$", PowerShell "PS C:\path>", cmd "C:\path>".
# Group "where" = the folder part, group "typed" = whatever is written after it.
PROMPT = re.compile(r"^(?:\(\S+\)\s*)?(?:"
                    r"(?P<bash>\S+@[\w.-]+:(?P<where1>[^\s#$]*)\s?[#$])"
                    r"|(?P<ps>PS (?P<where2>[A-Za-z]:\\[^>]*)>)"
                    r"|(?P<cmd>(?P<where3>[A-Za-z]:\\[^>]*)>)"
                    r")(?P<typed>.*)$")
FAILED = re.compile(r"(?i)\b(failed to compile|build failed|compilation failed|npm err!|error:|errors? found|"
                    r"fatal:|exception|traceback|exit(ed)? (with )?code [1-9]|command failed|not found|denied)")
WORKED = re.compile(r"(?i)(compiled successfully|build (folder )?is ready|successfully|built in|done in|"
                    r"\bdone\b|finished|0 errors|✓|ready in)")

watching = {}                # (window, text area index) -> {"since", "command", "where"}

def terminal_windows():
    user32, found = ctypes.windll.user32, []
    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, name, 256)
            if name.value in CLASSES:
                found.append(hwnd)
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(each), 0)
    return found

def screen(hwnd):
    # The visible lines of the window's terminal (Windows Terminal = the showing tab), or None if unreadable.
    # (Windows Terminal has a few text areas whose order changes; the terminal is the one with the most lines.)
    import pc
    from comtypes.gen.UIAutomationClient import IUIAutomationTextPattern
    try:
        uia = pc.automation()
        areas = uia.ElementFromHandle(hwnd).FindAll(4, uia.CreatePropertyCondition(30040, True))  # has text
    except Exception:
        return None  # (the window is closing)
    best = None
    for i in range(areas.Length):
        try:
            pattern = areas.GetElement(i).GetCurrentPattern(10014).QueryInterface(IUIAutomationTextPattern)
            shown = pattern.GetVisibleRanges()
            text = "".join(shown.GetElement(j).GetText(-1) for j in range(shown.Length))
        except Exception:
            continue
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if len(lines) >= 2 and (best is None or len(lines) > len(best)):  # (a one-line area is the tab title)
            best = lines
    return best

def folder_name(match):
    where = (match.group("where1") or match.group("where2") or match.group("where3") or "").rstrip("\\/")
    name = re.split(r"[\\/]", where)[-1] if where not in ("", "~") else "home"
    return name or "home"

def describe(command, where, seconds, output):
    # "Sir, the admin-panel build is done." / "... finished with an error: ..."
    words = command.split()
    tools = ("npm", "pnpm", "yarn", "npx", "bun")
    # (the npm part may come after settings: NODE_OPTIONS="..." npm run build)
    start = next((n for n, w in enumerate(words) if w in tools), None)
    if start is not None and len(words) > start + 1:
        rest = words[start + 1:]
        script = rest[1] if rest[0] == "run" and len(rest) > 1 else rest[0]
        what = f"the {where} {script}"
    else:
        what = f"your command in {where} ({' '.join(words[:4])})"
    took = f"{int(seconds // 60)} min" if seconds >= 90 else f"{int(seconds)} s"
    bad = [line for line in output if FAILED.search(line)]
    if bad and not any(WORKED.search(line) for line in output[-6:]):
        return f"{memory.call_me()}, {what} finished with an error after {took}: {bad[-1].strip()[:120]}"
    return f"{memory.call_me()}, {what} is done ({took})."

def look():
    import alerts
    windows = terminal_windows()
    for key in list(watching):
        if key not in windows:
            watching.pop(key, None)  # window closed
    for key in windows:
        lines = screen(key)
        if not lines:
            continue  # (couldn't read it this time: keep what we know)
        last = PROMPT.match(lines[-1])
        job = watching.get(key)
        if last and not last.group("typed").strip():
            # Back at an empty prompt: a command that was running has finished
            if job and job.get("running"):
                # (its command line is still on screen above, or it scrolled away but the prompt is in the
                # same folder and we saw it running a moment ago; else it's a switch to another tab)
                spot = max((n for n, line in enumerate(lines[:-1]) if PROMPT.match(line)
                            and PROMPT.match(line).group("typed").strip() == job["command"]), default=None)
                same_job = spot is not None or (folder_name(last) == job["where"]
                                                and time.time() - job["seen"] < CHECK_SECONDS * 3)
                seconds = time.time() - job["since"]
                if same_job and seconds >= LONG_RUN and not looking_at(key):
                    line = describe(job["command"], job["where"], seconds, lines[(spot or 0) + 1:-1])
                    alerts.say(f"terminal_{key}_{int(job['since'])}", line, line, 0, urgent=True)
            watching.pop(key, None)
            continue
        if last:
            # A prompt with a command typed after it: still typing, or running with no output yet
            continue
        # Output at the bottom = running. Remember the latest command line above it.
        command_line = next((m for m in (PROMPT.match(line) for line in reversed(lines))
                             if m and m.group("typed").strip()), None)
        if command_line:
            command = command_line.group("typed").strip()
            if job is None or job["command"] != command:
                # (the clock starts when output starts, not while they were typing it)
                job = watching[key] = {"since": time.time(), "command": command,
                                       "where": folder_name(command_line), "running": True}
        if job:
            job["seen"] = time.time()  # (long output may push the command line off screen: keep the job)

def looking_at(hwnd):
    # They're looking at this terminal right now (in front, and they touched the laptop in the last 20 s)
    import alerts
    return ctypes.windll.user32.GetForegroundWindow() == hwnd and alerts.idle_seconds() < 20

def watch():
    import settings
    while True:
        try:
            if settings.on("alert_terminal"):
                look()
        except Exception as e:
            print("(Terminal watcher:", str(e)[:120] + ")")
        time.sleep(CHECK_SECONDS)

def start():
    threading.Thread(target=watch, daemon=True, name="terminals").start()
