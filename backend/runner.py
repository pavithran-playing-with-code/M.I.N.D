# A project's terminal, by voice: "Mind, run npm run share in gameroom", "Mind, stop gameroom's backend" (= Ctrl+C),
# "Mind, what's running in blogsite?", "Mind, docker compose up in blogsite".
#
# VS Code hides its terminals from Windows' screen reader, so M.I.N.D can't see which terminal is which; typing
# blindly could put "npm run share" + Enter into a CODE FILE. So this works on the real programs instead:
# - stop: the programs started inside that project's folder (node, python, ...) are stopped, like Ctrl+C,
#   and M.I.N.D says exactly which ones. The terminal itself stays open.
# - run: only the project's OWN scripts (the "scripts" in its package.json files), npm/pnpm/yarn install, and
#   docker compose up/down where a compose file exists. Never a made-up command. It runs in its own visible
#   Windows Terminal tab in the right folder, so all the output is there to see.
import json
import os
import re
import subprocess

import psutil

SKIP = {"node_modules", ".git", "venv", ".venv", "dist", "build", ".next", "__pycache__", ".expo", "android", "ios"}
NEVER_STOP = {"code.exe", "explorer.exe", "chrome.exe", "msedge.exe", "powershell.exe", "pwsh.exe", "cmd.exe",
              "windowsterminal.exe", "openconsole.exe", "conhost.exe", "wt.exe", "bash.exe", "git.exe",
              "claude.exe"}  # (Claude Code works inside the project folder too: never stop it)

HERE = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))  # (M.I.N.D's own folder: it never stops itself)

def started_by_vs_code(p):
    # Never stopped: VS Code's own helpers (extensions, language servers: VS Code is their parent), anything
    # Claude Code started (its commands and servers, somewhere up the line), and M.I.N.D's own programs.
    # Things you ran in a terminal yourself have the terminal's shell above them: only those may be stopped.
    try:
        if os.path.normcase(p.cwd()).startswith(HERE):
            return True
        parent = p.parent()
        if parent and parent.name().lower() == "code.exe":
            return True
        for _ in range(8):
            if not parent:
                break
            if parent.name().lower() == "claude.exe":
                return True
            parent = parent.parent()
    except psutil.Error:
        pass
    return False

COMPOSE = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")

def project_dir(name, again=True):
    import pc
    for folder in pc.find_folder(name or ""):
        if any(os.path.exists(os.path.join(folder, m)) for m in (".git", "package.json", "CLAUDE.md", "main.py") + COMPOSE):
            return folder
    if again:  # (a new project: the folder list is only refreshed every 15 minutes, so look once more now)
        pc.index_folders()
        return project_dir(name, False)
    return ""

def folders_with(root):
    # Every folder in the project (3 levels deep) with a package.json or a compose file: {folder: info}
    found = {}
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        if here[len(root):].count(os.sep) >= 3:
            dirs[:] = []
        info = {}
        if "package.json" in files:
            try:
                with open(os.path.join(here, "package.json"), encoding="utf-8") as f:
                    info["scripts"] = json.load(f).get("scripts") or {}
            except (OSError, ValueError):
                info["scripts"] = {}
            info["manager"] = ("pnpm" if os.path.exists(os.path.join(here, "pnpm-lock.yaml")) or os.path.exists(os.path.join(root, "pnpm-lock.yaml"))
                               else "yarn" if os.path.exists(os.path.join(here, "yarn.lock")) else "npm")
        if any(c in files for c in COMPOSE):
            info["compose"] = True
        if info:
            found[here] = info
    return found

def short(root, folder):
    rel = os.path.relpath(folder, root)
    return os.path.basename(root) + ("" if rel == "." else "\\" + rel)

def pick(root, places, where):
    # Several folders can do it: the one whose path has the word they said ("backend"), else ask
    if where:
        named = [f for f in places if where.lower() in os.path.relpath(f, root).lower()]
        if named:
            places = named
    return places

