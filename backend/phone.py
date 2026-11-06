# M.I.N.D on your phone: see one laptop window live, tap/scroll/type in it, and talk to M.I.N.D.
# It's its own small web server on 127.0.0.1:8765 (never on your Wi-Fi). Tailscale (free, private: only YOUR
# devices) carries it to the phone: run once on the laptop: tailscale serve --bg 8765
# Only a paired phone can use it: the first time, the phone asks for a 6-digit code that the laptop shows.
import asyncio
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
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, Response
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
  if (e.request.method === 'POST' && url.pathname === '/phone/share') {
    // Shared from another app: keep it on the phone, then open M.I.N.D, which asks what to do with it
    e.respondWith((async () => {
      const form = await e.request.formData()
      const box = await caches.open('mind-shared')
      for (const old of await box.keys()) await box.delete(old)
      const words = { title: form.get('title') || '', text: form.get('text') || '', url: form.get('url') || '', files: [] }
      let n = 0
      for (const file of form.getAll('files')) {
        if (!file || !file.name) continue
        await box.put('/phone/shared/' + n, new Response(file, { headers: { 'X-Name': encodeURIComponent(file.name) } }))
        words.files.push(file.name); n++
      }
      await box.put('/phone/shared/words', new Response(JSON.stringify(words)))
      return Response.redirect('/phone?shared=1', 303)
    })())
    return
  }
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
            # "Share" in any phone app (a link, text, a photo, a file) -> M.I.N.D -> the laptop
            "share_target": {"action": "/phone/share", "method": "POST", "enctype": "multipart/form-data",
                             "params": {"title": "title", "text": "text", "url": "url", "files": [{"name": "files", "accept": ["*/*"]}]}},
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

# ---------- Live view: ONE connection streams the window to the phone and carries taps/keys back ----------
# (asking for each picture again and again gave ~2-3 pictures a second; this pushes up to ~12 as soon as they change)
FAST, CALM = 0.07, 0.3  # seconds between pictures: while things change or you touch it / after 2 s of no change
IN_FLIGHT = 3           # pictures on their way to the phone at once (a slow connection never piles them up)

