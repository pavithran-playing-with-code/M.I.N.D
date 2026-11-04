# "Mind, do what Claude said": reads the chat on screen, makes a short plan (download its file, unzip it,
# put a folder into a project, delete the zip, get the Claude Code prompt ready), says the plan, and only
# does it after they say go. Files are only touched inside the user's own folders; the zip goes to the
# Recycle Bin, and project files that get replaced are backed up first. Claude Code gets the prompt in its
# box, NOT sent: the user presses Enter (M.I.N.D never uses their Claude account).
import difflib
import json
import os
import re
import shutil
import tempfile
import time
import zipfile

import pc
import state

DOWNLOADS = os.path.join(pc.HOME, "Downloads")
BACKUPS = os.path.join(tempfile.gettempdir(), "mind_backups")
PLAN_SECONDS = 300   # a plan waits this long for "go"
WAIT_DOWNLOAD = 30   # seconds for a download to finish
GO_WORDS = re.compile(r"\b(go|yes|yeah|yep|ok|okay|sure|do it|go ahead|proceed|carry on|start)\b|சரி|ஆமா", re.I)

PLAN_RULES = """You read the end of an AI chat (Claude/ChatGPT) on the user's screen. It may tell them to download
an attached file, unzip it, put a folder into a code project, delete the zip, and give a prompt to Claude Code.
Reply with JSON only, from the text only (never invent):
{"file": "the attached file's name exactly as shown (a card like 'X drop' ZIP), or ''",
 "project": "the project folder it goes into (e.g. dfresh), or ''",
 "folders": ["folder names from the zip to put into the project, e.g. docs"],
 "delete_zip": true or false (the text says to delete the zip),
 "prompt": "the exact words they're told to give Claude Code, without quotes, or ''",
 "other": "any step in the text you can't map to the fields above, or ''"}"""

pending = {"plan": None, "at": 0.0, "window": 0}

def chat_plan(hwnd):
    import brain
    text = pc.page_text(hwnd)
    if not text.strip():
        return None, "Couldn't read the chat on screen. Bring the chat window to the front and ask again."
    answer = brain.write(PLAN_RULES, text[-5000:], seconds=20, writers=brain.QUICK_WRITERS)
    found = re.search(r"\{.*\}", answer or "", re.S)
    try:
        plan = json.loads(found.group(0), strict=False) if found else None
    except ValueError:
        plan = None
    if not plan or not (plan.get("file") or plan.get("prompt")):
        return None, "The chat on screen doesn't say to download a file or give Claude Code a prompt."
    plan["folders"] = [f.strip(" /\\") for f in plan.get("folders") or [] if f.strip(" /\\")]
    return plan, ""

def plan_words(plan):
    steps = []
    if plan.get("file"):
        steps.append(f"get the file '{plan['file']}'")
        if plan.get("folders") and plan.get("project"):
            steps.append(f"put {' and '.join(plan['folders'])} into {plan['project']}")
        if plan.get("delete_zip"):
            steps.append("delete the zip (Recycle Bin)")
    if plan.get("prompt") and plan.get("project"):
        steps.append(f"put the prompt in {plan['project']}'s Claude Code box for you to send: \"{plan['prompt']}\"")
    words = "; ".join(steps)
    if plan.get("other"):
        words += f". Can't do this part: {plan['other']}"
    return words

def follow_chat(go=False):
    # The tool. First call: read the chat and make the plan. go=true (after they said go): do it.
    if str(go).lower() in ("true", "yes", "1"):
        if not GO_WORDS.search(getattr(state, "last_user_text", "")):
            return "Not started: they haven't said go. Say the plan and ask 'Go?'"
        if not pending["plan"] or time.time() - pending["at"] > PLAN_SECONDS:
            return "No plan waiting (it's been too long). Read the chat again first (go=false)."
        plan, pending["plan"] = pending["plan"], None
        return do_plan(plan, pending["window"])
    hwnd = pc.target_window()
    if not hwnd:
        return "No chat window in front."
    plan, problem = chat_plan(hwnd)
    if not plan:
        return problem
    pending.update(plan=plan, at=time.time(), window=hwnd)
    return f"PLAN (say it in one or two sentences, then ask 'Go?'; do nothing until they say go): {plan_words(plan)}"

# ---------- Doing it ----------
def do_plan(plan, hwnd):
    done = []
    project = None
    if plan.get("project"):
        project = project_path(plan["project"])
        if not project:
            return f"Stopped before changing anything: no project folder called {plan['project']}."
    if plan.get("file"):
        zip_path = find_download(plan["file"]) or download(plan["file"], hwnd)
        if not zip_path:
            return (f"Stopped before changing anything: couldn't get '{plan['file']}'. Ask them to click "
                    "Download on it in the chat, then say go again.")
        done.append(f"got {os.path.basename(zip_path)}")
        if zip_path.lower().endswith(".zip") and project and plan.get("folders"):
            result = unzip_into(zip_path, project, plan["folders"])
            if result.startswith("Stopped"):
                return result
            done.append(result)
            if plan.get("delete_zip"):
                to_recycle_bin(zip_path)
                done.append("zip moved to the Recycle Bin")
    if plan.get("prompt") and project:
        done.append(prompt_ready(os.path.basename(project), plan["prompt"]))
    return "Done: " + "; ".join(done)

def project_path(name):
    # The project's folder (only inside the user's home)
    if not pc.folders:
        pc.index_folders()
    for path in pc.find_folder(name):
        if inside_home(path):
            return path
    return None

def inside_home(path):
    return os.path.realpath(path).lower().startswith(os.path.realpath(pc.HOME).lower() + os.sep)

