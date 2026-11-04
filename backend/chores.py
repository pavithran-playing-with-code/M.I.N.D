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

# ---------- Claude Code asks questions -> your Claude chat answers them ----------
# "Mind, ask Claude about these questions": the questions Claude Code is waiting on are read EXACTLY from its
# session file (no screenshots needed), pasted into your Claude/ChatGPT chat for that project, and the reply
# is turned into one pick per question. Picking inside Claude Code's question box isn't done yet (VS Code's
# panel can't be read or pressed by the screen-reader API): M.I.N.D says the picks and copies any own answer.
REPLY_WAIT = 240  # seconds for the chat to answer
MARKER = "Claude Code is asking me these questions"

MAP_RULES = """Questions (with lettered options) and an AI's reply that answers them are below. For each question,
give the option the reply picked, or its own answer if it picked none / changed it. JSON only:
{"answers": [{"question": 1, "option": "the option's label exactly, or ''", "own": "anything the reply adds beyond the
plain option, written as a note for Claude Code (e.g. 'Expenses is phase 23, not 17'), or its own answer if it picked
no option; else ''", "why": "the reply's reason in a few words"}]}"""

asked = {"questions": None, "project": "", "chat": None, "at": 0.0}

def session_questions(path):
    # The questions of the last AskUserQuestion step that has no answer yet in this session file
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - 3_000_000))
        lines = f.read().decode("utf-8", "ignore").splitlines()
    open_asks, answered = {}, set()
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_use" and part.get("name") == "AskUserQuestion":
                open_asks[part.get("id")] = (part.get("input") or {}).get("questions") or []
            elif part.get("type") == "tool_result":
                answered.add(part.get("tool_use_id"))
    waiting = [qs for key, qs in open_asks.items() if key not in answered]
    return waiting[-1] if waiting else []

def open_questions(project=""):
    # (project, questions) for the newest Claude Code session with questions waiting
    import watcher
    for s in watcher.claude_code_sessions():
        if project and pc.squash(project) not in pc.squash(s.get("project", "")):
            continue
        questions = session_questions(s["key"])
        if questions:
            return s.get("project", ""), questions
    return "", []

def questions_text(project, questions):
    lines = [f"{MARKER} in {project}. Which option should I pick for each? Answer each by its number "
             "(an option, or your own short answer if none fits), with one line why."]
    for n, q in enumerate(questions, 1):
        lines.append(f"\n{n}. {q.get('header', '')}: {q.get('question', '')}")
        for letter, option in zip("abcdefgh", q.get("options") or []):
            lines.append(f"   {letter}) {option.get('label', '')}: {option.get('description', '')}")
    return "\n".join(lines)

def find_chat(chat, project):
    # (window, tab, name) of the AI chat tab to ask: the named one, else one about the project
    tabs = [t for t in pc.browser_tabs() if pc.AI_CHAT_TITLE.search(t[2])]
    for want in (chat, project):
        flat = pc.squash(want or "")
        hits = [t for t in tabs if flat and flat in pc.squash(t[2])]
        if hits:
            return hits[0]
    return None

def chat_box(hwnd):
    # The chat's own prompt box (the last one, like "Write your prompt to Claude")
    uia = pc.automation()
    boxes = []
    for type_id in pc.TEXT_BOXES:
        found = uia.ElementFromHandle(hwnd).FindAll(4, uia.CreatePropertyCondition(30003, type_id))
        for i in range(found.Length):
            element = found.GetElement(i)
            try:
                if element.CurrentIsKeyboardFocusable and pc.CHAT_BOX.search(element.CurrentName or ""):
                    boxes.append(element)
            except Exception:
                continue
    real = [b for b in boxes if b.CurrentControlType != 50030]  # (the whole page is a "document": not the box)
    return (real or boxes or [None])[-1]

def still_answering(hwnd):
    return any(re.match(r"stop( response| streaming| generating)?$", name.strip(), re.I)
               for _, _, name, _, _ in pc.clickables(hwnd, unique=False))

