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
ICONS = os.path.join(BASE_DIR, "icons")  # M.I.N.D's icon in every size (icons.py draws them)
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
const COPY = 'mind-phone-2'  // (a new name wipes the old copy: it had the old icon)
self.addEventListener('install', (e) => { self.skipWaiting(); e.waitUntil(caches.open(COPY).then((c) => c.addAll(['/phone']))) })
self.addEventListener('activate', (e) => e.waitUntil(caches.keys().then((all) => Promise.all(all.filter((k) => k !== COPY).map((k) => caches.delete(k)))).then(() => self.clients.claim())))
// A notification from the laptop (alerts, reminders, "Claude is done", things M.I.N.D sends you)
self.addEventListener('push', (e) => {
  let note = { title: 'M.I.N.D', body: '' }
  try { note = e.data.json() } catch (err) { note.body = e.data ? e.data.text() : '' }
  e.waitUntil(self.registration.showNotification(note.title || 'M.I.N.D', { body: note.body, icon: '/phone/icon-v2.png', badge: '/phone/icon-v2.png', tag: 'mind-' + Date.now() }))
})
self.addEventListener('notificationclick', (e) => {
  e.notification.close()
  e.waitUntil(self.clients.matchAll({ type: 'window' }).then((open) => open.length ? open[0].focus() : self.clients.openWindow('/phone')))
})
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET' || url.pathname.startsWith('/phone/api/')) return  // (live data is never kept)
  if (url.pathname.includes('icon') || url.pathname.endsWith('manifest.json')) return  // (icons always fresh from the laptop)
  // The copy on the phone answers at once (the app opens instantly); a fresh one is fetched in the background
  // for next time. With no copy yet, it waits for the laptop.
  const fresh = fetch(e.request).then((res) => {
    if (res.ok) { const copy = res.clone(); caches.open(COPY).then((c) => c.put(e.request, copy)) }
    return res
  })
  e.waitUntil(fresh.catch(() => {}))
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || fresh.catch(() => caches.match('/phone'))))
})
"""

@app.get("/phone/sw.js")
def service_worker():
    return Response(SERVICE_WORKER, media_type="text/javascript", headers={"Cache-Control": "no-store", "Service-Worker-Allowed": "/phone"})

@app.get("/phone/icon-v2.png")
def icon():
    return FileResponse(os.path.join(ICONS, "app-192.png"))

@app.get("/phone/icon-v2-{name}.png")
def icon_size(name: str):
    if name not in ("180", "192", "512", "maskable-512"):
        raise HTTPException(404, "No such icon.")
    return FileResponse(os.path.join(ICONS, f"app-{name}.png"), headers={"Cache-Control": "max-age=86400"})

@app.get("/phone/manifest.json")
def manifest():
    # So "Add to Home screen" makes it open like an app (no address bar)
    return {"name": "M.I.N.D", "short_name": "M.I.N.D", "id": "/phone", "start_url": "/phone", "display": "standalone", "orientation": "any",
            "background_color": "#03070d", "theme_color": "#03070d",
            "icons": [{"src": "/phone/icon-v2-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                      {"src": "/phone/icon-v2-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                      {"src": "/phone/icon-v2-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}

# ---------- The laptop's windows ----------
def laptop_locked():
    # The lock screen belongs to Windows itself: nothing can click or type there
    return any((p.info["name"] or "").lower() == "logonui.exe" for p in psutil.process_iter(["name"]))

@app.get("/phone/api/windows")
def windows(x_mind_key: str = Header("")):
    check(x_mind_key)
    import overlay
    found = [w for w in overlay.open_list() if w["title"] not in overlay.MIND_TITLES]
    make_thumbs([w["handle"] for w in found if not w["minimized"]])  # (ready by the time the phone asks)
    return {"windows": found, "locked": laptop_locked(), "front": win32gui.GetForegroundWindow()}

THUMB_WIDTH, THUMB_KEEP = 320, 30  # the list's small pictures: this wide, kept this many seconds
thumbs = {}  # handle -> (when, jpeg)
making = set()

def make_thumbs(handles):
    # Makes the small pictures for the list in the background, 4 at a time (one by one took ~1.4 s for 8)
    from concurrent.futures import ThreadPoolExecutor
    def one(handle):
        try:
            image = capture(handle, THUMB_WIDTH)
            if image is not None:
                out = io.BytesIO()
                image.save(out, "JPEG", quality=55)
                thumbs[handle] = (time.time(), out.getvalue())
        finally:
            making.discard(handle)
    todo = [h for h in handles if h not in making and time.time() - thumbs.get(h, (0, b""))[0] > THUMB_KEEP]
    making.update(todo)
    if todo:
        pool = ThreadPoolExecutor(4)
        for h in todo:
            pool.submit(one, h)
        pool.shutdown(wait=False)

def ready_thumb(handle, wait=2.0):
    # The list picture: the one made ahead (waits a moment if it's still being made)
    end = time.time() + wait
    while handle in making and time.time() < end:
        time.sleep(0.05)
    when, jpeg = thumbs.get(handle, (0, b""))
    return jpeg if time.time() - when < THUMB_KEEP else b""

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
    if width <= THUMB_WIDTH + 40 and not known:
        jpeg = ready_thumb(handle)
        if jpeg:
            return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    image = capture(handle, max(240, min(width, 1400)))
    if image is None:
        return Response(status_code=204)
    stamp = hashlib.md5(image.resize((96, 54)).convert("L").tobytes()).hexdigest()[:12]
    if stamp == known:
        return Response(status_code=204, headers={"X-Stamp": stamp})
    out = io.BytesIO()
    image.save(out, "JPEG", quality=55)
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

# ---------- Control Center on the phone: the same settings as the HUD's (settings.py) ----------
@app.get("/phone/api/settings")
def phone_settings(x_mind_key: str = Header("")):
    import settings
    check(x_mind_key)
    return {"groups": settings.panel()}

class Change(BaseModel):
    key: str
    value: object = None

@app.post("/phone/api/setting")
def phone_setting(change: Change, x_mind_key: str = Header("")):
    import settings
    check(x_mind_key)
    worked, message = settings.change(change.key, change.value)
    return {"ok": worked, "message": message, "groups": settings.panel()}

@app.post("/phone/api/unpair")
def unpair(x_mind_key: str = Header("")):
    # "Forget this phone": its key stops working (pair again with a new code to come back)
    check(x_mind_key)
    devices = load_devices()
    devices.pop(hashed(x_mind_key), None)
    save_devices(devices)
    subs = load_subs()
    subs.pop(hashed(x_mind_key), None)
    with open(PUSH_SUBS, "w", encoding="utf-8") as f:
        json.dump(subs, f)
    print("(A phone was unpaired)")
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
        return {"heard": text, "said": "My main brain couldn't answer just now. Try again in a bit?", "voice": ""}
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

# ---------- Notifications on the phone (web push: they pop up even when the app is closed) ----------
# The phone's browser gives an address to send to; only messages signed with the laptop's own key are shown.
PUSH_KEY = os.path.join(BASE_DIR, "phone_push_key.pem")       # (git-ignored, made once)
PUSH_SUBS = os.path.join(BASE_DIR, "phone_push.json")         # where each paired phone wants its notifications

def push_keys():
    from py_vapid import Vapid01
    from cryptography.hazmat.primitives import serialization
    import base64
    vapid = Vapid01.from_file(PUSH_KEY) if os.path.exists(PUSH_KEY) else None
    if vapid is None:
        vapid = Vapid01()
        vapid.generate_keys()
        vapid.save_key(PUSH_KEY)
    raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")

def load_subs():
    try:
        with open(PUSH_SUBS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

@app.get("/phone/api/push_key")
def push_key(x_mind_key: str = Header("")):
    check(x_mind_key)
    return {"key": push_keys()}

@app.post("/phone/api/push_subscribe")
async def push_subscribe(request: Request, x_mind_key: str = Header("")):
    check(x_mind_key)
    sub = await request.json()
    if not isinstance(sub, dict) or not str(sub.get("endpoint", "")).startswith("https://"):
        raise HTTPException(400, "Not a notification address.")
    subs = load_subs()
    new = subs.get(hashed(x_mind_key)) != sub
    subs[hashed(x_mind_key)] = sub  # (one per paired phone)
    with open(PUSH_SUBS, "w", encoding="utf-8") as f:
        json.dump(subs, f)
    if new:
        # A first notification right away, so the phone knows it really works (or sees why not)
        problem = push_one(sub, "M.I.N.D", "Notifications are on. Alerts, reminders and 'Claude is done' will come here.")
        if problem:
            return {"ok": False, "problem": problem}
    return {"ok": True}

def push_one(sub, title, text):
    # Sends one notification; returns "" if the push service accepted it, else why not
    from pywebpush import webpush, WebPushException
    push_keys()
    try:
        webpush(sub, json.dumps({"title": title, "body": text[:400]}), vapid_private_key=PUSH_KEY,
                vapid_claims={"sub": "mailto:mind@localhost.invalid"}, ttl=3600, timeout=10)
        return ""
    except WebPushException as e:
        code = e.response.status_code if e.response is not None else ""
        return f"push service said {code}: {str(e)[:120]}"
    except Exception as e:
        return str(e)[:150]

@app.post("/phone/api/push_unsubscribe")
def push_unsubscribe(x_mind_key: str = Header("")):
    # The phone's Notifications switch turned off: nothing more is sent to this phone
    check(x_mind_key)
    subs = load_subs()
    subs.pop(hashed(x_mind_key), None)
    with open(PUSH_SUBS, "w", encoding="utf-8") as f:
        json.dump(subs, f)
    return {"ok": True}

def notify(text, title="M.I.N.D"):
    # Alerts, reminders, "Claude is done", messages M.I.N.D sends you: a notification on each paired phone.
    # Runs in the background, never makes M.I.N.D wait.
    def send():
        subs = load_subs()
        gone = []
        for owner, sub in subs.items():
            problem = push_one(sub, title, text)
            if " 404" in problem or " 410" in problem:
                gone.append(owner)  # (that phone turned notifications off or reinstalled)
            elif problem:
                print("Couldn't notify the phone:", problem)
        if gone:
            subs = {k: v for k, v in load_subs().items() if k not in gone}
            with open(PUSH_SUBS, "w", encoding="utf-8") as f:
                json.dump(subs, f)
    threading.Thread(target=send, daemon=True).start()

def connected():
    return bool(load_subs())

# ---------- The inbox: things M.I.N.D sends you (a text, a screenshot, a file), in the Mind tab ----------
INBOX = os.path.join(BASE_DIR, "phone_inbox")   # (git-ignored; the last INBOX_KEEP are kept)
INBOX_KEEP = 30
FILE_LIMIT = 100 * 1024 * 1024

def inbox_list():
    try:
        with open(os.path.join(INBOX, "list.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []

def to_inbox(kind, text="", name="", data=b""):
    os.makedirs(INBOX, exist_ok=True)
    item = {"id": secrets.token_hex(6), "kind": kind, "text": text, "name": name, "at": time.strftime("%d %b, %I:%M %p")}
    if data:
        with open(os.path.join(INBOX, item["id"]), "wb") as f:
            f.write(data)
    items = inbox_list() + [item]
    for old in items[:-INBOX_KEEP]:
        try:
            os.remove(os.path.join(INBOX, old["id"]))
        except OSError:
            pass
    with open(os.path.join(INBOX, "list.json"), "w", encoding="utf-8") as f:
        json.dump(items[-INBOX_KEEP:], f)
    return item

@app.get("/phone/api/inbox")
def inbox(x_mind_key: str = Header("")):
    check(x_mind_key)
    return {"items": inbox_list()}

@app.get("/phone/api/inbox/{item_id}")
def inbox_file(item_id: str, x_mind_key: str = Header("")):
    check(x_mind_key)
    item = next((i for i in inbox_list() if i["id"] == item_id), None)
    path = os.path.join(INBOX, item_id)
    if not item or not os.path.exists(path):
        raise HTTPException(404, "That's no longer in the inbox.")
    kind = "image/jpeg" if item["kind"] == "image" else "application/octet-stream"
    return FileResponse(path, media_type=kind, filename=item.get("name") or None)

def screenshot():
    from PIL import ImageGrab
    shot = ImageGrab.grab(all_screens=False)
    shot.thumbnail((1920, 1920))
    out = io.BytesIO()
    shot.convert("RGB").save(out, "JPEG", quality=80)
    return out.getvalue()

def send_to_phone(text="", screenshot_too=False):
    # Tool: "Mind, send this to my phone: ..." / "send a screenshot to my phone"
    if not connected():
        return "Their phone has no notifications on yet: tell them to open the M.I.N.D phone app and tap 'Turn on notifications'."
    said = []
    if text:
        to_inbox("text", text)
        notify(text)
        said.append("Sent to their phone.")
    if screenshot_too or not text:
        to_inbox("image", "Your screen", "screen.jpg", screenshot())
        notify("Your screen is in the M.I.N.D app.", "Screenshot")
        said.append("Screenshot sent to their phone.")
    return " ".join(said)

def send_file_to_phone(which):
    # Tool: "send me the PDF I downloaded today" (a number or name from find_files)
    import pc
    if not connected():
        return "Their phone has no notifications on yet: tell them to open the M.I.N.D phone app and tap 'Turn on notifications'."
    path, problem = pc.pick_file(which)
    if problem:
        return problem
    if os.path.getsize(path) > FILE_LIMIT:
        return f"{os.path.basename(path)} is too big to send (over 100 MB)."
    with open(path, "rb") as f:
        to_inbox("file", os.path.basename(path), os.path.basename(path), f.read())
    notify(os.path.basename(path) + " is in the M.I.N.D app.", "File from your laptop")
    return f"Sent {os.path.basename(path)} to their phone (it's in the M.I.N.D app's inbox)."

# ---------- A photo from the phone: "what's this?" ----------
@app.post("/phone/api/photo")
async def photo(request: Request, x_mind_key: str = Header(""), x_question: str = Header("")):
    import urllib.parse
    check(x_mind_key)
    picture = await request.body()
    if not picture or len(picture) > 15_000_000:
        raise HTTPException(400, "No photo.")
    question = urllib.parse.unquote(x_question).strip()[:500]
    def look_and_answer():
        import live_brain
        seen = live_brain.read_picture(picture, "a photo they sent from their phone", question or "What is this?")
        return answer(text=f"(They sent a photo{': ' + question if question else ''}. What it shows: {seen}) "
                           + (question or "What's this?"))
    import asyncio
    return await asyncio.to_thread(look_and_answer)

# ---------- Staying awake, so the phone can always reach the laptop ----------
# Asleep, the laptop's Wi-Fi is off (S3 sleep): nothing can reach it, and it can't be woken from a phone over
# Wi-Fi. So while the setting says so, M.I.N.D asks Windows not to sleep. The SCREEN still turns off as usual
# (that's most of the power); a tap in the phone app wakes it. Closing the lid still does what Windows says.
ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
awake = {"held": False}

def should_stay_awake():
    import settings
    import psutil
    wanted = str(settings.get("stay_awake"))
    if wanted == "always":
        return True
    if wanted == "charging":
        battery = psutil.sensors_battery()
        return battery is None or battery.power_plugged  # (no battery = a desktop: always plugged in)
    return False

def keep_awake():
    # One long-lived thread holds the "stay awake" request (Windows ties it to the thread that asked)
    while True:
        try:
            want = should_stay_awake()
        except Exception:
            want = False
        if want != awake["held"]:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if want else 0))
            awake["held"] = want
            print("(Laptop stays awake for the phone)" if want else "(Laptop may sleep again)")
        time.sleep(30)

def start():
    import icons
    threading.Thread(target=keep_awake, daemon=True).start()
    icons.ensure()  # (the app icon in every size)
    import server
    server.run_in_background(app, PORT)  # (selector loop: keeps accepting after a dropped connection)
