# "Mind, set up my phone": gives this laptop its own private phone address and pairs a phone with one QR scan.
# 1. Tailscale (free) is installed if it's missing (winget; Windows asks "allow changes?" once)
# 2. They sign in to Tailscale in Chrome (Google works)
# 3. Tailscale Funnel gives M.I.N.D's phone app (port 8765) a fixed https address (the first time Tailscale
#    shows one "Enable" page)
# 4. A QR code with the address + a one-time pairing secret: the phone camera opens the app and it pairs itself.
# The phone needs NOTHING installed. Every step is skipped when it's already done (the owner's laptop: just the QR).
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time

NO_WINDOW = 0x08000000
PORT = 8443          # the public https port (the owner's 443 is used by another project)
APP = "http://127.0.0.1:8765"
QR_MINUTES = 10
progress = {"busy": False, "step": "", "message": "", "link": "", "address": "", "qr": "", "error": "", "until": 0.0}

def tailscale():
    found = shutil.which("tailscale")
    if found:
        return found
    path = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tailscale", "tailscale.exe")
    return path if os.path.exists(path) else None

def run(*args, seconds=20):
    try:
        done = subprocess.run([tailscale(), *args], capture_output=True, text=True, timeout=seconds,
                              creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
        return done.stdout + done.stderr
    except Exception as e:
        return str(e)

def ts_status():
    try:
        return json.loads(run("status", "--json"))
    except Exception:
        return {}

def signed_in():
    return ts_status().get("BackendState") == "Running"

def host_name():
    return (ts_status().get("Self", {}).get("DNSName") or "").rstrip(".")

def funnel_on(host):
    # Already pointing our public port at the phone app?
    try:
        on = json.loads(run("funnel", "status", "--json"))
    except Exception:
        return False
    spot = f"{host}:{PORT}"
    proxy = on.get("Web", {}).get(spot, {}).get("Handlers", {}).get("/", {}).get("Proxy", "")
    return bool(on.get("AllowFunnel", {}).get(spot)) and proxy.rstrip("/") == APP

def say(step, message, link=""):
    progress.update(step=step, message=message, link=link)
    print(f"(Phone setup: {message})")

def open_link(url):
    import pc
    pc.open_in_browser(url)

def wait_for(check, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(2)
    return False

def follow(args, seconds, waiting_line):
    # Runs a Tailscale command that may print a web page to visit (sign-in, "enable Funnel"):
    # that page opens in Chrome and the command is waited for
    process = subprocess.Popen([tailscale(), *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
    opened = set()
    def read():
        for line in process.stdout:
            for url in re.findall(r"https://login\.tailscale\.com/\S+", line):
                if url not in opened:
                    opened.add(url)
                    say(progress["step"], waiting_line, url)
                    open_link(url)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        process.kill()

def make_qr():
    # A one-time pairing secret in the link's # part (never sent to any server: only the phone app reads it)
    import phone
    import segno
    import settings
    host = host_name()
    secret = secrets.token_urlsafe(18)
    settings.change("phone_pairing", True)  # (opens pairing for 10 minutes; closes after one phone)
    phone.pairing.update(code=secret, until=time.time() + QR_MINUTES * 60, tries=0)
    address = f"https://{host}:{PORT}/phone"
    qr = segno.make(f"{address}#pair={secret}", error="m")
    progress.update(address=address, qr=qr.svg_data_uri(scale=8, border=2, dark="#000000", light="#ffffff"),
                    until=time.time() + QR_MINUTES * 60)
    say("qr", "Scan this with your phone's camera. It opens M.I.N.D and pairs it.")

def setup():
    try:
        if not tailscale():
            say("install", "Installing Tailscale (free). If Windows asks to allow changes, click Yes.")
            subprocess.run(["winget", "install", "-e", "--id", "Tailscale.Tailscale", "--silent",
                            "--accept-package-agreements", "--accept-source-agreements"],
                           capture_output=True, timeout=600, creationflags=NO_WINDOW)
            if not wait_for(tailscale, 120):
                raise RuntimeError("Tailscale didn't install. Install it from tailscale.com/download, then try again.")
            wait_for(lambda: ts_status() != {}, 60)  # (its background service starting)
        if not signed_in():
            say("sign_in", "Opening Tailscale's sign-in in Chrome...")
            threading.Thread(target=follow, args=(("up",), 300, "Sign in to Tailscale in Chrome (Google works)."),
                             daemon=True).start()
            if not wait_for(signed_in, 300):
                raise RuntimeError("Tailscale sign-in didn't finish. Say 'Mind, set up my phone' to try again.")
        host = host_name()
        if not host:
            raise RuntimeError("Tailscale has no name for this laptop yet. Try again in a minute.")
        if not funnel_on(host):
            say("funnel", "Turning on your private phone address...")
            follow(("funnel", "--bg", f"--https={PORT}", APP), 300,
                   "In Chrome, click Enable (it lets your phone reach this laptop).")
            if not wait_for(lambda: funnel_on(host), 30):
                raise RuntimeError("The phone address didn't turn on. Say 'Mind, set up my phone' to try again.")
        make_qr()
    except Exception as e:
        progress.update(error=str(e)[:200], step="error", message=str(e)[:200])
        print("(Phone setup failed)", str(e)[:200])
    finally:
        progress["busy"] = False

def start():
    # Starts the setup (or just a fresh QR) in the background and shows it on the HUD
    if not progress["busy"]:
        progress.update(busy=True, step="start", message="Getting your phone address ready...", link="",
                        qr="", error="", address="")
        threading.Thread(target=setup, daemon=True).start()
    return status()

def show_panel():
    import showcase
    showcase.put_on_hud({"kind": "phone_setup", "title": "Set up your phone"}, minutes=15, again=True)

def paired():
    if progress["qr"]:
        progress.update(qr="", step="paired", message="✅ Your phone is paired! Tap \"Add to Home screen\" in Chrome's menu on it.")

def open_again():
    if progress["link"]:
        open_link(progress["link"])

def status():
    out = dict(progress)
    if out["qr"] and time.time() > out["until"]:
        out.update(qr="", step="expired", message="That QR code ran out. Make a new one.")
    out.pop("until", None)
    return out

def setup_phone():
    # The tool: "Mind, set up my phone" / "pair my phone" / "connect my phone" (the panel starts it)
    show_panel()
    return ("The phone setup is on the HUD. Tell them in one line: follow the steps there, then scan the QR code "
            "with the phone camera (nothing to install on the phone).")
