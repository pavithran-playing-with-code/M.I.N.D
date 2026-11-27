# Updates for friends' M.I.N.D: every few hours it checks the public GitHub repo's version.json. A newer version
# is installed BY ITSELF at a moment nobody is using the laptop (setting "Update Mind by itself", on by default),
# and it says what's new afterwards. With the setting off it only tells them ("Say 'Mind, update yourself'").
# Updating = a separate helper
# program (this file run as a script) that waits for M.I.N.D to close, backs up the files it replaces, copies the
# new ones in, installs new Python parts if the list changed, starts M.I.N.D again, and if the new M.I.N.D
# doesn't come up within 2 minutes, puts the old files back and starts the old one (rollback).
# Personal files (.env, profile.json, memory...) are never in a release, so they're never touched.
# The owner's own copy (it has a .git folder) never updates itself: it IS where updates come from.
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

REPO = "pavithran-playing-with-code/M.I.N.D"   # the public repo friends download from
BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
VERSION_FILE = os.path.join(ROOT, "version.json")
FILES_LIST = "release_files.txt"                # every file of a release (to remove files a new one dropped)
BACKUPS = os.path.join(BACKEND, "update_backup")
CHECK_HOURS = 6
AWAY_SECONDS = 180  # nobody touched the laptop this long = a good moment to update by itself
NO_WINDOW = 0x08000000
found = {"version": None, "notes": "", "checked": 0.0, "told": None}

def local():
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 0, "notes": ""}

def is_dev_copy():
    return os.path.isdir(os.path.join(ROOT, ".git"))

