# Server: a small web server so the HUD (React page) can see and talk to M.I.N.D.
# Runs in the background on http://localhost:8000
import os
import re
import time
import random
import asyncio
import threading
import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
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

@app.get("/api/pulse")
def get_pulse():
    return state.pulse()

@app.get("/api/state")
def get_state():
    from ears import wake_word  # already loaded by main.py
    return {**state.snapshot(), "wake_word": wake_word()}

# ---------- M.I.N.D Live: talk like a person (live_brain.py) ----------
@app.get("/live")
def live_page():
    # Never cached: M.I.N.D's hidden Live window kept running an old copy of the page after changes
    return FileResponse(os.path.join(BASE_DIR, "live.html"), headers={"Cache-Control": "no-store"})

@app.websocket("/api/live")
async def live_talk(ws: WebSocket):
    # Only M.I.N.D's own page may use it (a website can't connect and spend the free brain)
    if ws.headers.get("origin", "") not in ("http://localhost:8000", "http://127.0.0.1:8000"):
        await ws.close(code=1008)
        return
    await ws.accept()
    import live_brain
    try:
        await live_brain.run(ws, auto="auto" in ws.query_params)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("Live page stopped:", str(e)[:200])

class LiveTest(BaseModel):
    clip: str = ""   # e.g. "laptop/12.wav" from backend/hearing_test
    alert: str = ""  # a test announcement (said like "Claude is done")
    reply: bool = False  # the clip is a reply inside the talk going on (no "Mind" needed)
    text: str = ""   # a question typed in instead of a recording ("what's this error on my screen?")
    early: bool = False  # like real use: the connection starts on "Mind", while the clip is still being "said"
    unclear: bool = False  # like a wake where the words weren't clear (a possible false wake)

@app.post("/api/live_test")
def live_test(test: LiveTest):
    # For Claude's own tests: a hearing-test recording goes to M.I.N.D Live exactly as if the ears had
    # just heard you say it after "Mind" (so fixes are checked without the owner testing them)
    import live_brain
    if test.alert:
        state.alerts.append(test.alert)
        return {"ok": True}
    if test.text:
        return {"ok": live_brain.wake(b"", test.text)}
    folder = os.path.realpath(os.path.join(BASE_DIR, "hearing_test"))
    path = os.path.realpath(os.path.join(folder, test.clip))
    if not path.startswith(folder + os.sep) or not os.path.isfile(path):
        return {"ok": False, "why": "only recordings in hearing_test"}
    with open(path, "rb") as f:
        sound = f.read()[44:]  # (skip the wav header)
    if test.early and not test.reply:
        live_brain.warm()
        time.sleep(len(sound) / 32000)  # (as long as saying it takes)
    if not test.reply:
        live_brain.speed.clear()
        live_brain.speed["stopped"] = time.time()  # (so the log shows how fast the answer came)
    return {"ok": live_brain.feed(sound) if test.reply else live_brain.wake(sound, "", unclear=test.unclear)}

@app.get("/api/notes")
def notes_list():
    import notes
    return notes.listed()

class NoteAsk(BaseModel):
    action: str = "add"
    id: str = ""
    text: str = ""

@app.post("/api/notes")
def notes_change(ask: NoteAsk, request: Request):
    # The HUD Notes card: add / done / undo / pin / delete / edit / clear_done (only M.I.N.D's own pages)
    import notes
    if not own_page(request):
        return Response(status_code=403)
    result = notes.change(ask.action, ask.id, ask.text)
    return {"ok": result is not None, **notes.listed()}

@app.get("/api/guide")
def guide():
    # The Mind Guide panel's contents (apps.CONTROLS / ABILITIES / PHONE_GUIDE)
    import apps
    return apps.guide_data()

@app.post("/api/command")
def send_command(command: Command):
    text = command.text.strip()
    if text:
        state.type_command(text)
    return {"ok": True}

class Typed(BaseModel):
    wpm: int
    accuracy: int
    seconds: float
    mode: str = "passage"

class GameDone(BaseModel):
    game: str
    score: int = 0
    won: bool = False
    draw: bool = False

@app.post("/api/game_result")
def game_done(result: GameDone):
    import apps
    apps.game_result(result.game, result.score, result.won, result.draw)
    return {"ok": True}

@app.post("/api/typing_result")
def typing_done(result: Typed):
    import apps
    apps.typing_result(result.wpm, result.accuracy, result.seconds, result.mode)
    return {"ok": True}

class ScreenResult(BaseModel):
    id: int
    shown: str
    open: list = []

@app.post("/api/screen_result")
def screen_result(result: ScreenResult):
    # The Jarvis HUD's answer to "show my VS Code in the HUD": what it shows (or that nothing matched)
    state.screen_result = result.model_dump()
    return {"ok": True}

class Embed(BaseModel):
    handle: int
    x: int
    y: int
    width: int
    height: int
    tab: str = ""

@app.post("/api/embed")
def embed_window(place: Embed):
    # Jarvis mode: this real window goes into the hole in the HUD
    import overlay
    return overlay.embed(place.handle, place.x, place.y, place.width, place.height, place.tab)

