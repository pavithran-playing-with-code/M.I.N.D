# Server: a small web server so the HUD (React page) can see and talk to M.I.N.D.
# Runs in the background on http://localhost:8000
import os
import time
import random
import threading
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import state
import info
from memory import profile, save_profile, BASE_DIR

PORT = 8000
HUD_FOLDER = os.path.join(BASE_DIR, "..", "dist")  # made by "npm run build"

app = FastAPI()

class Command(BaseModel):
    text: str

@app.get("/api/state")
def get_state():
    from ears import wake_word  # already loaded by main.py
    return {**state.snapshot(), "wake_word": wake_word()}

@app.post("/api/command")
def send_command(command: Command):
    text = command.text.strip()
    if text:
        state.type_command(text)
    return {"ok": True}

@app.post("/api/showcase/close")
def close_showcase():
    # The X on the hologram panel
    state.showcase = None
    return {"ok": True}

@app.post("/api/mute")
def mute():
    # Double-tap on the orb: offline (mic off) / online
    return {"muted": state.toggle_mute()}

OFF_LINES = ["Mind off. See you, Sir.", "Mind off. Catch you later.", "Mind off."]  # made ready at start

@app.post("/api/power_off")
def power_off():
    # Turn M.I.N.D off (HUD power button, taskbar button): say goodbye and close, fast and clean
    def finish():
        import taskbar, hud, telegram_bot, voice
        time.sleep(0.2)  # let the caller get its answer first
        state.set_status("offline")
        phone = threading.Thread(target=telegram_bot.say_off, daemon=True)  # tell your phone
        phone.start()
        line = random.choice(OFF_LINES)
        try:
            voice.play_file(*voice.make_audio(line))  # ready-made: plays at once
        except Exception:
            try:  # no internet: the Windows voice (its own copy, since this is another thread)
                import comtypes, comtypes.client
                comtypes.CoInitialize()
                comtypes.client.CreateObject("SAPI.SpVoice").Speak(line)  # waits until it's said
            except Exception as e:
                print("Couldn't say goodbye:", e)
        hud.close_hud()
        taskbar.show(False)
        import audio
        audio.unduck()  # (os._exit skips atexit)
        pid_file = os.path.join(BASE_DIR, "mind.pid")
        if os.path.exists(pid_file):
            os.remove(pid_file)
        give_up = time.time() + 3
        while time.time() < give_up and voice.file_playing():
            time.sleep(0.05)  # finish the goodbye
        phone.join(max(0, min(1, give_up - time.time())))  # the phone message, but don't wait long
        os._exit(0)
    threading.Thread(target=finish, daemon=True).start()
    return {"ok": True}

@app.post("/api/orb")
def orb_clicked():
    state.click()
    return {"ok": True}

# ---------- Side panel info ----------
class Location(BaseModel):
    lat: float
    lon: float
    name: str = ""
    accuracy: float = 100  # meters

@app.get("/api/info")
def get_info():
    return {**info.snapshot(), "city": profile.get("city", "")}

@app.post("/api/speedtest")
def run_speed_test():
    info.start_speed_test()
    return {"ok": True}

@app.post("/api/location")
def set_location(place: Location):
    # Where the browser says you are, so "what's the weather" uses your exact spot
    state.location = place.model_dump()
    if place.name and place.name != "Your location" and not profile.get("city"):
        profile["city"] = place.name  # remember it, so weather works before the HUD opens next time
        save_profile()
    return {"ok": True}

@app.post("/api/browser")
async def browser_report(request: Request):
    # Reports from the M.I.N.D Chrome extension (all tabs, AI chats running/done).
    # Only an extension can send these: a web page can't fake the chrome-extension:// origin.
    if not request.headers.get("origin", "").startswith("chrome-extension://"):
        return {"ok": False}
    import browser
    return {"ok": True, **browser.report(await request.json())}  # may say "reload" (new code on disk)

@app.get("/api/browser")
def browser_status():
    # Is the extension installed / on / talking / up to date (no tab contents)
    import browser
    return {"status": browser.status()}

# Serve the built HUD page at http://localhost:8000 (if it has been built)
if os.path.isdir(HUD_FOLDER):
    app.mount("/", StaticFiles(directory=HUD_FOLDER, html=True), name="hud")

def hud_ready():
    return os.path.isdir(HUD_FOLDER)

def start():
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