class Grabber:
    # Takes pictures of one window again and again; the drawing surfaces are made once and reused (~60 ms, was ~150)
    def __init__(self, handle):
        self.handle, self.size, self.parts = handle, None, None

    def free(self):
        if self.parts:
            window_dc, source, target, bitmap = self.parts
            for step in (target.DeleteDC, source.DeleteDC, lambda: win32gui.DeleteObject(bitmap.GetHandle()),
                         lambda: win32gui.ReleaseDC(self.handle, window_dc)):
                try:
                    step()
                except Exception:
                    pass
        self.parts, self.size = None, None

    def grab(self, width):
        import win32ui
        import overlay
        from PIL import Image
        with overlay.real_pixels():
            left, top, right, bottom = win32gui.GetWindowRect(self.handle)
            size = (right - left, bottom - top)
            if size[0] <= 0 or size[1] <= 0 or user32.IsHungAppWindow(self.handle):
                return None
            if size != self.size:  # (first picture, or the window changed size: new surfaces)
                self.free()
                window_dc = win32gui.GetWindowDC(self.handle)
                source = win32ui.CreateDCFromHandle(window_dc)
                target = source.CreateCompatibleDC()
                bitmap = win32ui.CreateBitmap()
                bitmap.CreateCompatibleBitmap(source, *size)
                target.SelectObject(bitmap)
                self.parts, self.size = (window_dc, source, target, bitmap), size
            target, bitmap = self.parts[2], self.parts[3]
            user32.PrintWindow(self.handle, target.GetSafeHdc(), 2)
            image = Image.frombuffer("RGB", size, bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
        if image.width > width:
            image = image.resize((width, round(image.height * width / image.width)), Image.BILINEAR, reducing_gap=2.0)
        return image

    def frame(self, width, last):
        # (the JPEG, its fingerprint), or (None, last) when nothing changed
        try:
            image = self.grab(width)
        except Exception:
            self.free()  # (it closed or changed just then: fresh surfaces next time)
            return None, last
        if image is None:
            return None, last
        stamp = hashlib.md5(image.resize((160, 90)).convert("L").tobytes()).digest()
        if stamp == last:
            return None, last
        out = io.BytesIO()
        image.save(out, "JPEG", quality=55)
        return out.getvalue(), stamp

@app.websocket("/phone/api/live")
async def live(ws: WebSocket):
    await ws.accept()
    try:
        hello = json.loads(await ws.receive_text())
        key = str(hello.get("key", ""))
        if not allowed(key):
            await ws.send_text(json.dumps({"error": "Not paired"}))
            return await ws.close()
        view = {"handle": int(hello["handle"]), "width": max(240, min(int(hello.get("width", 900)), 1400)),
                "sent": 0, "sent_at": 0.0, "busy_until": time.time() + 2, "fresh": True}
    except Exception:
        return await ws.close()
    loop = asyncio.get_running_loop()
    eyes = ThreadPoolExecutor(1)   # (one thread keeps the drawing surfaces)
    hands = ThreadPoolExecutor(1)  # taps/keys in order, without holding up the pictures
    grabber = Grabber(view["handle"])
    poke = asyncio.Event()
    jobs = {"tap": lambda a: tap(Tap(**a), key), "scroll": lambda a: scroll(Scroll(**a), key),
            "keys": lambda a: keys(Keys(**a), key)}

    def finished(job):
        view["busy_until"] = time.time() + 2  # (the window is about to change: pictures come quickly)
        poke.set()
        problem = job.exception()
        if problem is not None:
            text = problem.detail if isinstance(problem, HTTPException) else str(problem)[:80]
            asyncio.ensure_future(ws.send_text(json.dumps({"error": text})))

    async def listen():
        while True:
            message = json.loads(await ws.receive_text())
            do, args = message.get("do"), message.get("args") or {}
            if do == "ack":
                view["sent"] = max(0, view["sent"] - 1)
                poke.set()
            elif do == "width":
                view["width"], view["fresh"] = max(240, min(int(args.get("width", 900)), 1400)), True
                poke.set()
            elif do in jobs:
                view["busy_until"] = time.time() + 2
                loop.run_in_executor(hands, jobs[do], args).add_done_callback(finished)

    async def stream():
        last, said_small = None, False
        while True:
            handle = view["handle"]
            if not win32gui.IsWindow(handle):
                await ws.send_text(json.dumps({"gone": True}))
                return
            if win32gui.IsIconic(handle):
                if not said_small:
                    await ws.send_text(json.dumps({"minimized": True}))
                    said_small = True
            else:
                said_small = False
                if view["sent"] >= IN_FLIGHT and time.time() - view["sent_at"] > 3:
                    view["sent"] = 0  # (a lost "got it": don't stop forever)
                if view["sent"] < IN_FLIGHT:
                    if view["fresh"]:
                        last, view["fresh"] = None, False
                    jpeg, last = await loop.run_in_executor(eyes, grabber.frame, view["width"], last)
                    if jpeg:
                        await ws.send_bytes(jpeg)
                        view["sent"] += 1
                        view["sent_at"] = time.time()
                        view["busy_until"] = max(view["busy_until"], time.time() + 2)
            poke.clear()
            try:
                await asyncio.wait_for(poke.wait(), FAST if time.time() < view["busy_until"] else CALM)
            except asyncio.TimeoutError:
                pass

    tasks = [asyncio.ensure_future(listen()), asyncio.ensure_future(stream())]
    stay_awake()
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        eyes.submit(grabber.free)
        eyes.shutdown(wait=False)
        hands.shutdown(wait=False)
        try:
            await ws.close()
        except Exception:
            pass

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
        if not pc.bring_to_front(handle):
            # Windows often refuses a program in the background: "always on top" for a moment always works,
            # then the window takes the keyboard (the phone's taps landed on whatever window was covering it)
            import overlay
            overlay.in_front(handle)
            pc.bring_to_front(handle)

def spot(handle, x, y):
    left, top, right, bottom = win32gui.GetWindowRect(handle)
    point = int(left + max(0.0, min(1.0, x)) * (right - left)), int(top + max(0.0, min(1.0, y)) * (bottom - top))
    under = win32gui.WindowFromPoint(point)
    if under and win32gui.GetAncestor(under, 2) != handle:  # 2 = GA_ROOT: the top window at that spot
        import overlay
        overlay.in_front(handle)  # (still covered: lift it once more, never click a different window)
        under = win32gui.WindowFromPoint(point)
        if under and win32gui.GetAncestor(under, 2) != handle:
            raise HTTPException(409, "Another window is covering that spot on the laptop. Try again.")
    return point

class Pick(BaseModel):
    handle: int

# ---------- Remote tab: the phone is the laptop's touchpad and keyboard (remote.py) ----------
@app.websocket("/phone/api/remote")
async def remote_control(ws: WebSocket):
    import remote
    await ws.accept()
    try:
        hello = json.loads(await ws.receive_text())
        if not allowed(str(hello.get("key", ""))):
            await ws.send_text(json.dumps({"error": "Not paired"}))
            return await ws.close()
    except Exception:
        return await ws.close()
    print("(Phone remote connected)")
    loop = asyncio.get_running_loop()
    slow = ThreadPoolExecutor(1)  # keys, typing and media buttons, in order (mouse moves never wait for them)
    last_awake = 0.0
    try:
        await ws.send_text(json.dumps({"ok": True, "locked": laptop_locked()}))
        while True:
            message = json.loads(await ws.receive_text())
            if time.time() - last_awake > 20:
                last_awake = time.time()
                stay_awake()
                if laptop_locked():
                    await ws.send_text(json.dumps({"error": "The laptop is locked. Unlock it first."}))
            if any(k in message for k in ("m", "b", "w")):
                remote.handle(message)  # (a few microseconds: right here, so the pointer follows the finger)
            else:
                note = await loop.run_in_executor(slow, remote.handle, message)
                if note:
                    await ws.send_text(json.dumps({"error": note}))
    except Exception:
        pass
    finally:
        remote.let_go()  # a drag that was going on: the button is let go
        slow.shutdown(wait=False)
        print("(Phone remote disconnected)")

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
    point = spot(touch.handle, touch.x, touch.y)
    print(f"(Phone: {touch.kind} on '{win32gui.GetWindowText(touch.handle)[:40]}', in front: "
          f"{win32gui.GetForegroundWindow() == touch.handle})")  # (so a tap that did nothing can be traced)
    user32.SetCursorPos(*point)
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
@app.get("/phone/api/abilities")
def phone_abilities(x_mind_key: str = Header("")):
    # "What can I say?": the same list as the HUD's "What I can do" panel (apps.ABILITIES)
    import apps
    check(x_mind_key)
    return {"groups": [{"icon": i, "name": n, "say": [x for x in s if not x.startswith("(")]} for i, n, s in apps.ABILITIES]}

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
    # The phone's Online / Offline switch: same as double-tapping the core on the laptop
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

class Remove(BaseModel):
    id: str

@app.post("/phone/api/inbox_remove")
def inbox_remove(item: Remove, x_mind_key: str = Header("")):
    # The ✕ on an inbox card
    check(x_mind_key)
    items = [i for i in inbox_list() if i["id"] != item.id]
    try:
        os.remove(os.path.join(INBOX, os.path.basename(item.id)))
    except OSError:
        pass
    with open(os.path.join(INBOX, "list.json"), "w", encoding="utf-8") as f:
        json.dump(items, f)
    return {"ok": True}

# ---------- Files FROM the laptop: the newest files in your usual folders, tap one to get it on the phone ----------
LAPTOP_FOLDERS = ["Downloads", "Desktop", "Documents", "Pictures", "Videos"]
SKIP_DIRS = {"node_modules", "venv", ".git", "__pycache__", "dist", "build", ".next", "site-packages"}

# Every file in your home folder (~40,000 here) is listed in memory by a background scan (~4 s), so search and
# Recent answer instantly. The list is refreshed when it's 2 minutes old (the old one answers meanwhile).
INDEX_SKIP = SKIP_DIRS | {"AppData", "Windows", "$Recycle.Bin", "live_chrome", ".venv", "env", ".cache", ".npm", ".gradle", ".m2", ".nuget"}
index = {"files": [], "at": 0.0, "busy": False}  # files: (name lowered, path, size, modified, is_folder)

def scan_home():
    found, folders = [], [os.path.expanduser("~")]
    while folders:
        folder = folders.pop()
        try:
            with os.scandir(folder) as items:
                for item in items:
                    name = item.name
                    if name.startswith(".") or name in INDEX_SKIP:
                        continue
                    try:
                        if item.is_dir(follow_symlinks=False):
                            folders.append(item.path)
                            found.append((name.lower(), item.path, 0, item.stat().st_mtime, True))
                        elif not name.startswith("~$"):
                            info = item.stat()  # (free on Windows: it came with the folder listing)
                            found.append((name.lower(), item.path, info.st_size, info.st_mtime, False))
                    except OSError:
                        continue
        except OSError:
            continue
    index.update(files=found, at=time.time(), busy=False)

def fresh_index(wait=False, older_than=120):
    # The file list; rescanned in the background when it's older than older_than seconds. wait=True waits for
    # the new scan (a file that just arrived must show up), else the old list answers at once.
    wait = wait or index.get("stale") or not index["files"]
    if not index["busy"] and time.time() - index["at"] > older_than:
        index["busy"], index["stale"] = True, False
        worker = threading.Thread(target=scan_home, daemon=True)
        worker.start()
        index["worker"] = worker
    if wait and index["busy"] and index.get("worker"):
        index["worker"].join(15)
    return index["files"]

def recent_files(limit=40):
    home = os.path.expanduser("~")
    roots = tuple(os.path.join(home, f).lower() + os.sep for f in LAPTOP_FOLDERS)
    home_depth = home.count(os.sep)
    # (files up to 2 folders deep, like Downloads\From M.I.N.D\x.jpg: not code files deep inside projects)
    picks = [f for f in fresh_index(older_than=30) if not f[4] and f[1].lower().startswith(roots)
             and f[1].count(os.sep) - home_depth <= 3 and not f[0].endswith((".tmp", ".crdownload", ".ini", ".lnk"))]
    picks.sort(key=lambda f: -f[3])
    return [(f[3], f[2], f[1], "") for f in picks[:limit]]

HOME = os.path.expanduser("~")
HIDDEN_AT_HOME = {"AppData", "Application Data", "Local Settings", "NTUSER.DAT", "ntuser.ini", "Cookies", "Recent",
                  "SendTo", "Start Menu", "Templates", "NetHood", "PrintHood", "My Documents"}  # (Windows' own clutter)

def rel_of(path):
    return os.path.relpath(path, HOME).replace(os.sep, "/")

def home_path(rel):
    # A path the phone asked for, only if it's inside your home folder (never Windows or other users' files)
    full = os.path.realpath(os.path.join(HOME, (rel or "").replace("/", os.sep)))
    if full != os.path.realpath(HOME) and not full.lower().startswith(os.path.realpath(HOME).lower() + os.sep):
        raise HTTPException(403, "Only files in your own folders.")
    return full

def entry(path, name):
    try:
        info = os.stat(path)
    except OSError:
        return None
    folder = os.path.isdir(path)
    return {"name": name, "rel": rel_of(path), "folder": folder, "size": 0 if folder else info.st_size,
            "at": time.strftime("%d %b %Y, %I:%M %p", time.localtime(info.st_mtime)), "when": info.st_mtime}

def key_from(header, query):
    # Downloads and video playing come from links and <video>, which can't send headers: the key comes in the link
    return header or query

@app.get("/phone/api/files")
def laptop_files(x_mind_key: str = Header("")):
    # The newest files in your usual folders
    check(x_mind_key)
    return {"files": [dict(entry(path, os.path.basename(path)), where=os.path.relpath(os.path.dirname(path), HOME).replace(os.sep, " › "))
                      for when, size, path, folder in recent_files() if entry(path, os.path.basename(path))]}

@app.get("/phone/api/browse")
def browse(rel: str = "", x_mind_key: str = Header("")):
    # One folder's contents: folders first, then files (newest first)
    check(x_mind_key)
    folder = home_path(rel)
    if not os.path.isdir(folder):
        raise HTTPException(404, "That folder isn't there.")
    at_home = os.path.realpath(folder) == os.path.realpath(HOME)
    items = []
    try:
        names = os.listdir(folder)
    except OSError:
        raise HTTPException(403, "Windows doesn't allow opening that folder.")
    for name in names:
        if name.startswith((".", "~$", "desktop.ini")) or (at_home and name in HIDDEN_AT_HOME):
            continue
        item = entry(os.path.join(folder, name), name)
        if item:
            items.append(item)
    items.sort(key=lambda i: (not i["folder"], -i["when"] if not i["folder"] else 0, i["name"].lower()))
    return {"rel": "" if at_home else rel_of(folder), "name": "Your folders" if at_home else os.path.basename(folder), "items": items[:400]}


@app.get("/phone/api/search")
def search(q: str = "", x_mind_key: str = Header("")):
    # Any file or folder in your home folder whose name has these words (any order), newest first (instant: the index)
    check(x_mind_key)
    words = [w for w in q.lower().split() if w]
    if not words:
        raise HTTPException(400, "Type part of a name.")
    hits = [f for f in fresh_index() if all(w in f[0] for w in words)]
    if not hits:  # (maybe it's brand new: look again with a list made just now, ~4 s)
        hits = [f for f in fresh_index(wait=True, older_than=5) if all(w in f[0] for w in words)]
    hits.sort(key=lambda f: -f[3])
    items = []
    for name, path, size, when, folder in hits[:80]:
        item = entry(path, os.path.basename(path))
        if item:
            where = os.path.relpath(os.path.dirname(path), HOME)
            item["where"] = "Home" if where == "." else where.replace(os.sep, " › ")
            items.append(item)
    return {"items": items, "partial": False}

@app.get("/phone/api/file")
def laptop_file(rel: str, k: str = "", download: int = 0, x_mind_key: str = Header("")):
    # Any size: streamed, and videos can jump around (the phone asks for parts of the file)
    check(key_from(x_mind_key, k))
    path = home_path(rel)
    if not os.path.isfile(path):
        raise HTTPException(404, "That file isn't there any more.")
    if download:
        print("(Phone: took", os.path.basename(path), "from the laptop)")
    return FileResponse(path, filename=os.path.basename(path), content_disposition_type="attachment" if download else "inline")

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

# ---------- The Laptop tab: live status, one-tap buttons, clipboard both ways, files to the laptop ----------
@app.get("/phone/api/laptop")
def laptop(x_mind_key: str = Header("")):
    import pc
    import settings
    import audio
    check(x_mind_key)
    battery = psutil.sensors_battery()
    memory = psutil.virtual_memory()
    try:
        playing = audio.music_playing()
    except Exception:
        playing = False
    return {"battery": round(battery.percent) if battery else None, "charging": bool(battery and battery.power_plugged),
            "cpu": round(psutil.cpu_percent(None)),  # (since the last ask: no waiting)
            "ram_used": round((memory.total - memory.available) / 1024 ** 3, 1),
            "ram_total": round(memory.total / 1024 ** 3, 1), "front": pc.in_front(), "music": playing,
            "mind": state.status, "online": not state.muted, "locked": laptop_locked(),
            "screen_off": screen_is_off(), "stay_awake": str(settings.get("stay_awake")), "kept_awake": should_stay_awake()}

# One-tap buttons: the same actions M.I.N.D does by voice, done at once (no brain, no waiting)
screen = {"off_at": 0.0}

def screen_off():
    # Turns only the display off (power saving); the laptop keeps working. "Screen on", a key or the mouse wakes it
    screen["off_at"] = time.time()
    ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)  # broadcast: monitor power off
    return "Screen off. The laptop keeps working."