def zip_name_score(file_name, wanted):
    a, b = pc.squash(os.path.splitext(file_name)[0]), pc.squash(wanted)
    return 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()

def finished_downloads():
    try:
        names = os.listdir(DOWNLOADS)
    except OSError:
        return {}
    return {n: os.path.getmtime(os.path.join(DOWNLOADS, n)) for n in names
            if not n.lower().endswith((".crdownload", ".tmp", ".part")) and os.path.isfile(os.path.join(DOWNLOADS, n))}

def find_download(wanted, since=None):
    # A file in Downloads with that name (from today), best match first
    best, best_score = None, 0.0
    for name, changed in finished_downloads().items():
        if (since and changed < since) or time.time() - changed > 24 * 3600:
            continue
        score = zip_name_score(name, wanted)
        if score > best_score:
            best, best_score = name, score
    return os.path.join(DOWNLOADS, best) if best and best_score >= 0.6 else None

def download(wanted, hwnd):
    # Click the file card in the chat; if it only opens a preview, press its Download button
    before = set(finished_downloads())
    if not hwnd or not pc.win32gui.IsWindow(hwnd):
        return None  # (the chat window was closed)
    for step in (wanted, "Download"):
        try:
            if not press(hwnd, step):
                continue
        except Exception as e:
            print("Couldn't press", step, "in the chat:", str(e)[:80])
            continue
        end = time.time() + (6 if step == wanted else WAIT_DOWNLOAD)
        while time.time() < end:
            new = [n for n in finished_downloads() if n not in before]
            if new:
                return max((os.path.join(DOWNLOADS, n) for n in new), key=os.path.getmtime)
            time.sleep(0.5)
    return None

def press(hwnd, name):
    # Presses the best-matching button/link by name in that window (the screen-reader way: the window
    # doesn't need to be in front, and no real mouse click lands anywhere else)
    want = pc.squash(name)
    best, best_score = None, 0.0
    for top, left, item_name, what, element in pc.clickables(hwnd, unique=False):
        have = pc.squash(item_name)
        score = 1.0 if have == want else 0.9 if want and want in have else difflib.SequenceMatcher(None, want, have).ratio()
        if score > best_score:
            best, best_score = element, score
    if not best or best_score < 0.6:
        return False
    from comtypes.gen.UIAutomationClient import IUIAutomationInvokePattern
    best.GetCurrentPattern(10000).QueryInterface(IUIAutomationInvokePattern).Invoke()
    return True

def unzip_into(zip_path, project, folders):
    # Puts the named folders from the zip into the project (merging, like dragging them onto it).
    # Checks everything BEFORE changing the project; replaced files are backed up first.
    with tempfile.TemporaryDirectory() as unpacked:
        with zipfile.ZipFile(zip_path) as z:
            for member in z.namelist():  # (a zip can't write outside its own folder)
                if not os.path.realpath(os.path.join(unpacked, member)).startswith(os.path.realpath(unpacked) + os.sep):
                    return f"Stopped before changing anything: the zip has a strange path ({member})."
            z.extractall(unpacked)
        sources = {}
        for folder in folders:
            source = find_inside(unpacked, folder)
            if not source:
                return f"Stopped before changing anything: there's no '{folder}' folder in the zip."
            sources[folder] = source
        backup = os.path.join(BACKUPS, time.strftime("%Y%m%d-%H%M%S"))
        copied = replaced = 0
        for folder, source in sources.items():
            for root, _, files in os.walk(source):
                for name in files:
                    from_file = os.path.join(root, name)
                    relative = os.path.join(folder, os.path.relpath(from_file, source))
                    to_file = os.path.join(project, relative)
                    if os.path.exists(to_file):
                        os.makedirs(os.path.dirname(os.path.join(backup, relative)), exist_ok=True)
                        shutil.copy2(to_file, os.path.join(backup, relative))
                        replaced += 1
                    os.makedirs(os.path.dirname(to_file), exist_ok=True)
                    shutil.copy2(from_file, to_file)
                    copied += 1
    where = os.path.basename(project)
    note = f" ({replaced} replaced; old copies in {backup})" if replaced else ""
    return f"put {', '.join(folders)} into {where}: {copied} files{note}"

def find_inside(unpacked, folder):
    # The folder at the top of the zip, or one level down (zips often have one outer folder)
    for root, dirs, _ in os.walk(unpacked):
        if root[len(unpacked):].count(os.sep) > 1:
            continue
        for d in dirs:
            if d.lower() == folder.lower():
                return os.path.join(root, d)
    return None

def to_recycle_bin(path):
    # Deleted the Windows way, so it can be brought back from the Recycle Bin
    from win32com.shell import shell, shellcon
    shell.SHFileOperation((0, shellcon.FO_DELETE, path, None,
                           shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION | shellcon.FOF_SILENT | shellcon.FOF_NOERRORUI,
                           None, None))

def prompt_ready(project, prompt):
    # The project in VS Code, and the prompt in its Claude Code box (not sent)
    import watcher
    from urllib.parse import quote
    if not watcher.vscode_window(project):
        pc.open_folder(project)
        for _ in range(30):
            if watcher.vscode_window(project):
                break
            time.sleep(0.5)
    result = watcher.to_claude_code(project, prompt)
    if result.startswith("No recent Claude Code session"):
        window = watcher.vscode_window(project)
        if not window:
            return f"couldn't open {project} in VS Code, so the prompt wasn't put in"
        pc.bring_to_front(window)
        time.sleep(0.5)
        os.startfile(f"vscode://anthropic.claude-code/open?prompt={quote(prompt)}")  # a new Claude Code chat
        return f"prompt put in a new Claude Code chat in {project}, NOT sent: they press Enter"
    return result
