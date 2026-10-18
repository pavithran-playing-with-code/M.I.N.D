# Server: a small web server so the HUD (React page) can see and talk to M.I.N.D.
# Runs in the background on http://localhost:8000
import os
import threading
import uvicorn
from fastapi import FastAPI
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

@app.post("/api/orb")
def orb_clicked():
    state.click()
    return {"ok": True}

# ---------- Side panel info ----------
class Location(BaseModel):
    lat: float
    lon: float
    name: str = ""

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

# Serve the built HUD page at http://localhost:8000 (if it has been built)
if os.path.isdir(HUD_FOLDER):
    app.mount("/", StaticFiles(directory=HUD_FOLDER, html=True), name="hud")

def hud_ready():
    return os.path.isdir(HUD_FOLDER)

def start():
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
