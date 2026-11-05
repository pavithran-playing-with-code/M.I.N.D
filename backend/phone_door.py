# The phone door: a tiny helper that is always running (it starts with Windows, and M.I.N.D starts it too).
# While M.I.N.D is OFF it answers the phone app on M.I.N.D's phone port, so the app can show
# "M.I.N.D is off" with a "Turn M.I.N.D on" button. Only a paired phone (its key) can turn it on.
# While M.I.N.D is ON it stays out of the way (M.I.N.D's own phone server has the port).
# Plain Python only (no web framework), so it costs ~15 MB of RAM and almost no CPU.
import ctypes
import hashlib
import hmac
import http.server
import json
import os
import subprocess
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765                     # (the same port as M.I.N.D's phone server: Tailscale already points here)
DEVICES = os.path.join(HERE, "phone_devices.json")
PID_FILE = os.path.join(HERE, "mind.pid")
STARTING_FOR = 90               # seconds: after "turn on", M.I.N.D gets this long to start before the door opens again

door = {"server": None, "started_at": 0.0}

def mind_running():
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            pid = int(f.read().strip() or 0)
    except (OSError, ValueError):
        return False
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # (can we see that process? = it's alive)
    if not handle:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE

def paired(key):
    if not key:
        return False
    try:
        with open(DEVICES, encoding="utf-8") as f:
            known = json.load(f)
    except (OSError, ValueError):
        return False
    wanted = hashlib.sha256(key.encode()).hexdigest()
    return any(hmac.compare_digest(wanted, k) for k in known)

def start_mind():
    door["started_at"] = time.time()
    pythonw = os.path.join(HERE, "venv", "Scripts", "pythonw.exe")
    subprocess.Popen([pythonw, "main.py"], cwd=HERE, creationflags=0x08000000 | 0x00000008)  # (no window, on its own)
    # (the door keeps saying "starting" until M.I.N.D is up; then the loop below hands the port over)

class Door(http.server.BaseHTTPRequestHandler):
    def answer(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/phone/api/status"):
            starting = time.time() - door["started_at"] < STARTING_FOR
            self.answer(200, {"mind_off": True, "starting": starting})
        elif self.path.rstrip("/") == "/phone":
            with open(os.path.join(HERE, "phone.html"), "rb") as f:
                page = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        else:
            self.answer(503, {"mind_off": True})  # (everything else needs M.I.N.D itself)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(min(length, 10000))
        if self.path.startswith("/phone/api/start"):
            if not paired(self.headers.get("X-Mind-Key", "")):
                return self.answer(403, {"ok": False, "detail": "This phone isn't paired"})
            if not mind_running():
                start_mind()
            return self.answer(200, {"ok": True})
        self.answer(503, {"mind_off": True})

    def log_message(self, *args):
        pass  # (quiet)

def open_door():
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Door)
    except OSError:
        return  # (the port is busy: M.I.N.D is starting or something else has it; try again later)
    door["server"] = server
    threading.Thread(target=server.serve_forever, daemon=True).start()

def close_door():
    server, door["server"] = door["server"], None
    if server:
        server.shutdown()
        server.server_close()

def main():
    # Only one door at a time
    ctypes.windll.kernel32.CreateMutexW(None, False, "MIND_phone_door")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return
    while True:
        running = mind_running()
        if running and door["server"]:
            close_door()
        elif not running and not door["server"]:
            open_door()
        time.sleep(2)

if __name__ == "__main__":
    main()
