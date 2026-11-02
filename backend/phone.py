# M.I.N.D on your phone: see one laptop window live, tap/scroll/type in it, and talk to M.I.N.D.
# It's its own small web server on 127.0.0.1:8765 (never on your Wi-Fi). Tailscale (free, private: only YOUR
# devices) carries it to the phone: run once on the laptop: tailscale serve --bg 8765
# Only a paired phone can use it: the first time, the phone asks for a 6-digit code that the laptop shows.
import ctypes
import hashlib
import hmac
import io
import json
import os
import secrets
import threading
import time
import wave

import psutil
import uvicorn
import win32con
import win32gui
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

import state
from memory import BASE_DIR

PORT = 8765
PAGE = os.path.join(BASE_DIR, "phone.html")
DEVICES = os.path.join(BASE_DIR, "phone_devices.json")  # paired phones (only a hash of each key; git-ignored)
ICON = os.path.join(os.path.dirname(BASE_DIR), "extension", "icons", "icon128.png")
CODE_MINUTES = 5
CODE_TRIES = 5

app = FastAPI()
user32 = ctypes.windll.user32

# ---------- Pairing: a code on the laptop, a long secret key on the phone ----------
pairing = {"code": "", "until": 0.0, "tries": 0}

def load_devices():
    try:
        with open(DEVICES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def save_devices(devices):
    with open(DEVICES, "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=1)

def hashed(key):
    return hashlib.sha256(key.encode()).hexdigest()

def allowed(key):
    if not key:
        return False
    wanted = hashed(key)
    return any(hmac.compare_digest(wanted, known) for known in load_devices())

def check(key):
    if not allowed(key):
        raise HTTPException(401, "Not paired")
    stay_awake()

def stay_awake():
    # While the phone is using it, the laptop doesn't fall asleep on its own (closing the lid still sleeps it)
    ctypes.windll.kernel32.SetThreadExecutionState(0x00000001 | 0x00000002)  # "in use" (system + display), once per request

class Code(BaseModel):
    code: str = ""
    name: str = "Phone"

@app.post("/phone/api/pair_start")
def pair_start():
    # The phone asks to pair: a new code shows on the laptop (HUD chat, floating reactor, log)
    if time.time() > pairing["until"]:
        pairing.update(code=f"{secrets.randbelow(1000000):06d}", until=time.time() + CODE_MINUTES * 60, tries=0)
        line = f"Phone pairing code: {pairing['code']} (type it on your phone; it works for {CODE_MINUTES} minutes)."
        print(line)
        state.add_message("mind", line)
    return {"ok": True, "minutes": CODE_MINUTES}

@app.post("/phone/api/pair")
def pair(given: Code):
    if time.time() > pairing["until"] or pairing["tries"] >= CODE_TRIES:
        raise HTTPException(403, "The code ran out. Ask for a new one.")
    pairing["tries"] += 1
    if not hmac.compare_digest(given.code.strip(), pairing["code"]):
        raise HTTPException(403, f"Wrong code ({CODE_TRIES - pairing['tries']} tries left).")
    pairing.update(code="", until=0.0)
    key = secrets.token_urlsafe(32)
    devices = load_devices()
    devices[hashed(key)] = {"name": given.name[:40], "added": time.strftime("%Y-%m-%d %H:%M")}
    save_devices(devices)
    print(f"(Phone paired: {given.name[:40]})")
    state.add_message("mind", "Your phone is paired now.")
    return {"key": key}

# ---------- The page ----------
@app.get("/phone")
@app.get("/phone/")
def page():
    return FileResponse(PAGE, headers={"Cache-Control": "no-store"})

SERVICE_WORKER = """
// Keeps a copy of the phone page, so it still opens (and says the laptop can't be reached) when the laptop is off
const COPY = 'mind-phone'
self.addEventListener('install', (e) => { self.skipWaiting(); e.waitUntil(caches.open(COPY).then((c) => c.addAll(['/phone', '/phone/icon.png']))) })
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET' || url.pathname.startsWith('/phone/api/')) return  // (live data is never kept)
  e.respondWith(fetch(e.request).then((res) => {
    if (res.ok) { const copy = res.clone(); caches.open(COPY).then((c) => c.put(e.request, copy)) }
    return res
  }).catch(() => caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || caches.match('/phone'))))
})
"""

@app.get("/phone/sw.js")
def service_worker():
    return Response(SERVICE_WORKER, media_type="text/javascript", headers={"Cache-Control": "no-store", "Service-Worker-Allowed": "/phone"})

@app.get("/phone/icon.png")
def icon():
    return FileResponse(ICON)

@app.get("/phone/manifest.json")
def manifest():
    # So "Add to Home screen" makes it open like an app (no address bar)
    return {"name": "M.I.N.D", "short_name": "M.I.N.D", "start_url": "/phone", "display": "standalone",
            "background_color": "#03070d", "theme_color": "#03070d",
            "icons": [{"src": "/phone/icon.png", "sizes": "128x128", "type": "image/png"}]}

# ---------- The laptop's windows ----------
def laptop_locked():
    # The lock screen belongs to Windows itself: nothing can click or type there
    return any((p.info["name"] or "").lower() == "logonui.exe" for p in psutil.process_iter(["name"]))

@app.get("/phone/api/windows")
def windows(x_mind_key: str = Header("")):
    check(x_mind_key)
    import overlay
    found = [w for w in overlay.open_list() if w["title"] not in overlay.MIND_TITLES]
    return {"windows": found, "locked": laptop_locked(), "front": win32gui.GetForegroundWindow()}

last_frame = {}  # handle -> fingerprint of the last picture sent (unchanged = nothing is sent)

def capture(handle, width):
    import overlay
    try:
        with overlay.real_pixels():  # (the whole window, not just the top-left part, on a scaled screen)
            return capture_now(handle, width)
    except Exception as e:  # (it closed or changed size just then: skip this one picture)
        print("(Phone: couldn't take a picture of a window:", str(e)[:60] + ")")
        return None

def capture_now(handle, width):
    # The window as a picture (PrintWindow: works even when something covers it), shrunk to the phone's width
    import win32ui
    from PIL import Image
    left, top, right, bottom = win32gui.GetWindowRect(handle)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0 or user32.IsHungAppWindow(handle):
        return None
    window_dc = win32gui.GetWindowDC(handle)
    made = []  # (whatever got made is freed again, even if a step fails halfway)
    try:
        source = win32ui.CreateDCFromHandle(window_dc)
        made.append(source.DeleteDC)
        target = source.CreateCompatibleDC()
        made.append(target.DeleteDC)
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(source, w, h)
        made.append(lambda: win32gui.DeleteObject(bitmap.GetHandle()))
        target.SelectObject(bitmap)
        user32.PrintWindow(handle, target.GetSafeHdc(), 2)  # 2 = also what's drawn by the graphics card (Chrome)
        info = bitmap.GetInfo()
        image = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    finally:
        for free in reversed(made):
            free()
        win32gui.ReleaseDC(handle, window_dc)
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.BILINEAR)
    return image

@app.get("/phone/api/frame")
def frame(handle: int, width: int = 900, known: str = "", x_mind_key: str = Header("")):
    # The newest picture of the window, or 204 if nothing changed since the one the phone has ("known")
    check(x_mind_key)
    if not win32gui.IsWindow(handle):
        raise HTTPException(404, "That window is gone.")
    if win32gui.IsIconic(handle):
        return Response(status_code=204, headers={"X-Minimized": "1"})
    image = capture(handle, max(240, min(width, 1400)))
    if image is None:
        return Response(status_code=204)
    stamp = hashlib.md5(image.resize((96, 54)).convert("L").tobytes()).hexdigest()[:12]
    if stamp == known:
        return Response(status_code=204, headers={"X-Stamp": stamp})
    out = io.BytesIO()
    image.save(out, "JPEG", quality=60)
    return Response(out.getvalue(), media_type="image/jpeg", headers={"X-Stamp": stamp, "Cache-Control": "no-store"})

# ---------- Using the window: it comes to the front on the laptop, then the tap/keys land in it ----------
def to_front(handle):
    import pc
    if not win32gui.IsWindow(handle):
        raise HTTPException(404, "That window is gone.")
    if laptop_locked():
        raise HTTPException(423, "The laptop is locked. Unlock it first.")
    if win32gui.IsIconic(handle):
        win32gui.ShowWindow(handle, win32con.SW_RESTORE)
    if win32gui.GetForegroundWindow() != handle:  # (the Alt trick on a window already in front opens Chrome's menu)
        pc.bring_to_front(handle)

def spot(handle, x, y):
    left, top, right, bottom = win32gui.GetWindowRect(handle)
    return int(left + max(0.0, min(1.0, x)) * (right - left)), int(top + max(0.0, min(1.0, y)) * (bottom - top))

class Pick(BaseModel):
    handle: int

@app.post("/phone/api/open")
def open_window(pick: Pick, x_mind_key: str = Header("")):
    check(x_mind_key)
    to_front(pick.handle)
    return {"ok": True}

class Tap(BaseModel):
    handle: int
    x: float
    y: float
    kind: str = "click"  # click / double / right

MOUSE = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}