def ask_chat(hwnd, text):
    # Pastes the text into the chat, sends it, and waits for the full reply. None = no message box
    box = chat_box(hwnd)
    if not box:
        return None
    before = pc.clipboard_text()
    pc.set_clipboard(text)
    if pc.win32gui.GetForegroundWindow() != hwnd:
        pc.bring_to_front(hwnd)
        time.sleep(0.4)
    if pc.win32gui.GetForegroundWindow() != hwnd:
        pc.set_clipboard(before or "")
        return ""  # (never press keys into whatever else is in front)
    box.SetFocus()
    time.sleep(0.2)
    pc.tap_keys(pc.CTRL, pc.KEY_V)  # (pasted: typing new lines would send it half done)
    time.sleep(0.4)
    pc.tap_keys(pc.ENTER)
    time.sleep(0.5)
    if before:
        pc.set_clipboard(before)  # their clipboard back
    end, last, still = time.time() + REPLY_WAIT, "", 0
    while time.time() < end:
        time.sleep(2)
        page = pc.page_text(hwnd)
        reply = page[page.rfind(MARKER):] if MARKER in page else ""
        reply = reply.split("with one line why.", 1)[-1]
        for q in asked["questions"] or []:  # (our own pasted question text isn't the answer)
            for line in [q.get("question", "")] + [o.get("description", "") for o in q.get("options") or []]:
                if len(line) > 30:
                    reply = reply.replace(line, "")
        if reply == last and len(reply.strip()) > 40 and not still_answering(hwnd):
            still += 1
            if still >= 2:
                return reply.strip()
        else:
            still = 0
        last = reply
    return last.strip()

def answer_questions(project="", chat="", go=False):
    # The tool. go=false: read Claude Code's waiting questions and find the chat to ask. go=true: ask it, get picks.
    import brain
    if str(go).lower() in ("true", "yes", "1"):
        if not GO_WORDS.search(getattr(state, "last_user_text", "")):
            return "Not started: they haven't said go. Say the plan and ask 'Go?'"
        if not asked["questions"] or time.time() - asked["at"] > PLAN_SECONDS:
            return "Nothing waiting (it's been too long). Look again first (go=false)."
        hwnd, tab, name = asked["chat"]
        pc.select_tab(hwnd, tab)
        time.sleep(1.0)
        reply = ask_chat(hwnd, questions_text(asked["project"], asked["questions"]))
        if reply is None:
            return f"Couldn't find the message box in '{name}'."
        if not reply:
            return f"Asked '{name}', but no answer came within {REPLY_WAIT // 60} minutes."
        raw = brain.write(MAP_RULES, json.dumps({"questions": asked["questions"], "reply": reply[-6000:]}),
                          seconds=20, writers=brain.QUICK_WRITERS)
        found = re.search(r"\{.*\}", raw or "", re.S)
        try:
            picks = json.loads(found.group(0), strict=False)["answers"] if found else []
        except (ValueError, KeyError):
            picks = []
        if not picks:
            return f"'{name}' answered, but I couldn't match it to the questions. Its reply starts: {reply[:300]}"
        words, own = [], []
        for p in picks:
            n = int(p["question"]) if str(p.get("question", "")).isdigit() else 0
            q = asked["questions"][n - 1] if 0 < n <= len(asked["questions"]) else {}
            words.append(f"{q.get('header') or n}: {p.get('option') or 'Other'}"
                         + (f" (own answer: {p['own']})" if p.get("own") else "")
                         + (f", because {p['why']}" if p.get("why") else ""))
            if p.get("own"):
                own.append(p["own"])
        if own:
            pc.set_clipboard("\n".join(own))
        asked["questions"] = None
        return ("Claude's picks (tell them; they click these in Claude Code's question box"
                + ("; the own answer is copied, ready to paste in Other" if own else "") + "): " + "; ".join(words))
    where, questions = open_questions(project)
    if not questions:
        return "Claude Code has no questions waiting" + (f" in {project}." if project else ".")
    found = find_chat(chat, where)
    if not found:
        return (f"Claude Code in {where} asks {len(questions)} question(s), but I can't see a Claude/ChatGPT chat tab"
                f"{' called ' + chat if chat else ' about ' + where}. Ask which chat.")
    asked.update(questions=questions, project=where, chat=found, at=time.time())
    heads = ", ".join(q.get("header") or q.get("question", "")[:30] for q in questions)
    return (f"PLAN (say it short, ask 'Go?'): Claude Code in {where} asks {len(questions)} question(s) ({heads}). "
            f"I'll paste them into your chat '{found[2][:50]}' and bring back its picks.")
