# A tiny text box beside the floating reactor: click the reactor, type, press Enter (Shift+Enter = a new line;
# the box grows up to MAX_LINES lines).
# Esc, a second click on the reactor or clicking away closes it.
# Made with tkinter (comes with Python). The box is built ONCE, in its own thread, and kept hidden, so a click
# only has to show it (instant). Making it fresh each time took ~0.3 s on top of the double-click wait.
import ctypes
import queue
import threading
import time

import state

BORDER = "#28c8ff"      # same blue as the reactor
BACKGROUND = "#0b1620"
TEXT = "#d8f6ff"
HINT = "#5f8796"
HINT_TEXT = "Type to Mind…"
ICON = "#7fdcff"
CLOSE_AFTER = 30        # seconds: closes by itself if nothing was typed
MAX_LINES = 6           # the box grows this tall at most (then it scrolls)

box = {"open": False, "close": False, "typing": False}
asks = queue.Queue()    # ("show", where) / ("close", None) for the box's own thread
worker = None

def is_open():
    return box["open"]

def close():
    box["close"] = True
    asks.put(("close", None))

def show(where):
    # where(): (x, y, width, height) in screen pixels, or None if the reactor is gone.
    # Asked again and again, so the box follows the reactor when you drag it.
    if box["open"]:
        return
    box.update(open=True, close=False, typing=False)
    warm()
    asks.put(("show", where))

def warm():
    # Build the (hidden) box now, so the first click is instant too
    global worker
    if worker is None or not worker.is_alive():
        worker = threading.Thread(target=run, daemon=True)
        worker.start()

def rounded(hwnd, width, height):
    # Soft round corners and a glowing blue edge (Windows 11 draws them smooth);
    # on Windows 10 the corners are cut round instead
    dwm = ctypes.windll.dwmapi
    corner = ctypes.c_int(2)  # DWMWCP_ROUND
    blue = ctypes.c_uint(0x00FFC828)  # #28c8ff as Windows wants it (blue-green-red)
    if dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), 4) != 0:
        region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, 14, 14)
        ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
    dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(blue), 4)  # border colour