class Which(BaseModel):
    handle: int = 0

@app.post("/api/embed/raise")
def embed_raise(which: Which):
    import overlay
    overlay.raise_embedded(which.handle)
    return {"ok": True}

@app.post("/api/embed/lower")
def embed_lower(which: Which):
    import overlay
    overlay.lower_embedded(which.handle)
    return {"ok": True}

@app.post("/api/embed/release")
def embed_release(which: Which):
    import overlay
    overlay.release(which.handle)
    return {"ok": True}

@app.get("/api/windows")
def open_windows():
    import overlay
    return {"windows": overlay.open_list()}

@app.get("/api/window_picture/{handle}")
def window_picture(handle: int):
    import overlay
    try:
        image = overlay.picture(handle)
    except Exception:
        image = None
    return Response(image, media_type="image/jpeg") if image else Response(status_code=404)

class Layout(BaseModel):
    layout: dict

@app.post("/api/workspace")
def save_workspace(new: Layout, request: Request):
    # The HUD's layout, after you moved, resized, minimized or hid something
    origin = request.headers.get("origin", "")
    if origin and not re.match(r"http://(localhost|127\.0\.0\.1)(:\d+)?$", origin):
        return Response(status_code=403)
    import workspace
    return {"v": workspace.replace(new.layout)}

# ---------- Mail panel (gmail.py): only M.I.N.D's own pages may read or send mail ----------
class MailAsk(BaseModel):
    view: str = "important"
    words: str = ""
    account: str = ""
    id: str = ""
    action: str = ""
    to: str = ""
    subject: str = ""
    body: str = ""
    reply_id: str = ""
    draft: bool = False

def own_page(request):
    origin = request.headers.get("origin", "")
    return not origin or re.match(r"http://(localhost|127\.0\.0\.1)(:\d+)?$", origin)

@app.post("/api/mail/{what}")
def mail(what: str, ask: MailAsk, request: Request):
    if not own_page(request):
        return Response(status_code=403)
    import gmail
    try:
        if what == "panel":
            return {"said": gmail.show_panel()}
        if what == "list":
            return gmail.panel_list(ask.view, ask.words, ask.account)
        if what == "open":
            return gmail.panel_open(ask.id)
        if what == "act":
            return gmail.panel_act(ask.id, ask.action)
        if what == "send":
            return gmail.panel_send(ask.to, ask.subject, ask.body, ask.reply_id, ask.account, ask.draft)
    except Exception as e:
        return {"problem": f"Gmail didn't answer ({str(e)[:100]})"}
    return Response(status_code=404)

@app.get("/api/life")
def life_summary(request: Request, days: int = 7):
    # The Life dashboard (life.py): the quick part from this laptop's own counts
    if not own_page(request):
        return Response(status_code=403)
    import life
    return life.summary(days)

@app.get("/api/life/mail")
def life_mail(request: Request, days: int = 7):
    # Its mail part (asks Gmail: a few seconds, so the page asks for it separately)
    if not own_page(request):
        return Response(status_code=403)
    import life
    try:
        return life.mail_part(days)
    except Exception as e:
        return {"ready": True, "problem": str(e)[:100]}

class WindowAct(BaseModel):
    handle: int
    action: str

@app.post("/api/window")
def window_act(act: WindowAct):
    # Jarvis mode's Windows panel: bring forward / minimize / maximize / close a window
    import overlay
    return {"result": overlay.window_act(act.handle, act.action)}

@app.post("/api/showcase/close")
def close_showcase():
    # The X on the picture panel
    state.showcase = None
    return {"ok": True}

class Jarvis(BaseModel):
    on: bool

@app.post("/api/jarvis")
def jarvis_switch(wanted: Jarvis, request: Request):
    # A tap on the core: Jarvis mode on, or (inside it) back to the normal HUD. It's your own tap, so no "did they ask?"
    origin = request.headers.get("origin", "")
    if origin and not re.match(r"http://(localhost|127\.0\.0\.1)(:\d+)?$", origin):
        return Response(status_code=403)
    import overlay
    import calls
    import hud
    if wanted.on:
        if calls.in_call():
            return {"ok": False, "message": "You're on a call"}
        overlay.start()
    else:
        overlay.stop()
        for _ in range(30):  # (until it has really gone: while it runs, "open the HUD" means Jarvis mode, and it came back)
            if not overlay.running():
                break
            time.sleep(0.1)
        hud.open_hud()
    return {"ok": True, "message": ""}

@app.post("/api/mute")
def mute():
    # Double-tap on the core: offline (mic off) / online
    import settings
    settings.set_mic(state.muted)
    return {"muted": state.muted}

# ---------- The HUD's Controls panel (settings.py) ----------
class Change(BaseModel):
    key: str
    value: object = None

@app.get("/api/settings")
def get_settings():
    import settings
    return {"groups": settings.panel()}

