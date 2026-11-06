# The ONE M.I.N.D taskbar button (owner's ask, 2026-11-06):
#   single click = open the HUD (or tuck it away if it's already in front)
#   double click = turn M.I.N.D on / off
# Windows starts this once per click, so two copies close together = a double click: the first copy takes
# click.lock, waits a moment, and if a second copy left click.double meanwhile, it's a double click.
# Only Python's own library here, so it starts fast.
import os
import sys
import time
import ctypes
import subprocess
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, "click.lock")
DOUBLE = os.path.join(HERE, "click.double")
WAIT = 0.6  # how long the first click waits for a second one

def mind_running():
    # mind.pid holds M.I.N.D's process number; is that a live pythonw?
    try:
        pid = int(open(os.path.join(HERE, "mind.pid")).read().split()[0])
    except (OSError, ValueError, IndexError):
        return False
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # (query limited information)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        name = ctypes.create_unicode_buffer(400)
        size = ctypes.c_ulong(400)
        k32.GetExitCodeProcess(handle, ctypes.byref(code))
        k32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size))
        return code.value == 259 and name.value.lower().endswith("pythonw.exe")  # 259 = still running
    finally:
        k32.CloseHandle(handle)

def ask_mind(path):
    try:
        request = urllib.request.Request("http://127.0.0.1:8000" + path, data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=3).read()
        return True
    except Exception:
        return False  # (still starting up: ignore the click)

def say(line):
    # M.I.N.D is off, so its own voice isn't there: the Windows voice says it
    command = f"(New-Object -ComObject SAPI.SpVoice).Speak('{line}') | Out-Null"
    subprocess.Popen(["powershell", "-NoProfile", "-Command", command], creationflags=subprocess.CREATE_NO_WINDOW)

def start_mind():
    python = os.path.join(HERE, "venv", "Scripts", "pythonw.exe")
    subprocess.Popen([python, os.path.join(HERE, "main.py")], cwd=HERE, creationflags=subprocess.CREATE_NO_WINDOW)

def first_click():
    # True = this copy is the first click; False = a second click (it's been noted for the first copy)
    for _ in range(2):
        try:
            os.close(os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(LOCK) < 2:
                    open(DOUBLE, "w").close()
                    return False
                os.remove(LOCK)  # left over from an old click
            except OSError:
                pass
    return False

def main():
    if not first_click():
        return
    time.sleep(WAIT)
    double = os.path.exists(DOUBLE)
    for leftover in (DOUBLE, LOCK):
        try:
            os.remove(leftover)
        except OSError:
            pass
    running = mind_running()
    if double:
        if running:
            ask_mind("/api/power_off")
        else:
            start_mind()
    elif running:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # (this click's right to bring a window forward goes to M.I.N.D)
        ask_mind("/api/hud_button")
    else:
        say("Mind is off. Double click to turn it on.")

if __name__ == "__main__":
    main()
    sys.exit(0)