def screen_on():
    # A tiny mouse nudge (there and back) is what Windows needs to light the display again
    ctypes.windll.user32.mouse_event(0x0001, 1, 0, 0, 0)
    ctypes.windll.user32.mouse_event(0x0001, -1, 0, 0, 0)
    ctypes.windll.kernel32.SetThreadExecutionState(0x00000002)  # ES_DISPLAY_REQUIRED (once)
    screen["off_at"] = 0.0
    return "Screen on."

def screen_is_off():
    import alerts
    # Off since the button, and nobody has touched the laptop since (a key or the mouse turns it on)
    return bool(screen["off_at"]) and alerts.idle_seconds() >= time.time() - screen["off_at"] - 1

QUICK = {"play_pause": ("media_control", {"action": "play_pause"}), "next": ("media_control", {"action": "next"}),
         "previous": ("media_control", {"action": "previous"}), "volume_up": ("change_volume", {"action": "up"}),
         "volume_down": ("change_volume", {"action": "down"}), "mute": ("change_volume", {"action": "mute"}),
         "lock": ("lock_pc", {})}

class Quick(BaseModel):
    action: str

@app.post("/phone/api/do")
def do(quick: Quick, x_mind_key: str = Header("")):
    import tools
    check(x_mind_key)
    if quick.action == "screen_off":
        return {"said": screen_off()}
    if quick.action == "screen_on":
        return {"said": screen_on()}
    if quick.action == "screenshot":
        to_inbox("image", "Your screen", "screen.jpg", screenshot())
        return {"said": "Screenshot is in your inbox below."}
    if quick.action not in QUICK:
        raise HTTPException(400, "Unknown button.")
    name, args = QUICK[quick.action]
    result, worked = tools.run_tool(name, args)
    print(f"(Phone button: {quick.action})")
    return {"said": result}