def fetch(url, seconds=20):
    request = urllib.request.Request(url, headers={"User-Agent": "MIND-updater", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=seconds) as answer:
        return answer.read()

def latest():
    # The newest release's version.json (raw file from the public repo's main branch)
    return json.loads(fetch(f"https://raw.githubusercontent.com/{REPO}/main/version.json?t={int(time.time())}"))

def check(force=False):
    # Returns the newer version's info, or None. Never on the owner's own copy.
    if is_dev_copy():
        return None
    if not force and time.time() - found["checked"] < CHECK_HOURS * 3600:
        return found if found["version"] else None
    found["checked"] = time.time()
    try:
        newest = latest()
    except Exception as e:
        print("(Update check failed)", str(e)[:100])
        return None
    if int(newest.get("version", 0)) > int(local().get("version", 0)):
        found.update(version=int(newest["version"]), notes=newest.get("notes", ""))
        return found
    found.update(version=None, notes="")
    return None

REMIND_HOURS = 6  # not updated yet: said again this often (not at night), until they update

def free_moment():
    # Nobody is using the laptop or Mind right now: no talk going on, no call, no key or mouse for a few minutes
    import alerts, calls, setup, state
    return (not state.live and not calls.in_call() and not setup.needed()
            and alerts.idle_seconds() >= AWAY_SECONDS)

def by_itself(newer, profile, switched_on):
    # Install this version without asking? (the switch is on, and this version didn't already fail to start)
    return bool(newer) and switched_on and profile.get("update_failed") != newer["version"]

def after_update():
    # First start after it updated itself: say what's new, once. If the old version is still here, the new one
    # didn't start and was put back: that version isn't tried by itself again (they're told it's waiting instead).
    import alerts
    from memory import profile, save_profile
    going = profile.pop("updating_to", None)
    if not going:
        return
    if int(local().get("version", 0)) >= int(going.get("version", 0)):
        notes = f" What's new: {going['notes']}." if going.get("notes") else ""
        line = f"I updated myself to version {going['version']} while you were away.{notes}"
        alerts.say("updated", line, line, 0, phone=True)
    else:
        profile["update_failed"] = going.get("version")
        print(f"(The update to version {going.get('version')} didn't start, the old version is back: see logs/update_log.txt)")
    save_profile()

def keep_checking():
    # Background thread: at start (after 3 minutes) and then every hour. With "Update Mind by itself" on (the
    # default) a new version is installed at the next moment nobody is at the laptop. Otherwise it's told once
    # in full, then a short reminder every REMIND_HOURS until it's installed. Remembered across restarts (profile).
    import alerts, settings
    from memory import profile, save_profile
    time.sleep(100)  # (after the quiet start: alerts wait 90 s)
    try:
        after_update()
    except Exception as e:
        print("(After-update note failed)", str(e)[:100])
    time.sleep(80)
    while True:
        newer = check()
        if by_itself(newer, profile, settings.on("auto_update")):
            for _ in range(120):  # (looks every 30 s for an hour, then checks for an even newer one)
                if free_moment():
                    profile["updating_to"] = {"version": newer["version"], "notes": newer["notes"]}
                    save_profile()
                    print(f"(Nobody's here: updating myself to version {newer['version']})")
                    start_update(quiet=True)
                    return
                time.sleep(30)
            continue
        told = profile.get("update_told") or {}
        first = newer and told.get("version") != newer["version"]
        due = newer and (first or time.time() - told.get("at", 0) >= REMIND_HOURS * 3600)
        if due and not alerts.quiet_hours():
            if first:
                notes = f": {newer['notes']}" if newer["notes"] else ""
                line = f"A new version of Mind is ready{notes}. Say 'Mind, update yourself' when you're free."
            else:
                line = "Reminder: a new version of Mind is still waiting. Say 'Mind, update yourself' when you're free."
            alerts.say("update", line, line, 0, phone=True)
            found["told"] = newer["version"]
            profile["update_told"] = {"version": newer["version"], "at": time.time()}
            save_profile()
        time.sleep(3600)

def update_mind(action="check"):
    # The tool: "Mind, any updates?" (check) / "Mind, update yourself" (install)
    if is_dev_copy():
        return "This is the developer's own copy (it has git): it doesn't update itself. Changes come from Claude Code here."
    newer = check(force=True)
    mine = local().get("version", 0)
    if not newer:
        return f"Already on the newest version ({mine})."
    if action != "install":
        return f"Version {newer['version']} is ready (you have {mine}). What's new: {newer['notes'] or 'fixes'}. Ask if they want it now."
    import state
    said = (getattr(state, "last_user_text", "") or "").lower()
    if not any(w in said for w in ("update", "upgrade", "install", "yes", "yeah", "sure", "go ahead", "do it")):
        return "Not updated: they didn't ask for it. Ask 'Shall I update now?' first."
    start_update()
    return (f"Updating to version {newer['version']}: I'll close, update and come back in about a minute "
            f"(longer if new parts need downloading). Say ONE short line like 'Updating, back in a minute.'")

def start_update(quiet=False):
    # The helper runs separately (M.I.N.D must be closed while its files are replaced)
    python = os.path.join(BACKEND, "venv", "Scripts", "python.exe")
    subprocess.Popen([python, os.path.abspath(__file__), "apply", str(os.getpid())], cwd=BACKEND,
                     creationflags=NO_WINDOW | 0x00000008)  # (detached: it outlives M.I.N.D)
    def later():
        time.sleep(1 if quiet else 6)  # (time to say "updating")
        import server
        server.power_off(quiet=quiet)
    import threading
    threading.Thread(target=later, daemon=True).start()
    print("(Updating myself: the helper takes over)")

# ---------- The helper (runs as: python updater.py apply <pid>) ----------
def log(text):
    os.makedirs(os.path.join(BACKEND, "logs"), exist_ok=True)
    with open(os.path.join(BACKEND, "logs", "update_log.txt"), "a", encoding="utf-8") as f:
        f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + text + "\n")

def release_files(folder):
    path = os.path.join(folder, FILES_LIST)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def wait_closed(pid):
    import psutil
    end = time.time() + 60
    while psutil.pid_exists(pid) and time.time() < end:
        time.sleep(0.5)
    while os.path.exists(os.path.join(BACKEND, "mind.pid")) and time.time() < end:
        time.sleep(0.5)
    time.sleep(1.5)

def start_mind():
    subprocess.Popen([os.path.join(BACKEND, "venv", "Scripts", "pythonw.exe"), "main.py"], cwd=BACKEND,
                     creationflags=NO_WINDOW | 0x00000008)

def healthy(seconds=120):
    # The new M.I.N.D is up: its web server answers and it wrote its pid
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/api/setup", timeout=3)
            if os.path.exists(os.path.join(BACKEND, "mind.pid")):
                return True
        except Exception:
            pass
        time.sleep(3)
    return False