@app.post("/phone/api/tap")
def tap(touch: Tap, x_mind_key: str = Header("")):
    check(x_mind_key)
    to_front(touch.handle)
    user32.SetCursorPos(*spot(touch.handle, touch.x, touch.y))
    down, up = MOUSE["right" if touch.kind == "right" else "left"]
    for _ in range(2 if touch.kind == "double" else 1):
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.05)
    return {"ok": True}

class Scroll(BaseModel):
    handle: int
    x: float
    y: float
    notches: int  # + = down the page, - = up

@app.post("/phone/api/scroll")
def scroll(wheel: Scroll, x_mind_key: str = Header("")):
    check(x_mind_key)
    to_front(wheel.handle)
    user32.SetCursorPos(*spot(wheel.handle, wheel.x, wheel.y))
    notches = max(-15, min(15, wheel.notches))
    for _ in range(abs(notches)):
        user32.mouse_event(0x0800, 0, 0, -120 if notches > 0 else 120, 0)  # 0x0800 = wheel
        time.sleep(0.02)
    return {"ok": True}

class Keys(BaseModel):
    handle: int
    text: str = ""   # letters to type
    keys: str = ""   # a shortcut: enter, backspace, ctrl+c, alt+tab...

@app.post("/phone/api/keys")
def keys(press: Keys, x_mind_key: str = Header("")):
    import pc
    check(x_mind_key)
    to_front(press.handle)
    if press.text:
        pc.type_text(press.text[:4000])
    if press.keys:
        said = pc.press_keys(press.keys)
        if not said.startswith("Pressed"):
            raise HTTPException(400, said)
    return {"ok": True}