class Clip(BaseModel):
    text: str

@app.get("/phone/api/clipboard")
def get_clipboard(x_mind_key: str = Header("")):
    import pc
    check(x_mind_key)
    return {"text": pc.clipboard_text()[:20000]}

@app.post("/phone/api/clipboard")
def put_clipboard(clip: Clip, x_mind_key: str = Header("")):
    import pc
    check(x_mind_key)
    if not pc.set_clipboard(clip.text[:20000]):
        raise HTTPException(500, "The laptop's clipboard was busy. Try again.")
    print("(Phone: put text on the laptop's clipboard)")
    return {"ok": True}

FROM_PHONE = os.path.join(os.path.expanduser("~"), "Downloads", "From M.I.N.D")

@app.post("/phone/api/upload")
async def upload(request: Request, x_mind_key: str = Header(""), x_name: str = Header("")):
    # A file or photo from the phone, saved in Downloads\From M.I.N.D (never overwrites: "name (2).jpg")
    import urllib.parse
    check(x_mind_key)
    data = await request.body()
    if not data or len(data) > FILE_LIMIT:
        raise HTTPException(400, "No file, or bigger than 100 MB.")
    name = os.path.basename(urllib.parse.unquote(x_name)).strip(". ") or "from phone"
    name = "".join(c for c in name if c not in '<>:"/|?*\\')[:120] or "from phone"  # (letters Windows won't allow)
    os.makedirs(FROM_PHONE, exist_ok=True)
    stem, ext = os.path.splitext(name)
    path, n = os.path.join(FROM_PHONE, name), 2
    while os.path.exists(path):
        path, n = os.path.join(FROM_PHONE, f"{stem} ({n}){ext}"), n + 1
    with open(path, "wb") as f:
        f.write(data)
    print("(Phone: sent", os.path.basename(path), "to the laptop)")
    index["at"], index["stale"] = 0, True  # (in Recent/search right away: the next ask waits for a rescan)
    return {"saved": os.path.basename(path)}