def copy_in(source, names):
    for name in names:
        target = os.path.join(ROOT, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(source, name), target)

def same_file(a, b):
    try:
        with open(a, "rb") as x, open(b, "rb") as y:
            return x.read() == y.read()
    except OSError:
        return False

def apply(pid):
    log("Update started")
    wait_closed(pid)
    work = os.path.join(BACKEND, "update_download")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    try:
        data = fetch(f"https://codeload.github.com/{REPO}/zip/refs/heads/main", seconds=120)
        with open(os.path.join(work, "new.zip"), "wb") as f:
            f.write(data)
        with zipfile.ZipFile(os.path.join(work, "new.zip")) as z:
            z.extractall(work)
        new = next(os.path.join(work, d) for d in os.listdir(work) if os.path.isdir(os.path.join(work, d)))
        new_files = release_files(new)
        if not new_files:
            raise RuntimeError("the download has no file list")
        old_files = release_files(ROOT)
        version = json.load(open(os.path.join(new, "version.json"), encoding="utf-8"))["version"]
    except Exception as e:
        log(f"Download failed, nothing changed: {e}")
        shutil.rmtree(work, ignore_errors=True)
        start_mind()
        return

    # Back up every file this update replaces or removes (rollback)
    backup = os.path.join(BACKUPS, str(local().get("version", 0)))
    shutil.rmtree(backup, ignore_errors=True)
    for name in set(old_files) | set(new_files):
        here = os.path.join(ROOT, name)
        if os.path.exists(here):
            os.makedirs(os.path.dirname(os.path.join(backup, name)), exist_ok=True)
            shutil.copy2(here, os.path.join(backup, name))
    lock_changed = not same_file(os.path.join(new, "backend", "requirements-lock.txt"),
                                 os.path.join(BACKEND, "requirements-lock.txt"))
    node_changed = not same_file(os.path.join(new, "package-lock.json"), os.path.join(ROOT, "package-lock.json"))
    try:
        copy_in(new, new_files)
        for name in set(old_files) - set(new_files):  # files the new version doesn't have any more
            try:
                os.remove(os.path.join(ROOT, name))
            except OSError:
                pass
        python = os.path.join(BACKEND, "venv", "Scripts", "python.exe")
        if lock_changed:
            log("New Python parts: installing")
            subprocess.run([python, "-m", "pip", "install", "-r", "requirements-lock.txt", "--disable-pip-version-check"],
                           cwd=BACKEND, creationflags=NO_WINDOW, timeout=1800, check=True)
        if node_changed and shutil.which("npm.cmd"):
            log("New HUD parts: installing")
            subprocess.run(["npm.cmd", "ci", "--no-audit", "--no-fund"], cwd=ROOT, creationflags=NO_WINDOW, timeout=1800)
        start_mind()
        if healthy():
            log(f"Updated to version {version}")
            shutil.rmtree(work, ignore_errors=True)
            return
        raise RuntimeError("the new version didn't start")
    except Exception as e:
        log(f"Update failed ({e}): putting the old version back")
        stop_new()
        for name in set(new_files) - set(old_files):
            try:
                os.remove(os.path.join(ROOT, name))
            except OSError:
                pass
        copy_in(backup, [n for n in set(old_files) | set(new_files) if os.path.exists(os.path.join(backup, n))])
        start_mind()
        log("Old version back" if healthy() else "Old version put back, but it didn't answer either")
    shutil.rmtree(work, ignore_errors=True)

def stop_new():
    # Ends a new M.I.N.D that started but isn't healthy (only M.I.N.D's own main.py from this folder)
    import psutil
    for p in psutil.process_iter(["cmdline", "cwd"]):
        try:
            line = " ".join(p.info["cmdline"] or [])
            if "main.py" in line and (p.info["cwd"] or "").lower() == BACKEND.lower():
                p.kill()
        except Exception:
            pass
    time.sleep(2)
    try:
        os.remove(os.path.join(BACKEND, "mind.pid"))
    except OSError:
        pass

if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "apply":
    apply(int(sys.argv[2]))
