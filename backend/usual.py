# "Open my usual tabs" / "open yesterday's tabs": M.I.N.D really knows these, it never guesses.
# - Usual = what you use most over the last 2 weeks, learned from time spent: apps and VS Code projects (learn.py
#   counts those), and websites per Chrome account (note_site, only the site's name, never the page).
#   "Remember these as my usual" saves what's open now instead, and that list wins.
# - Yesterday = what Chrome itself had open when it last closed (its session files, per Chrome account).
# Saved in knowledge.json / profile.json (personal, git-ignored).
import os
import re
import glob
import time
import struct
import datetime
import subprocess
import win32gui
from urllib.parse import urlparse
from memory import profile, save_profile

CHROME_DATA = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
DAYS = 14         # "usual" looks at the last two weeks
MOST_TABS = 6     # never more at once: 8 GB of memory, and Chrome is already the biggest user
MOST_APPS = 3
MOST_PROJECTS = 2
NOT_USUAL_APPS = {"file explorer", "snippingtool", "notepad", "chrome", "taskmgr", "searchhost", "shellexperiencehost",
                  "applicationframehost", "lockapp", "code", "electron", "python", "pythonw", "cmd", "powershell"}
SKIP_ADDRESS = re.compile(r"^(chrome|edge|about|data|file|devtools|chrome-extension|view-source):|//(localhost|127\.)", re.I)
# Sites counted before websites were noted by address: their names in the time counts
KNOWN_SITES = {"youtube": "www.youtube.com", "claude": "claude.ai", "chatgpt": "chatgpt.com", "gmail": "mail.google.com",
               "inbox": "mail.google.com", "gemini": "gemini.google.com", "whatsapp": "web.whatsapp.com",
               "groqcloud": "console.groq.com", "instagram": "www.instagram.com", "github": "github.com"}

# ---------- Which site you're on, in which Chrome account (every 30 s, from learn.count_time) ----------
def window_profile(hwnd):
    # The Chrome account of a window: its toolbar has a button with the profile's name. Several profiles can share
    # a name ("Pavithran"), then it's the one Chrome used last.
    import pc
    profiles = pc.chrome_profiles()
    names = {name.lower() for _, name, *_ in profiles}
    uia = pc.automation()
    buttons = uia.ElementFromHandle(hwnd).FindAll(4, uia.CreatePropertyCondition(30003, 50000))
    for i in range(min(buttons.Length, 120)):
        name = (buttons.GetElement(i).CurrentName or "").strip().lower()
        if name in names:
            same = [folder for folder, n, *_ in profiles if n.lower() == name]
            return max(same, key=last_used)
    return ""

def last_used(folder):
    files = glob.glob(os.path.join(CHROME_DATA, folder, "Sessions", "Session_*"))
    return max((os.path.getmtime(f) for f in files), default=0)

def note_site(day_sites, hwnd):
    # +0.5 minute for the site showing in this Chrome window: {"Profile 2|mail.google.com": minutes}
    import watcher
    address = watcher.page_address(hwnd)
    if not address or SKIP_ADDRESS.search(address):
        return
    host = urlparse(address if "//" in address else "https://" + address).netloc.lower()
    if host and "." in host:
        key = f"{window_profile(hwnd)}|{host}"
        day_sites[key] = day_sites.get(key, 0) + 0.5