def run():
    try:
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # same pixels as the reactor
    except Exception:
        pass
    import tkinter as tk
    import tkinter.font as tkfont
    root = tk.Tk()
    root.withdraw()  # hidden until a click
    root.overrideredirect(True)  # no title bar
    root.attributes("-topmost", True)
    root.configure(bg=BACKGROUND)
    # [ ◈  Type to Mind…              ↵ ]
    tk.Label(root, text="◈", bg=BACKGROUND, fg=ICON, font=("Segoe UI Symbol", 11)).pack(side="left", padx=(10, 4))
    tk.Label(root, text="↵", bg=BACKGROUND, fg=HINT, font=("Segoe UI Symbol", 11)).pack(side="right", padx=(4, 10))
    font = tkfont.Font(family="Bahnschrift", size=11)
    entry = tk.Text(root, bg=BACKGROUND, fg=HINT, insertbackground=BORDER, relief="flat", font=font, height=1,
                    wrap="word", borderwidth=0, highlightthickness=0, undo=True)
    entry.pack(side="left", fill="x", expand=True)
    now = {"where": None, "place": [], "one_line": 0, "opened": 0.0, "had_focus": False}

    def frame():
        return int(root.wm_frame(), 16)

    def put(place):
        root.geometry("{2}x{3}+{0}+{1}".format(*place))

    def open_box(where):
        place = list(where() or [])
        if not place:
            box.update(open=False)
            return
        now.update(where=where, place=place, one_line=place[3], opened=time.time(), had_focus=False)
        entry.config(height=1, fg=HINT)
        entry.delete("1.0", "end")
        entry.insert("1.0", HINT_TEXT)
        entry.mark_set("insert", "1.0")
        put(place)
        root.deiconify()
        root.lift()
        root.update_idletasks()
        rounded(frame(), place[2], place[3])
        take_focus()

    def hide_box():
        root.withdraw()
        box.update(open=False, typing=False, close=False)
        now["where"] = None

    def finish(event=None):
        box["close"] = True

    def key(event):
        if not box["typing"] and event.keysym not in ("Return", "Escape"):
            box["typing"] = True
            entry.delete("1.0", "end")  # the grey hint goes away
            entry.config(fg=TEXT)
        root.after(1, grow)

    def lines():
        try:
            return max(1, entry.count("1.0", "end", "displaylines")[0])
        except Exception:
            return 1

    def grow():
        # Taller with each line (up to MAX_LINES), growing upwards so it stays beside the reactor
        place = now["place"]
        if not place:
            return
        shown = min(lines(), MAX_LINES)
        entry.config(height=shown)
        height = now["one_line"] + (shown - 1) * font.metrics("linespace")
        if height != place[3]:
            place[1] -= height - place[3]
            place[3] = height
            put(place)
            rounded(frame(), place[2], place[3])
        entry.see("insert")

    def new_line(event=None):
        if not box["typing"]:  # (the grey hint goes away first)
            box["typing"] = True
            entry.delete("1.0", "end")
            entry.config(fg=TEXT)
        entry.insert("insert", "\n")
        root.after(1, grow)
        return "break"

    def send(event=None):
        text = entry.get("1.0", "end-1c").strip()
        if box["typing"] and text:
            state.type_command(text)  # handled like a command typed in the HUD
        finish()
        return "break"  # (Enter sends; it doesn't add a line)

    def focus_in(event=None):
        now["had_focus"] = True

    def focus_out(event=None):
        if now["had_focus"]:
            finish()  # clicked somewhere else

    def take_focus():
        take_keyboard(frame())
        entry.focus_force()
        entry.mark_set("insert", "1.0")

    def delete_word(event=None):
        # Ctrl+Backspace deletes the word before the cursor (like everywhere else in Windows)
        text = entry.get("insert linestart", "insert")
        word = len(text) - len(text.rstrip()) + (len(text.rstrip().split(" ")[-1]) if text.strip() else 0)
        entry.delete(f"insert-{max(word, 1 if text else 0)}c", "insert")
        root.after(1, grow)
        return "break"  # stop Tk from also typing a strange character

    def tick():
        # Every 10 ms: new asks from the reactor; while open, follow the reactor and close when it's time
        try:
            while True:
                ask, where = asks.get_nowait()
                if ask == "show":
                    open_box(where)
                elif ask == "close" and now["where"]:
                    hide_box()
        except queue.Empty:
            pass
        if now["where"]:
            spot = now["where"]()
            place = now["place"]
            if (not spot or box["close"]
                    or (not box["typing"] and time.time() - now["opened"] > CLOSE_AFTER)):
                hide_box()
            elif list(spot[:3]) != [place[0], place[1] + place[3] - now["one_line"], place[2]]:
                # the reactor was dragged: follow it
                place[:] = [spot[0], spot[1] - (place[3] - now["one_line"]), spot[2], place[3]]
                put(place)
        root.after(10, tick)

    entry.bind("<KeyPress>", key)
    entry.bind("<Control-BackSpace>", delete_word)
    entry.bind("<Return>", send)
    entry.bind("<Shift-Return>", new_line)
    entry.bind("<KeyRelease>", lambda event: grow())  # (pasted or wrapped text grows it too)
    entry.bind("<Escape>", finish)
    entry.bind("<FocusIn>", focus_in)
    entry.bind("<FocusOut>", focus_out)
    root.after(20, tick)
    try:
        root.mainloop()  # (runs as long as M.I.N.D; Tk objects stay in this one thread)
    except Exception as e:
        print("Type box problem:", e)
    box.update(open=False, typing=False)

def take_keyboard(hwnd):
    # Windows only lets the app you're using pick the window in front. Joining its input for a
    # moment lets the box take the keyboard. (The Alt-key trick ate the first letter you typed.)
    import win32gui, win32process, win32api
    front = win32gui.GetForegroundWindow()
    theirs = win32process.GetWindowThreadProcessId(front)[0] if front else 0
    mine = win32api.GetCurrentThreadId()
    user32 = ctypes.windll.user32
    if theirs and theirs != mine:
        user32.AttachThreadInput(mine, theirs, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if theirs and theirs != mine:
            user32.AttachThreadInput(mine, theirs, False)
