# Guard mode: "Mind, guard my laptop" (or the switch in the phone app) before walking away.
# If anyone then touches the REAL keyboard, mouse or touchpad: a webcam photo, the laptop locks, and the phone gets
# an alert with the photo (in the Mind tab's inbox). Unlocking with the Windows PIN (only the owner knows it)
# switches the guard off again.
# How touches are seen: Windows' low-level keyboard/mouse hooks. Input that programs make (M.I.N.D's own typing,
# the phone app's taps and remote) is marked "injected" by Windows and never counts, only real hands do.
# The photo is taken by a SEPARATE little program (python guard.py snap <file>), never inside M.I.N.D.
import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
GRACE = {"voice": 12, "phone": 3}   # seconds after arming before touches count (time to walk away)
MOVE_PX = 25                        # the mouse must really move this far (a tiny jiggle isn't a person)
CAMERA = "USB2.0 VGA UVC WebCam"    # found with Get-PnpDevice; another laptop: the first camera is tried

guard = {"armed": False, "since": 0.0, "caught": 0, "thread": None, "tid": 0, "trip": None}
user32 = ctypes.windll.user32

def is_locked():
    import psutil
    return any((p.info["name"] or "").lower() == "logonui.exe" for p in psutil.process_iter(["name"]))

def status():
    if not guard["armed"]:
        return "off"
    return "caught someone" if guard["caught"] else "on"

def arm(how="voice"):
    if guard["armed"]:
        return "Guard is already on."
    guard.update(armed=True, since=time.time() + GRACE.get(how, 12), caught=0)
    threading.Thread(target=watch, daemon=True, name="guard").start()
    print(f"(Guard on, from the {how})")
    return (f"Guard is on. In {GRACE.get(how, 12)} seconds, if anyone touches the laptop I'll take a photo, lock it "
            "and tell your phone. Unlocking with your PIN turns me off.")

def disarm(why="phone"):
    if not guard["armed"]:
        return "Guard was already off."
    guard["armed"] = False
    if guard["tid"]:
        user32.PostThreadMessageW(guard["tid"], 0x0012, 0, 0)  # WM_QUIT: the hook thread ends
    print(f"(Guard off: {why})")
    return "Guard is off."

# ---------- Watching for real hands ----------
class KBD(ctypes.Structure):
    _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

class MOUSE(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long), ("data", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

HOOK = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOK, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p

def watch():
    # The hooks live in this thread (they need its message loop); a real touch sets guard["trip"]
    guard["tid"] = ctypes.windll.kernel32.GetCurrentThreadId()
    start = {"x": None, "y": None}

    def touched(what):
        if guard["armed"] and time.time() >= guard["since"] and not guard["trip"]:
            guard["trip"] = what
            threading.Thread(target=caught, args=(what,), daemon=True).start()

    def on_key(code, wparam, lparam):
        if code == 0:
            key = ctypes.cast(lparam, ctypes.POINTER(KBD)).contents
            if not key.flags & 0x10:  # LLKHF_INJECTED: made by a program, not a finger
                touched("keyboard")
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def on_mouse(code, wparam, lparam):
        if code == 0:
            m = ctypes.cast(lparam, ctypes.POINTER(MOUSE)).contents
            if not m.flags & 0x01:  # LLMHF_INJECTED
                if wparam != 0x0200:  # clicks / wheel: a person for sure
                    touched("mouse")
                elif start["x"] is None or time.time() < guard["since"]:
                    start.update(x=m.x, y=m.y)
                elif abs(m.x - start["x"]) + abs(m.y - start["y"]) > MOVE_PX:
                    touched("mouse")
        return user32.CallNextHookEx(None, code, wparam, lparam)

    keep = (HOOK(on_key), HOOK(on_mouse))  # (kept alive while hooked)
    hooks = [user32.SetWindowsHookExW(13, keep[0], None, 0), user32.SetWindowsHookExW(14, keep[1], None, 0)]
    message = wintypes.MSG()
    try:
        while guard["armed"] and user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            pass
    finally:
        for hook in hooks:
            if hook:
                user32.UnhookWindowsHookEx(ctypes.c_void_p(hook))
        guard["tid"] = 0

def caught(what):
    # The photo starts at once; the laptop locks 1.5 s later (the camera needs ~3 s, and the person is still
    # there looking at the lock screen); then the phone is told
    print(f"(Guard: someone used the {what}!)")
    shot = {}
    camera = threading.Thread(target=lambda: shot.update(photo=snap_photo()), daemon=True)
    camera.start()
    time.sleep(1.5)
    user32.LockWorkStation()
    camera.join(10)
    photo = shot.get("photo")
    guard["caught"] += 1
    when = time.strftime("%I:%M %p").lstrip("0")
    try:
        import phone
        line = f"Someone used your laptop's {what} at {when}. I locked it."
        if photo:
            phone.to_inbox("image", line + " This is who was there.", "guard.jpg", photo)
        else:
            phone.to_inbox("text", line + " (The webcam didn't give a photo.)")
        phone.notify(line + (" Photo in the M.I.N.D app." if photo else ""), "🛡 Laptop guard", always=True)
    except Exception as e:
        print("(Guard couldn't tell the phone:", str(e)[:100] + ")")
    threading.Thread(target=wait_for_owner, daemon=True).start()

def wait_for_owner():
    # Locked by the guard; the owner unlocking (with the PIN) = welcome back, guard off
    time.sleep(3)
    while guard["armed"] and is_locked():
        time.sleep(1)
    if guard["armed"]:
        disarm("unlocked with the PIN")
    guard["trip"] = None

def snap_photo():
    # The separate helper takes the photo (max 8 s); bytes of a JPEG, or None
    out = os.path.join(os.environ.get("TEMP", HERE), f"mind_guard_{int(time.time())}.jpg")
    python = os.path.join(HERE, "venv", "Scripts", "python.exe")
    try:
        subprocess.run([python if os.path.exists(python) else sys.executable, os.path.abspath(__file__), "snap", out],
                       timeout=8, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        with open(out, "rb") as f:
            return f.read()
    except Exception:
        return None
    finally:
        try:
            os.remove(out)
        except OSError:
            pass

def cameras():
    found = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-PnpDevice -Class Camera,Image -Status OK | Select-Object -ExpandProperty FriendlyName"],
                           capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout.split("\n")
    return [CAMERA] + [c.strip() for c in found if c.strip() and c.strip() != CAMERA]

def snap(out):
    # (runs in the helper program) skip the first frames: the camera needs a moment for its light level
    import av
    for name in cameras():
        try:
            camera = av.open(f"video={name}", format="dshow", options={"video_size": "640x480"})
        except Exception:
            continue
        try:
            for n, frame in enumerate(camera.decode(video=0)):
                if n >= 15:
                    frame.to_image().save(out, quality=85)
                    return
        finally:
            camera.close()

def guard_laptop(on=True):
    # The brain's tool. Turning it OFF by voice isn't allowed: whoever is at the laptop could just say it.
    if on in (False, "false", "off", "no"):
        if guard["armed"]:
            return ("Not turned off by voice (anyone at the laptop could say it). Tell them: turn it off in the phone "
                    "app's Laptop tab, or unlock the laptop with the PIN.")
        return "Guard is already off."
    return arm("voice")

if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "snap":
    snap(sys.argv[2])