# ---------- What's usual ----------
def learned():
    # {"apps": [...], "projects": [...], "tabs": [{"url", "profile"}]}: most used first, from the time counts
    import learn
    since = (datetime.date.today() - datetime.timedelta(days=DAYS)).isoformat()
    apps, projects, sites = {}, {}, {}
    for day, used in learn.book["usage"].items():
        if day < since:
            continue
        for kind, minutes in used.items():
            if kind.startswith("VS Code: "):
                projects[kind[9:]] = projects.get(kind[9:], 0) + minutes
            elif kind.startswith("Chrome: "):
                # (older counts only have the page's site name: known sites still count)
                word = re.sub(r"^\(\d+\)\s*", "", kind[8:]).split()[0].lower() if kind[8:].strip() else ""
                if word in KNOWN_SITES:
                    key = "|" + KNOWN_SITES[word]
                    sites[key] = sites.get(key, 0) + minutes
            elif kind != "Chrome" and kind.lower() not in NOT_USUAL_APPS:
                apps[kind] = apps.get(kind, 0) + minutes
    for day, used in learn.book.get("sites", {}).items():
        if day >= since:
            for key, minutes in used.items():
                sites[key] = sites.get(key, 0) + minutes
    # A site counted with its account beats the same site without one
    hosts = {}
    for key, minutes in sites.items():
        folder, host = key.split("|", 1)
        have = hosts.setdefault(host, {"profile": "", "minutes": 0, "best": 0})
        have["minutes"] += minutes
        if folder and minutes > have["best"]:
            have["profile"], have["best"] = folder, minutes
    top = lambda found, least: [k for k, v in sorted(found.items(), key=lambda x: -x[1]) if v >= least]
    tabs = sorted(hosts.items(), key=lambda x: -x[1]["minutes"])
    return {"apps": top(apps, 5)[:MOST_APPS], "projects": top(projects, 10)[:MOST_PROJECTS],
            "tabs": [{"url": "https://" + host + "/", "profile": v["profile"]} for host, v in tabs if v["minutes"] >= 3][:MOST_TABS]}

def my_usual():
    return profile.get("usual") or learned()  # (what they told M.I.N.D wins over what it learned)

# ---------- Yesterday: Chrome's own session files ----------
def session_tabs(path):
    # The tabs in one Chrome session file: [address]. The file is a list of small records ("SNSS"):
    # 6 = a tab's page, 7 = which page of the tab is showing, 0 = its window, 16 = tab closed, 17 = window closed.
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"SNSS":
        return []
    tabs, closed_windows, pos = {}, set(), 8
    def tab(number):
        return tabs.setdefault(number, {"pages": {}, "showing": None, "window": None, "closed": False})
    while pos + 2 <= len(data):
        size = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        if not size or pos + size > len(data):
            break
        kind, body = data[pos], data[pos + 1:pos + size]
        pos += size
        try:
            if kind == 6:
                number, index, length = struct.unpack("<iii", body[4:16])
                tab(number)["pages"][index] = body[16:16 + length].decode("utf-8", "ignore")
            elif kind == 7:
                number, index = struct.unpack("<ii", body[:8])
                tab(number)["showing"] = index
            elif kind == 0:
                window, number = struct.unpack("<ii", body[:8])
                tab(number)["window"] = window
            elif kind == 16:
                tab(struct.unpack("<i", body[:4])[0])["closed"] = True
            elif kind == 17:
                closed_windows.add(struct.unpack("<i", body[:4])[0])
        except struct.error:
            pass
    alive = [t for t in tabs.values() if t["pages"] and not t["closed"]]
    # (closing the last window is how Chrome is closed: then its tabs are still "the last session")
    showing = [t for t in alive if t["window"] not in closed_windows] or alive
    return [t["pages"].get(t["showing"], t["pages"][max(t["pages"])]) for t in showing]

def yesterdays_tabs():
    # [{"url", "profile"}]: each Chrome account's newest session from before today (today's is locked while
    # Chrome runs), from the last 3 days only
    today = datetime.datetime.combine(datetime.date.today(), datetime.time()).timestamp()
    found = []
    for folder in glob.glob(os.path.join(CHROME_DATA, "*", "Sessions")):
        files = sorted(glob.glob(os.path.join(folder, "Session_*")), key=os.path.getmtime, reverse=True)
        for path in files:
            when = os.path.getmtime(path)
            if when >= today:
                continue
            if when < today - 3 * 86400:
                break
            try:
                urls = [u for u in session_tabs(path) if u and not SKIP_ADDRESS.search(u)]
            except OSError:
                continue  # (in use)
            found += [{"url": u, "profile": os.path.basename(os.path.dirname(folder)), "when": when} for u in urls]
            if urls:
                break
    seen, tabs = set(), []
    for t in sorted(found, key=lambda t: -t["when"]):
        if t["url"] not in seen:
            seen.add(t["url"])
            tabs.append({"url": t["url"], "profile": t["profile"]})
    return tabs[:MOST_TABS * 2]

# ---------- Opening them ----------
def is_open_already(url):
    # Is a tab of that site open? (by the site's main word in the tab titles: "youtube", "claude")
    import pc
    host = urlparse(url).netloc.lower().replace("www.", "")
    word = {"mail.google.com": "inbox", "web.whatsapp.com": "whatsapp"}.get(host, host.split(".")[0])
    try:
        return any(word in t[2].lower() for t in pc.browser_tabs())
    except Exception:
        return False