def run(project, command, where="", heard=""):
    root = project_dir(project)
    if not root:
        return f"Couldn't find a project called {project}."
    said = command.strip().lower()
    places = folders_with(root)
    # What to run: docker compose, an install, or one of the project's scripts
    if "docker" in said or "compose" in said:
        up = not re.search(r"\b(down|stop)\b", said)
        line, need = ("docker compose up -d" if up else "docker compose down"), "compose"
    elif re.search(r"\b(install|i)\s*$", said) or said.endswith("install"):
        line, need = "install", "scripts"
    else:
        words = re.sub(r"\b(npm|pnpm|yarn|run|the|script)\b", " ", said).split()
        name = words[-1] if words else ""
        if not name:
            return "Which script? Say its name, like 'run npm run dev in gameroom'."
        if heard and name not in heard.lower():  # (only what they said themselves: never a made-up command)
            return f"Not run: say the script's name yourself ('{name}' wasn't in your words)."
        line, need = name, "scripts"
    if need == "compose":
        options = [f for f, i in places.items() if i.get("compose")]
    elif line == "install":
        options = [f for f, i in places.items() if "manager" in i]
    else:
        options = [f for f, i in places.items() if line in i.get("scripts", {})]
        if not options:
            known = sorted({s for i in places.values() for s in i.get("scripts", {})})
            return (f"{os.path.basename(root)} has no '{line}' script. Its scripts: " + ", ".join(known[:15])) if known \
                else f"{os.path.basename(root)} has no scripts to run."
    options = pick(root, options, where)
    if not options:
        return f"Nothing in {os.path.basename(root)} can do that."
    if len(options) > 1:
        return "It's in several folders, which one? " + ", ".join(short(root, f) for f in options[:5])
    folder = options[0]
    if need == "compose":
        full = line
    else:
        manager = places[folder].get("manager", "npm")
        full = f"{manager} install" if line == "install" else (f"{manager} start" if line == "start" and manager == "npm" else f"{manager} run {line}")
    title = f"{short(root, folder)}: {full}"
    try:  # its own Windows Terminal tab, kept open so the output stays readable
        subprocess.Popen(["wt.exe", "-w", "mind", "new-tab", "--title", title, "-d", folder,
                          "powershell", "-NoExit", "-Command", full], creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        # (no Windows Terminal: "start" opens a normal console window for it; the helper itself never shows)
        subprocess.Popen(["cmd", "/c", "start", title, "/d", folder, "powershell", "-NoExit", "-Command", full],
                         creationflags=subprocess.CREATE_NO_WINDOW)
    print(f"(Terminal: ran '{full}' in {short(root, folder)})")
    return f"Running '{full}' in {short(root, folder)}, in its own terminal tab."

TERMINALS = {"windowsterminal.exe", "wt.exe", "openconsole.exe"}

def in_a_terminal(p):
    # A program inside a terminal tab M.I.N.D opened for you is YOURS (stoppable), not M.I.N.D's own helper
    try:
        for _ in range(6):
            p = p.parent()
            if not p or p.pid == os.getpid():
                return False
            if p.name().lower() in TERMINALS:
                return True
    except psutil.Error:
        pass
    return False

def inside(root, where=""):
    # The programs started inside the project folder (or its "where" part), not shells/editors/M.I.N.D itself
    base = os.path.normcase(os.path.join(root, where) if where and os.path.isdir(os.path.join(root, where)) else root)
    mine = {os.getpid()} | {p.pid for p in psutil.Process().children(recursive=True) if not in_a_terminal(p)}
    found = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (p.info["name"] or "").lower()
            if p.pid in mine or name in NEVER_STOP or started_by_vs_code(p):
                continue
            cwd = os.path.normcase(p.cwd())
            if cwd == base or cwd.startswith(base + os.sep):
                if where and not os.path.isdir(os.path.join(root, where)) and where.lower() not in cwd.lower():
                    continue
                found.append(p)
        except (psutil.Error, OSError):
            continue
    # Only the top ones (a child of another one found is stopped with its parent)
    pids = {p.pid for p in found}
    return [p for p in found if not (p.ppid() in pids)]

def describe(p, root):
    # Short and spoken-friendly: "npm run share (gameroom\backend)", "node server.js (...)"
    try:
        parts = p.cmdline()
        name = os.path.splitext(p.name())[0]
        joined = " ".join(parts)
        if "npm-cli.js" in joined:
            line = "npm " + joined.split("npm-cli.js", 1)[1].strip()
        else:
            line = name + " " + " ".join(os.path.basename(x) if os.sep in x or "/" in x else x for x in parts[1:])
        return f"{line.strip()[:60]} ({short(root, p.cwd())})"
    except psutil.Error:
        return p.name()

def stop(project, where=""):
    root = project_dir(project)
    if not root:
        return f"Couldn't find a project called {project}."
    targets = inside(root, where)
    if not targets:
        return f"Nothing is running in {os.path.basename(root)}{(' ' + where) if where else ''}."
    said = []
    for p in targets:
        said.append(describe(p, root))
        try:
            for child in p.children(recursive=True):
                child.terminate()
            p.terminate()  # (like Ctrl+C: the program ends, the terminal stays)
        except psutil.Error:
            pass
    print("(Terminal: stopped " + "; ".join(said) + ")")
    return "Stopped: " + "; ".join(said)

def running(project, where=""):
    root = project_dir(project)
    if not root:
        return f"Couldn't find a project called {project}."
    targets = inside(root, where)
    return ("Running in " + os.path.basename(root) + ": " + "; ".join(describe(p, root) for p in targets)) if targets \
        else f"Nothing is running in {os.path.basename(root)}."
