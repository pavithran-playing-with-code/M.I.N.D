# A tiny text box beside the floating reactor: click the reactor, type, press Enter.
# (M.I.N.D listens at the same time, so you can talk or type.) Esc or clicking away closes it.
# Made with tkinter (comes with Python), in its own thread.
import ctypes
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

box = {"open": False, "close": False, "typing": False}

def typing():
    # Has a key been pressed in the box? (then M.I.N.D stops listening: the keys aren't speech)
    return box["open"] and box["typing"]

def is_open():
    return box["open"]

def close():
    box["close"] = True

def show(where):
    # where(): (x, y, width, height) in screen pixels, or None if the reactor is gone.
    # Asked again and again, so the box follows the reactor when you drag it.
    if box["open"]:
        return
    box.update(open=True, close=False, typing=False)
    threading.Thread(target=run, args=(where,), daemon=True).start()

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

def run(where):
    try:
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # same pixels as the reactor
    except Exception:
        pass
    import tkinter as tk
    place = list(where() or [])
    if not place:
        box.update(open=False)
        return
    root = tk.Tk()
    try:
        root.overrideredirect(True)  # no title bar
        root.attributes("-topmost", True)
        root.configure(bg=BACKGROUND)
        root.geometry("{2}x{3}+{0}+{1}".format(*place))
        # [ ◈  Type to Mind…              ↵ ]
        tk.Label(root, text="◈", bg=BACKGROUND, fg=ICON, font=("Segoe UI Symbol", 11)).pack(side="left", padx=(10, 4))
        tk.Label(root, text="↵", bg=BACKGROUND, fg=HINT, font=("Segoe UI Symbol", 11)).pack(side="right", padx=(4, 10))
        entry = tk.Entry(root, bg=BACKGROUND, fg=HINT, insertbackground=BORDER, relief="flat",
                         font=("Bahnschrift", 11), borderwidth=0, highlightthickness=0)
        entry.pack(side="left", fill="both", expand=True)
        entry.insert(0, HINT_TEXT)
        root.update_idletasks()
        rounded(int(root.wm_frame(), 16), place[2], place[3])
        opened = time.time()
        had_focus = [False]

        def finish(event=None):
            box["close"] = True

        def key(event):
            if not box["typing"] and event.keysym not in ("Return", "Escape"):
                box["typing"] = True
                entry.delete(0, "end")  # the grey hint goes away
                entry.config(fg=TEXT)

        def send(event=None):
            text = entry.get().strip()
            if box["typing"] and text:
                state.type_command(text)  # handled like a command typed in the HUD
            finish()

        def focus_in(event=None):
            had_focus[0] = True

        def focus_out(event=None):
            if had_focus[0]:
                finish()  # clicked somewhere else

        def take_focus():
            take_keyboard(int(root.wm_frame(), 16))
            entry.focus_force()
            entry.icursor(0)

        def watch():
            now = where()
            if not now or box["close"] or (not box["typing"] and time.time() - opened > CLOSE_AFTER):
                root.quit()
                return
            if list(now) != place:  # the reactor was dragged: follow it
                place[:] = now
                root.geometry("{2}x{3}+{0}+{1}".format(*now))
            root.after(50, watch)

        def delete_word(event=None):
            # Ctrl+Backspace deletes the word before the cursor (like everywhere else in Windows)
            end = entry.index("insert")
            text = entry.get()[:end]
            start = len(text.rstrip()) - len(text.rstrip().split(" ")[-1]) if text.strip() else 0
            entry.delete(start, end)
            return "break"  # stop Tk from also typing a strange character

        entry.bind("<KeyPress>", key)
        entry.bind("<Control-BackSpace>", delete_word)
        entry.bind("<Return>", send)
        entry.bind("<Escape>", finish)
        entry.bind("<FocusIn>", focus_in)
        entry.bind("<FocusOut>", focus_out)
        root.after(30, take_focus)
        root.after(150, watch)
        root.mainloop()
    except Exception as e:
        print("Type box problem:", e)
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        # Tk must be cleaned up in THIS thread (else "Tcl_AsyncDelete: wrong thread" crashes M.I.N.D)
        root = entry = place = finish = key = send = focus_in = focus_out = take_focus = watch = None
        import gc
        gc.collect()
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