@app.post("/api/settings")
def set_setting(change: Change, request: Request):
    # Only M.I.N.D's own pages may change settings (a website can't switch off your voice lock)
    origin = request.headers.get("origin", "")
    if origin and not re.match(r"http://(localhost|127\.0\.0\.1)(:\d+)?$", origin):
        return Response(status_code=403)
    import settings
    worked, message = settings.change(change.key, change.value)
    return {"ok": worked, "message": message, "groups": settings.panel()}

# ---------- First-run setup (setup.py): name, keys, voice, extension ----------
@app.get("/api/setup")
def get_setup():
    import setup
    return setup.status()

@app.post("/api/setup/{what}")
def do_setup(what: str, args: dict, request: Request):
    if not own_page(request):  # (only M.I.N.D's own pages: a website can't change the keys)
        return Response(status_code=403)
    import setup
    worked, message = setup.act(what, args)
    return {"ok": worked, "message": message, "status": setup.status()}

@app.get("/api/phone_setup")
def phone_setup_status():
    import phone_setup
    return phone_setup.status()

@app.post("/api/phone_setup")
def phone_setup_start(request: Request):
    if not own_page(request):
        return Response(status_code=403)
    import phone_setup
    return phone_setup.start()

@app.post("/api/phone_setup/open")
def phone_setup_open(request: Request):
    if not own_page(request):
        return Response(status_code=403)
    import phone_setup
    phone_setup.open_again()
    return {"ok": True}

weather_cache = {"data": None, "at": 0.0}

@app.get("/api/weather")
def weather():
    # For the Weather card. Really asked at most every 10 minutes (every minute after a failure).
    wait = 600 if weather_cache["data"] else 60
    if time.time() - weather_cache["at"] > wait:
        import tools
        weather_cache["at"] = time.time()
        try:
            weather_cache["data"] = tools.weather_now()
        except Exception as e:
            print("Weather card:", str(e)[:120])
    return weather_cache["data"] or {}

OFF_LINES = ["Mind off. See you.", "Mind off. Catch you later.", "Mind off."]  # made ready at start

@app.post("/api/hud_button")
def hud_button(request: Request):
    # A single click on the taskbar M.I.N.D button (button.py): HUD up, or tucked away if it's in front
    if request.headers.get("origin"):
        return Response(status_code=403)  # (only the button, never a web page)
    import hud
    threading.Thread(target=hud.hud_button, daemon=True).start()
    return {"ok": True}

@app.post("/api/power_off")
def power_off():
    # Turn M.I.N.D off (HUD power button, taskbar button): say goodbye and close, fast and clean
    def finish():
        import taskbar, hud, voice
        time.sleep(0.2)  # let the caller get its answer first
        state.set_status("offline")
        line = random.choice(OFF_LINES)
        import calls
        try:
            if calls.in_call():
                raise StopIteration  # (on a call: goes off without a word)
            voice.play_file(*voice.make_audio(line))  # ready-made: plays at once
        except StopIteration:
            pass
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
        os._exit(0)
    threading.Thread(target=finish, daemon=True).start()
    return {"ok": True}

@app.post("/api/orb")
def orb_clicked():
    import floating
    floating.single_click()  # same as a click on the floating reactor (2nd click closes the little box)
    return {"ok": True}

# ---------- Side panel info ----------
class Location(BaseModel):
    lat: float
    lon: float
    name: str = ""
    accuracy: float = 100  # meters

@app.get("/api/sysmap")
def get_sysmap():
    # The laptop map's live numbers (sysmap.py): RAM by app, CPU by app, storage
    import sysmap
    return sysmap.snapshot()

@app.get("/api/info")
def get_info():
    return {**info.snapshot(), "city": profile.get("city", "")}

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
    import watcher
    data = await request.json()
    answer = browser.report(data)  # may say "reload" (new code on disk)
    if "running" in data:
        watcher.poke.set()  # a chat started/finished: the prompt watcher looks now, not in up to 4 s
    return {"ok": True, **answer}

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

def quiet_known_noise(loop, context):
    # The phone's direct link (aiortc/aioice) has a harmless bug: a STUN retry timer fires after its answer was
    # already settled ("InvalidStateError: invalid state" in aioice/stun.py). Nothing breaks; it just isn't logged
    # as a crash. Everything else is reported as usual.
    # (The handle only says "Transaction.__retry()", so the error's own traceback is checked for aioice.)
    error = context.get("exception")
    if isinstance(error, asyncio.InvalidStateError):
        import traceback
        where = " ".join(frame.filename for frame in traceback.extract_tb(error.__traceback__))
        if "aioice" in where or "Transaction.__retry" in repr(context.get("handle", "")):
            return
    loop.default_exception_handler(context)

def run_in_background(web_app, port):
    # Windows' default "proactor" loop has a bug: one "network name is no longer available" error
    # (WinError 64, e.g. a dropped connection) stops it accepting for good, so the port went dead while
    # M.I.N.D kept running. The "selector" loop keeps accepting after such errors.
    server = uvicorn.Server(uvicorn.Config(web_app, host="127.0.0.1", port=port, log_level="warning", loop="none"))
    def run():
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(quiet_known_noise)
        loop.run_until_complete(server.serve())
    threading.Thread(target=run, daemon=True).start()

def start():
    run_in_background(app, PORT)