class Link(BaseModel):
    url: str

@app.post("/phone/api/open_link")
def open_link(link: Link, x_mind_key: str = Header("")):
    # A link shared from the phone opens in the laptop's Chrome (only web links)
    import tools
    check(x_mind_key)
    url = link.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "Only web links can be opened.")
    tools.open_page(url)
    print("(Phone: opened a shared link on the laptop)")
    return {"ok": True}

class Opened(BaseModel):
    name: str

@app.post("/phone/api/open_upload")
def open_upload(item: Opened, x_mind_key: str = Header("")):
    check(x_mind_key)
    path = os.path.join(FROM_PHONE, os.path.basename(item.name))
    if not os.path.isfile(path):
        raise HTTPException(404, "That file isn't there any more.")
    os.startfile(path)
    return {"ok": True}

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
    psutil.cpu_percent(None)  # (the first CPU reading is always 0: take it now)
    threading.Thread(target=fresh_index, daemon=True).start()  # (the file index, ready for the first search)
    open_door()
    port_free()  # (the phone door had this port while M.I.N.D was off: it lets go within ~2 s)
    server.run_in_background(app, PORT)  # (selector loop: keeps accepting after a dropped connection)

def port_free(seconds=20):
    import socket
    end = time.time() + seconds
    while time.time() < end:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", PORT))
                return True
            except OSError:
                time.sleep(0.5)
    return False

def open_door():
    # The phone door (phone_door.py) keeps running after M.I.N.D is turned off, so the phone app can turn it
    # back on. Started through a short-lived helper, so stopping M.I.N.D's process tree doesn't stop the door.
    import subprocess
    pythonw = os.path.join(BASE_DIR, "venv", "Scripts", "pythonw.exe")
    launcher = ("import subprocess, sys; subprocess.Popen([sys.executable, 'phone_door.py'], "
                "creationflags=0x08000000 | 0x00000008)")
    try:
        subprocess.Popen([pythonw, "-c", launcher], cwd=BASE_DIR, creationflags=0x08000000)
    except OSError as e:
        print("Couldn't start the phone door:", e)