# ---------- M.I.N.D's own state: online (listening) or offline (mic off, the core dims) ----------
@app.get("/phone/api/status")
def status(x_mind_key: str = Header("")):
    check(x_mind_key)
    return {"online": not state.muted, "status": state.status, "locked": laptop_locked()}

class Mic(BaseModel):
    on: bool

@app.post("/phone/api/mic")
def mic(switch: Mic, x_mind_key: str = Header("")):
    # The phone's Online / Offline switch: same as triple-tapping the core on the laptop
    import settings
    check(x_mind_key)
    settings.set_mic(switch.on)
    print(f"(Phone: M.I.N.D {'online' if switch.on else 'offline'})")
    return {"online": not state.muted}

# ---------- Talking to M.I.N.D (the same Live brain and memory as on the laptop) ----------
class Say(BaseModel):
    text: str = ""

def voice_wav(sound, rate=24000):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(sound)
    return out.getvalue()

def answer(text="", sound=b""):
    import base64
    import live_brain
    got = live_brain.phone_turn(text, sound)
    if not got:
        return {"heard": text, "said": "My live brain couldn't answer just now. Try again in a bit?", "voice": ""}
    heard, said, voice = got
    return {"heard": heard, "said": said, "voice": base64.b64encode(voice_wav(voice)).decode() if voice else ""}

@app.post("/phone/api/say")
def say(words: Say, x_mind_key: str = Header("")):
    check(x_mind_key)
    if not words.text.strip():
        raise HTTPException(400, "Nothing to say.")
    return answer(text=words.text.strip()[:2000])

@app.post("/phone/api/talk")
async def talk(request: Request, x_mind_key: str = Header("")):
    # A voice clip recorded on the phone (webm / mp4 / ogg): M.I.N.D hears it and answers with its voice
    check(x_mind_key)
    import ears
    clip = await request.body()
    if not clip or len(clip) > 8_000_000:
        raise HTTPException(400, "No voice clip.")
    try:
        sound = ears.from_ogg(clip)  # (PyAV reads any of those formats)
    except Exception as e:
        raise HTTPException(400, f"Couldn't read that clip: {str(e)[:80]}")
    return await __import__("asyncio").to_thread(answer, "", sound)

def start():
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