def open_tab(url, folder=""):
    import hud
    chrome = hud.chrome_path()
    if chrome:
        subprocess.Popen([chrome] + ([f"--profile-directory={folder}"] if folder else []) + [url])
        time.sleep(0.4)  # (a moment between tabs, or Chrome can drop one)

def name_of(url):
    return urlparse(url).netloc.replace("www.", "") or url[:30]

def open_all(found):
    # Opens what isn't open yet. Returns what it did, in words.
    import tools
    import pc
    opened, already = [], []
    for app in found.get("apps", []):
        if pc.find_windows(app):
            already.append(app)
        elif tools.run_tool("open_app", {"name": app})[1]:
            opened.append(app)
    for project in found.get("projects", []):
        if any(project.lower() in w[3].lower() and "visual studio code" in w[3].lower() for w in pc.open_windows()):
            already.append(project)
        elif tools.run_tool("open_folder", {"name": project})[1]:
            opened.append(f"{project} in VS Code")
    for tab in found.get("tabs", []):
        if is_open_already(tab["url"]):
            already.append(name_of(tab["url"]))
        else:
            open_tab(tab["url"], tab.get("profile", ""))
            opened.append(name_of(tab["url"]))
    said = ("Opened: " + ", ".join(opened) + ". ") if opened else "Nothing new to open. "
    return said + (("Already open: " + ", ".join(already) + ".") if already else "")

# ---------- What's open now ("remember these as my usual") ----------
def open_now():
    import pc
    import watcher
    apps, projects, tabs = [], [], []
    for hwnd, pid, app, title in pc.open_windows():
        if title in pc.MIND_WINDOWS:
            continue
        if app.lower() == "chrome":
            address = watcher.page_address(hwnd)
            if address and not SKIP_ADDRESS.search(address):
                url = address if "//" in address else "https://" + address
                tabs.append({"url": url, "profile": window_profile(hwnd)})
        elif app == "Code":
            parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", title)]
            if len(parts) >= 2:
                projects.append(parts[-2])
        else:
            nice = {"WhatsApp.Root": "WhatsApp"}.get(app, app)
            if nice.lower() not in NOT_USUAL_APPS and nice not in apps:
                apps.append(nice)
    return {"apps": apps[:MOST_APPS * 2], "projects": projects[:MOST_PROJECTS], "tabs": tabs[:MOST_TABS]}

def describe(found):
    parts = list(found.get("apps", [])) + [f"{p} (VS Code)" for p in found.get("projects", [])]
    parts += [name_of(t["url"]) for t in found.get("tabs", [])]
    return ", ".join(parts)

def open_usual(action="open", what=""):
    # Tool. open = their usual things; yesterday = Chrome's tabs from last time; list = just say what's usual;
    # save = remember what's open now as their usual; remove = take 'what' out of it; forget = back to learning
    if action == "yesterday":
        tabs = yesterdays_tabs()
        if not tabs:
            return "Chrome has no saved tabs from yesterday (it only keeps what was open when it last closed). Say so."
        return open_all({"tabs": tabs})
    if action == "save":
        found = open_now()
        if not any(found.values()):
            return "Nothing is open to remember."
        profile["usual"] = found
        save_profile()
        return "Remembered as their usual: " + describe(found)
    if action == "forget":
        profile.pop("usual", None)
        save_profile()
        return "Forgot the saved list; usual is learned from what they use again."
    found = my_usual()
    if action == "remove":
        word = what.lower().replace(" ", "")
        found = {"apps": [a for a in found["apps"] if word not in a.lower().replace(" ", "")],
                 "projects": [p for p in found["projects"] if word not in p.lower().replace(" ", "")],
                 "tabs": [t for t in found["tabs"] if word not in t["url"].lower()]}
        profile["usual"] = found
        save_profile()
        return "Took that out. Their usual now: " + describe(found)
    if not any(found.values()):
        return ("Not enough known yet about what they usually open. Don't guess: say so, and offer 'remember these as "
                "my usual' once their things are open.")
    if action == "list":
        return "Their usual: " + describe(found)
    return open_all(found)
