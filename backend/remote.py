# The phone as a remote for the laptop (2026-11-06): touchpad, air mouse, keyboard, media and slide buttons.
# The phone app's Remote tab keeps ONE websocket open (/phone/api/remote) and sends tiny messages many times a
# second; this file turns them into real mouse and keyboard input on the laptop (Windows SendInput).
#   {"m": [dx, dy]}            move the pointer by that much (already sped up on the phone)
#   {"b": "left|right|middle", "a": "click|double|down|up"}
#   {"w": [dy, dx]}            scroll (wheel steps; 120 = one notch, smaller = smooth)
#   {"k": "ctrl+c"}            keys, like pc.press_keys
#   {"t": "hello"}             type text
#   {"q": "play_pause"}        a quick action from phone.QUICK (media, volume)
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
ULONG_PTR = ctypes.c_size_t

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

class _INPUT(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT)]

MOVE, WHEEL, HWHEEL = 0x0001, 0x0800, 0x1000
BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
held = set()  # buttons held down (a drag): let go if the phone disconnects

def mouse(flags, dx=0, dy=0, data=0):
    event = INPUT(type=0)  # 0 = mouse
    event.u.mi = MOUSEINPUT(int(dx), int(dy), ctypes.c_ulong(int(data) & 0xFFFFFFFF).value, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))

def move(dx, dy):
    dx, dy = max(-400, min(400, dx)), max(-400, min(400, dy))  # (one message never jumps across the screen)
    if dx or dy:
        mouse(MOVE, dx, dy)

def button(which="left", action="click"):
    down, up = BUTTONS.get(which, BUTTONS["left"])
    if action in ("click", "double"):
        for _ in range(2 if action == "double" else 1):
            mouse(down)
            mouse(up)
    elif action == "down":
        held.add(which)
        mouse(down)
    elif action == "up":
        held.discard(which)
        mouse(up)

def wheel(dy=0, dx=0):
    # Phone: finger down = page down. Windows: negative wheel = down.
    if dy:
        mouse(WHEEL, data=-max(-1200, min(1200, dy)))
    if dx:
        mouse(HWHEEL, data=max(-1200, min(1200, dx)))

def let_go():
    for which in list(held):
        button(which, "up")

def handle(message):
    # One message from the phone. Returns a short note when something couldn't be done, else "".
    import pc
    if "m" in message:
        move(*message["m"][:2])
    elif "b" in message:
        button(message["b"], message.get("a", "click"))
    elif "w" in message:
        wheel(*message["w"][:2])
    elif "k" in message:
        said = pc.press_keys(str(message["k"])[:40])
        return "" if said.startswith("Pressed") else said
    elif "t" in message:
        pc.type_text(str(message["t"])[:2000])
    elif "q" in message:
        import phone
        import tools
        if message["q"] in phone.QUICK:
            name, args = phone.QUICK[message["q"]]
            tools.run_tool(name, args)
    return ""
