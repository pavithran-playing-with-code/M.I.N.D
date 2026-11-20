# Floating window: a glowing arc reactor that stays on top of everything, with the chat
# floating beside it (no title bar, no background). Every frame is drawn with Pillow and
# shown in a "layered" Windows window, so each pixel can be see-through.
# Colors: blue = waiting / speaking, gold = listening / thinking, red = offline (mic off).
import ctypes
import math
import queue
import threading
import time
from ctypes import wintypes

import win32api
import win32con
import win32gui
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import state

TITLE = "M.I.N.D mini"  # pc.MIND_WINDOWS keeps close/window tools away from it
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
REACTOR = 72        # reactor size in pixels (at 100% screen scale)
TEXT_WIDTH = 230    # chat text beside the reactor
GAP = 8
HEIGHT = 92
MARGIN = 14         # distance from the screen edge
SHOW_SECONDS = 4    # the chat fades away this long after M.I.N.D goes quiet (longer for longer messages)
REPLY_LINES = 7     # a long reply shows this many lines next to the reactor (the text area grows)
NUDGE = 60      # "move it a little up", in pixels ("a lot" = 4 times this)

BLUE = (40, 200, 255)
GOLD = (255, 184, 56)
AMBER = (255, 150, 40)
# status: (color, brightness, spin speed in degrees per second)
LOOKS = {
    "waiting":   (BLUE, 0.6, 14),
    "starting":  (BLUE, 0.6, 14),
    "listening": (GOLD, 1.0, 40),
    "thinking":  (AMBER, 0.95, 170),
    "speaking":  (BLUE, 1.0, 60),
    "muted":     ((120, 130, 140), 0.22, 0),  # offline: the light is off
}

FONT_DIR = r"C:\Windows\Fonts"

def font(size, tamil=False):
    try:
        name = "Nirmala.ttc" if tamil else "bahnschrift.ttf"
        return ImageFont.truetype(f"{FONT_DIR}\\{name}", size)
    except OSError:
        return ImageFont.load_default(size)

def has_tamil(text):
    return any("\u0B80" <= ch <= "\u0BFF" for ch in text)

def wrap(text, fnt, width, max_lines):
    # Split text into lines that fit the width; "..." if it's too long
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if fnt.getlength(test) <= width or not line:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and fnt.getlength(lines[-1] + "…") > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines

def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Painter:
    # Draws one frame of the floating window (reactor + chat) as an RGBA image
    def __init__(self, scale=1.0, mirrored=False, size=1.0):
        self.s = scale
        self.size = size  # how big you made the reactor (the chat text stays the same size)
        self.mirrored = mirrored  # right-side corners: reactor at the edge, chat on its left
        self.above = False        # reactor down at the taskbar: the chat goes ABOVE it, centred (set each frame)
        self.layer_above = False  # (the text layer was made for that layout)
        self.text_shift = 0       # above: how far the text slides sideways to stay on screen
        self.spot_in_picture = (0, 0)  # where the reactor sits inside the last picture
        self.r = int(REACTOR * scale * size)
        self.w = self.r + int((GAP + TEXT_WIDTH) * scale)
        self.h = max(int(HEIGHT * scale), self.r + int(20 * scale))
        self.color = BLUE
        self.bright = 0.6
        self.angle = 0.0
        self.level = 0.0
        self.last = time.time()
        self.text_key = None
        self.text_layer = None
        self.text_alpha = 0.0
        self.hide_at = time.time() + SHOW_SECONDS
        self.seen_id = 0
        self.hover = None      # mouse resting on the reactor: the quick controls' values (volume, brightness...)
        self.dial = None       # where the controls' arcs and buttons are in the last picture (for the mouse)
        self.dial_up = True    # the arcs open upward (reactor low on the screen) or downward
        self.dial_alpha = 0.0
        self.chat_key = None   # the last chat shown (coming back from the controls doesn't pop it up again)
        self.chips = []  # [(action, (left, top, right, bottom))] buttons in window pixels (Copy / Replace)
        self.chip_spots = []  # the same, inside the text layer (moved into place each frame)
        # Soft glow behind the reactor (made once, tinted every frame)
        glow = Image.new("L", (self.r, self.r), 0)
        ImageDraw.Draw(glow).ellipse([self.r * 0.22] * 2 + [self.r * 0.78] * 2, fill=255)
        self.glow = glow.filter(ImageFilter.GaussianBlur(self.r * 0.12))

    def reactor(self, now, pulse):
        r2 = self.r * 2  # drawn at double size, then shrunk for smooth edges
        c = r2 / 2
        img = Image.new("RGBA", (r2, r2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        col = self.color
        b = self.bright
        s2 = self.s * self.size * 2

        def rgba(alpha, color=col):
            return color + (int(255 * max(0, min(1, alpha))),)

        def ring(radius, width, alpha):
            d.ellipse([c - radius, c - radius, c + radius, c + radius], outline=rgba(alpha), width=max(1, int(width)))

        # Outer ticks, turning slowly
        for i in range(48):
            a = math.radians(i * 7.5 + self.angle * 0.3)
            long = i % 4 == 0
            r_out, r_in = c * 0.97, c * (0.88 if long else 0.92)
            d.line([(c + r_in * math.cos(a), c + r_in * math.sin(a)),
                    (c + r_out * math.cos(a), c + r_out * math.sin(a))],
                   fill=rgba(b * (0.7 if long else 0.4)), width=max(1, int(1.2 * s2)))
        # Three arcs, turning with the state's speed
        rad = c * 0.82
        for i in range(3):
            start = self.angle + i * 120
            d.arc([c - rad, c - rad, c + rad, c + rad], start, start + 70, fill=rgba(b), width=max(1, int(2.5 * s2)))
        ring(c * 0.74, 1 * s2, b * 0.35)
        # The arc reactor's ring of 10 coils, turning the other way
        r_in, r_out = c * 0.46, c * 0.66
        for i in range(10):
            a0 = math.radians(-self.angle * 0.6 + i * 36)
            a1 = a0 + math.radians(26)
            points = [(c + r_in * math.cos(a0), c + r_in * math.sin(a0)),
                      (c + r_out * math.cos(a0 - 0.03), c + r_out * math.sin(a0 - 0.03)),
                      (c + r_out * math.cos(a1 + 0.03), c + r_out * math.sin(a1 + 0.03)),
                      (c + r_in * math.cos(a1), c + r_in * math.sin(a1))]
            d.polygon(points, fill=rgba(b * (0.25 + 0.35 * pulse)), outline=rgba(b * 0.9))
        ring(c * 0.42, 1.5 * s2, b * 0.8)
        # Glowing core: grows with the voice / mic
        core = c * (0.22 + 0.1 * pulse)
        d.ellipse([c - core, c - core, c + core, c + core], fill=rgba(b * 0.85))
        inner = core * 0.6
        d.ellipse([c - inner, c - inner, c + inner, c + inner], fill=rgba(min(1, b + 0.2), mix(col, (255, 255, 255), 0.7)))
        img = img.resize((self.r, self.r), Image.LANCZOS)

        # Glow underneath
        glow_alpha = (0.35 + 0.45 * pulse) * b
        tint = Image.new("RGBA", (self.r, self.r), col + (0,))
        tint.putalpha(self.glow.point(lambda v: int(v * glow_alpha)))
        return Image.alpha_composite(tint, img)

    def make_text(self, you, reply):
        # The chat lines with a dark shadow, so they're readable on any background
        width = int(TEXT_WIDTH * self.s)
        f_you = font(int(11 * self.s), has_tamil(you))
        f_reply = font(int(14 * self.s), has_tamil(reply))
        rows = [(line, f_you, (175, 205, 225)) for line in wrap(f"You: {you}", f_you, width, 1)] if you else []
        rows += [(line, f_reply, (230, 248, 255)) for line in wrap(reply, f_reply, width, REPLY_LINES)] if reply else []
        heights = [f.getbbox("Ag")[3] + int(3 * self.s) for _, f, _ in rows]
        tall = max(self.h, sum(heights) + int(20 * self.s))  # (a long message: the text area grows, the reactor stays)
        layer = Image.new("RGBA", (width + int(16 * self.s), tall), (0, 0, 0, 0))
        if not rows:
            return layer
        y = (tall - sum(heights)) // 2
        pad = int(6 * self.s)
        shadow = Image.new("L", layer.size, 0)
        sd = ImageDraw.Draw(shadow)
        td = ImageDraw.Draw(layer)
        for (line, f, color), h in zip(rows, heights):
            if self.above:
                x = (layer.width - int(f.getlength(line))) // 2  # above the reactor: centred
            else:
                x = pad if not self.mirrored else layer.width - pad - int(f.getlength(line))
            sd.text((x, y), line, font=f, fill=255)
            td.text((x, y), line, font=f, fill=color + (255,))
            y += h
        # Shadow: the text blurred and darkened, under the text
        shadow = shadow.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(3 * self.s))
        dark = Image.new("RGBA", layer.size, (0, 8, 16, 0))
        dark.putalpha(shadow.point(lambda v: min(255, v * 2)))
        return Image.alpha_composite(dark, layer)

    def make_offer(self, offer):
        # A fix (grammar) with Copy / Replace buttons, so you can use it without opening the HUD
        width = int(TEXT_WIDTH * self.s)
        f_label = font(int(10 * self.s))
        f_text = font(int(12 * self.s), has_tamil(offer["text"]))
        f_chip = font(int(11 * self.s))
        lines = wrap(offer["text"], f_text, width, 3)
        layer = Image.new("RGBA", (width + int(16 * self.s), self.h), (0, 0, 0, 0))
        td = ImageDraw.Draw(layer)
        line_h = f_text.getbbox("Ag")[3] + int(2 * self.s)
        chip_h = int(18 * self.s)
        label_h = f_label.getbbox("Ag")[3] + int(2 * self.s)
        total = label_h + line_h * len(lines) + int(4 * self.s) + chip_h
        y = max(0, (self.h - total) // 2)
        pad = int(6 * self.s)
        # dark rounded card behind it all, so it's readable on any background
        td.rounded_rectangle([0, max(0, y - int(4 * self.s)), width + int(2 * self.s), min(self.h - 1, y + total + int(4 * self.s))],
                             radius=int(8 * self.s), fill=(4, 18, 28, 215), outline=(40, 200, 255, 140))
        td.text((pad, y), offer.get("done") or "Better version:", font=f_label, fill=(61, 255, 154, 255))
        y += label_h
        for line in lines:
            td.text((pad, y), line, font=f_text, fill=(230, 248, 255, 255))
            y += line_h
        y += int(4 * self.s)
        self.chip_spots = []
        if not offer.get("done"):
            x = pad
            for action, label in [("copy", "Copy")] + ([("replace", "Replace")] if offer.get("replace") else []):
                w = int(f_chip.getlength(label)) + int(16 * self.s)
                td.rounded_rectangle([x, y, x + w, y + chip_h], radius=int(6 * self.s),
                                     fill=(20, 70, 95, 255), outline=(40, 200, 255, 255))
                td.text((x + int(8 * self.s), y + int(3 * self.s)), label, font=f_chip, fill=(200, 240, 255, 255))
                self.chip_spots.append((action, (x, y, x + w, y + chip_h)))
                x += w + int(8 * self.s)
        return layer

    def frame_dial(self, now, pulse):
        return self.frame_lines(now, pulse)

    def frame_lines(self, now, pulse):
        # Simple quick controls (S1): a small dark pill above the reactor with two thin glowing sliders
        # (cyan = volume, gold = screen brightness), the number at the end, and a round mic button.
        # Drag / click / scroll along a line. Speaker icon = mute.
        v, s, r, up = self.hover, self.s, self.r, self.dial_up
        k = 2
        u = s * k
        import settings
        two_rows = v.get("bright") is not None and settings.on("reactor_controls_brightness")
        mic_shown = settings.on("reactor_controls_mic")
        pw, ph, gap = (210 if mic_shown else 176) * s, (62 if two_rows else 38) * s, 8 * s
        w, h = int(max(pw, r)), int(ph + gap + r)
        px, py = (w - pw) / 2, (0 if up else r + gap)
        rx, ry = (w - r) / 2, (ph + gap if up else 0)
        cyan, gold, grey, white = (40, 210, 255), (255, 196, 70), (120, 130, 140), (230, 246, 255)
        glow = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        g, d = ImageDraw.Draw(glow), ImageDraw.Draw(img)
        d.rounded_rectangle([px * k, py * k, (px + pw) * k - 1, (py + ph) * k - 1], radius=16 * u,
                            fill=(8, 18, 26, 220), outline=cyan + (45,), width=max(1, int(u)))
        f_num = font(int(11 * u))
        cells, buttons = [], []
        muted = v.get("muted")
        rows = [("volume", v.get("volume"), cyan)]
        if v.get("bright") is not None and settings.on("reactor_controls_brightness"):
            rows.append(("bright", v.get("bright"), gold))
        for row, (name, value, color) in enumerate(rows):
            col = grey if (name == "volume" and muted) else color
            y = (py + (19 + row * 24) * s) * k
            ix = (px + 16 * s) * k
            if name == "volume":
                self.speaker_icon(d, ix, y, u * 0.7, col, muted)
                buttons.append(("mute", ix / k, y / k, 11 * s))
            else:
                self.sun_icon(d, ix, y, u * 0.7, col)
            x0, x1 = (px + 34 * s) * k, (px + pw - (64 if mic_shown else 44) * s) * k
            d.line([(x0, y), (x1, y)], fill=col + (60,), width=max(1, int(3 * u)))
            if value is not None:
                xe = x0 + (x1 - x0) * value / 100
                if value > 0:
                    d.line([(x0, y), (xe, y)], fill=col + (255,), width=max(1, int(3 * u)))
                    g.line([(x0, y), (xe, y)], fill=col + (200,), width=max(1, int(6 * u)))
                d.ellipse([xe - 5 * u, y - 5 * u, xe + 5 * u, y + 5 * u], fill=white + (255,))
            text = "MUTE" if (name == "volume" and muted) else ("--" if value is None else str(value))
            d.text(((px + pw - (56 if mic_shown else 36) * s) * k, y - 7 * u), text, font=f_num if text != "MUTE" else font(int(9 * u)),
                   fill=((255, 110, 110) if text == "MUTE" else white) + (255,))
            cells.append((name, x0 / k - 6 * s, y / k - 10 * s, x1 / k + 6 * s, y / k + 10 * s, "across"))
        if not mic_shown:
            return self.finish_controls(img, glow, w, h, k, u, rx, ry, now, pulse, cells, buttons)
        # mic button (red + slash when off)
        on = v.get("mic", True)
        ring = cyan if on else (255, 90, 90)
        mx, my = (px + pw - 20 * s) * k, (py + ph / 2) * k
        d.ellipse([mx - 10 * u, my - 10 * u, mx + 10 * u, my + 10 * u], outline=ring + (255,), width=max(1, int(1.3 * u)))
        q = u * 0.8
        d.rounded_rectangle([mx - 2.4 * q, my - 5.5 * q, mx + 2.4 * q, my + 1.5 * q], radius=2.4 * q, fill=ring + (255,))
        d.arc([mx - 4.5 * q, my - 3 * q, mx + 4.5 * q, my + 4 * q], 0, 180, fill=ring + (255,), width=max(1, int(1.4 * q)))
        d.line([(mx, my + 4 * q), (mx, my + 6.5 * q)], fill=ring + (255,), width=max(1, int(1.4 * q)))
        if not on:
            d.line([(mx - 6 * q, my - 6 * q), (mx + 6 * q, my + 6 * q)], fill=(255, 90, 90, 255), width=max(1, int(1.6 * q)))
        buttons.append(("mic", mx / k, my / k, 12 * s))
        return self.finish_controls(img, glow, w, h, k, u, rx, ry, now, pulse, cells, buttons)

    def speaker_icon(self, d, x, y, u, col, muted):
        d.rectangle([x - 6 * u, y - 3 * u, x - 2 * u, y + 3 * u], fill=col + (255,))
        d.polygon([(x - 2 * u, y - 3 * u), (x + 3 * u, y - 7 * u), (x + 3 * u, y + 7 * u), (x - 2 * u, y + 3 * u)], fill=col + (255,))
        if muted:
            d.line([(x + 5 * u, y - 4 * u), (x + 11 * u, y + 4 * u)], fill=(255, 100, 100, 255), width=max(1, int(1.8 * u)))
        else:
            d.arc([x - u, y - 6 * u, x + 9 * u, y + 6 * u], -50, 50, fill=col + (255,), width=max(1, int(1.6 * u)))

    def sun_icon(self, d, x, y, u, col):
        d.ellipse([x - 4 * u, y - 4 * u, x + 4 * u, y + 4 * u], fill=col + (255,))
        for ray in range(8):
            a = math.radians(ray * 45)
            d.line([(x + 6 * u * math.cos(a), y + 6 * u * math.sin(a)), (x + 8.5 * u * math.cos(a), y + 8.5 * u * math.sin(a))],
                   fill=col + (255,), width=max(1, int(1.6 * u)))

    def finish_controls(self, img, glow, w, h, k, u, rx, ry, now, pulse, cells, buttons):
        glow = glow.filter(ImageFilter.GaussianBlur(4 * u))
        out = Image.alpha_composite(glow, img).resize((w, h), Image.LANCZOS)
        out.alpha_composite(self.reactor(now, max(0, min(1, pulse))), (int(rx), int(ry)))
        if self.dial_alpha < 0.999:
            out.putalpha(out.getchannel("A").point(lambda a: int(a * self.dial_alpha)))
        self.dial = {"cells": cells, "buttons": buttons}
        self.chips = []
        self.spot_in_picture = (int(rx), int(ry))
        return out, True

    def frame(self, snap):
        now = time.time()
        dt = min(0.2, now - self.last)
        self.last = now
        status = "muted" if snap.get("muted") or snap.get("status") == "call" else snap.get("status", "waiting")
        color, bright, speed = LOOKS.get(status, LOOKS["waiting"])
        k = min(1, dt * 5)  # smooth color changes
        self.color = mix(self.color, color, k)
        self.bright += (bright - self.bright) * k
        self.angle = (self.angle + speed * dt) % 360

        if status == "listening":
            self.level += (min(1, snap.get("level", 0) * 2.5) - self.level) * min(1, dt * 12)
            pulse = self.level
        elif status == "speaking":
            pulse = 0.55 + 0.3 * math.sin(now * 9) + 0.15 * math.sin(now * 23)
        elif status == "thinking":
            pulse = 0.45 + 0.2 * math.sin(now * 5)
        else:
            pulse = 0.25 + 0.12 * math.sin(now * 1.6)  # slow breathing

        # The chat: your last words and the reply to them
        messages = snap.get("messages", [])
        you = next((m for m in reversed(messages) if m["who"] == "you"), None)
        reply = next((m for m in reversed(messages) if m["who"] == "mind"), None)
        if reply and you and reply["id"] < you["id"]:
            reply = None  # that reply was for something earlier
        newest = max([m["id"] for m in (you, reply) if m] or [0])
        if newest > self.seen_id:
            self.seen_id = newest
            self.hide_at = now + SHOW_SECONDS
        if status in ("thinking", "speaking"):  # (not while just listening for a follow-up)
            self.hide_at = max(self.hide_at, now + SHOW_SECONDS)
        if self.hover is not None:
            # the controls take over (the chat waits; it doesn't pop up again afterwards)
            self.dial_alpha = min(1.0, self.dial_alpha + dt * 6)
            self.text_alpha = 0.0
            return self.frame_dial(now, pulse)
        self.dial_alpha, self.dial = 0.0, None
        offer = state.offer if state.offer and now < state.offer["until"] else None
        if offer:
            key = ("offer", offer["id"], offer.get("done"))
            self.hide_at = max(self.hide_at, offer["until"])
        else:
            key = (you and you["text"], reply and reply["text"])
            self.chip_spots = []
        if key != self.text_key or self.layer_above != self.above:
            if key != self.chat_key:
                self.chat_key = key
                words = len(str(key[1] or "").split())
                self.hide_at = max(self.hide_at, now + min(25, SHOW_SECONDS + words * 0.3))  # (time to read it)
            self.text_key, self.layer_above = key, self.above
            self.text_layer = self.make_offer(offer) if offer else self.make_text(key[0] or "", key[1] or "")
        if now - state.read_now < 1:
            words = len(str(key[1] or "").split())
            self.hide_at = max(self.hide_at, now + max(10, min(40, words * 0.5)))  # tapped: read it, not hear it
        target = 1.0 if now < self.hide_at and any(key) else 0.0
        self.text_alpha += (target - self.text_alpha) * min(1, dt * (6 if target else 2.5))
        if self.above:
            return self.frame_above(now, pulse, status)

        tall = max(self.h, self.text_layer.height) if self.text_alpha > 0.01 else self.h
        img = Image.new("RGBA", (self.w, tall), (0, 0, 0, 0))
        rx = self.w - self.r if self.mirrored else 0
        img.alpha_composite(self.reactor(now, max(0, min(1, pulse))), (rx, (tall - self.r) // 2))
        if self.text_alpha > 0.01:
            layer = self.text_layer.copy()
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * self.text_alpha)))
            slide = int((1 - self.text_alpha) * 10 * self.s)  # drifts out from the reactor
            gap = int(GAP * self.s)
            tx = (rx - gap - layer.width - slide + int(8 * self.s)) if self.mirrored else (self.r + gap + slide - int(8 * self.s))
            img.alpha_composite(layer, (max(0, tx), (tall - layer.height) // 2))
            self.chips = [(a, (l + max(0, tx), t + (tall - layer.height) // 2, r + max(0, tx), b + (tall - layer.height) // 2))
                          for a, (l, t, r, b) in self.chip_spots]
        else:
            self.chips = []
        self.spot_in_picture = (rx, (tall - self.r) // 2)  # where the reactor sits inside this picture
        busy = status in ("listening", "thinking", "speaking") or 0.01 < self.text_alpha < 0.99
        return img, busy

    def frame_above(self, now, pulse, status):
        # Reactor at the bottom of the picture, the chat stacked right above it (centred on it). The picture only
        # grows upward, so the reactor never moves. `text_shift` (set by the window code) slides the text sideways
        # when the reactor is near a screen edge, so the text stays on screen.
        gap = int(GAP * self.s)
        showing = self.text_alpha > 0.01
        layer = self.text_layer if showing else None
        width = max(self.r, layer.width) if layer else self.r
        text_h = (layer.height + gap) if layer else 0
        img = Image.new("RGBA", (width, text_h + self.r), (0, 0, 0, 0))
        rx = (width - self.r) // 2 - (self.text_shift if layer else 0)
        rx = max(0, min(width - self.r, rx))
        img.alpha_composite(self.reactor(now, max(0, min(1, pulse))), (rx, text_h))
        self.chips = []
        if layer:
            faded = layer.copy()
            faded.putalpha(faded.getchannel("A").point(lambda v: int(v * self.text_alpha)))
            slide = int((1 - self.text_alpha) * 10 * self.s)  # drifts up out of the reactor
            tx, ty = (width - layer.width) // 2, slide
            img.alpha_composite(faded, (tx, ty))
            self.chips = [(a, (l + tx, t + ty, r + tx, b + ty)) for a, (l, t, r, b) in self.chip_spots]
        self.spot_in_picture = (rx, text_h)
        busy = status in ("listening", "thinking", "speaking") or 0.01 < self.text_alpha < 0.99
        return img, busy


# ---------- The Windows window ----------
class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]

commands = queue.Queue()
thread = None

def reactor_place(p):
    # Top-left of the reactor itself on the screen (spot = the normal box: reactor + chat beside it)
    return spot["x"] + (p.w - p.r if p.mirrored else 0), spot["y"] + (p.h - p.r) // 2

def at_taskbar(reactor_top, size, monitor_info):
    # The reactor sits down in (or touching) the taskbar: its middle is below the usable screen's bottom edge
    # minus a quarter of it. Then the chat and the text box go above it, not beside it.
    work_bottom = monitor_info["Work"][3]
    return work_bottom < monitor_info["Monitor"][3] and reactor_top + size * 0.75 >= work_bottom

def corner_spot(corner, w, h, offset=(0, 0), scale=1.0, slack=0):
    # Top-left point of the window: a corner of the main screen (above the taskbar),
    # shifted by the nudges / where it was dropped. It may go anywhere on the screen, over the taskbar too.
    # slack = the empty space above/below the reactor inside its box: that part may go off the screen,
    # so the reactor itself can sit right down in the taskbar (it used to bounce back up).
    info = win32api.GetMonitorInfo(win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY))
    left, top, right, bottom = info["Work"]
    margin = int(MARGIN * scale)
    x = left + margin if "left" in corner else right - w - margin
    y = top + margin if "top" in corner else bottom - h - margin
    left, top, right, bottom = info["Monitor"]
    x = max(left, min(right - w, x + int(offset[0] * scale)))
    y = max(top - slack, min(bottom - h + slack, y + int(offset[1] * scale)))
    return x, y

SMALLEST, BIGGEST = 50, 200  # reactor size, percent
WHEEL_STEP = 10              # one notch of the mouse wheel over the reactor

def reactor_size():
    from memory import profile
    try:
        return max(SMALLEST, min(BIGGEST, int(profile.get("reactor_size", 100))))
    except (TypeError, ValueError):
        return 100

def set_size(percent):
    # Mouse wheel, Control Center or voice. Saved, so it's the same size after a restart.
    from memory import profile, save_profile
    percent = max(SMALLEST, min(BIGGEST, int(percent)))
    profile["reactor_size"] = percent
    save_profile()
    commands.put(("size", None))
    return percent

def on_wheel(hwnd, msg, wparam, lparam):
    notch = ctypes.c_short((wparam >> 16) & 0xFFFF).value  # (up = bigger, down = smaller)
    hit = dial_hit()
    if hit and hit[0] in ("volume", "bright"):  # the wheel over an arc moves it 5 at a time
        value = controls.get(hit[0])
        if value is not None:
            set_control(hit[0], value + (5 if notch > 0 else -5))
        return 0
    p = current.get("painter")
    if p:  # only the wheel over the reactor itself resizes it (not over its chat or controls)
        mx, my = cursor()
        left, top = reactor_place(p)
        if not (left <= mx <= left + p.r and top <= my <= top + p.r):
            return 0
    set_size(reactor_size() + (WHEEL_STEP if notch > 0 else -WHEEL_STEP))
    return 0

# ---------- Quick controls while the mouse rests on the reactor (volume, brightness, mute, mic, battery) ----------
HOVER_DELAY = 0.25   # seconds resting on the reactor before the controls show (Control Center can change it)

def hover_delay():
    import settings
    try:
        return float(settings.get("reactor_controls_delay"))
    except (TypeError, ValueError):
        return HOVER_DELAY
HOVER_LEAVE = 0.6    # seconds away before they go
workers = {"controls": False}
controls = {}        # the values shown (changed at once when you drag, then really set by the worker)
control_asks = queue.Queue()

def dial_value(cell, x, y):
    # The value (0-100) for a spot along a control row: left = 0, right = 100
    _, left, _, right, _, _ = cell
    margin = 6 * (current["painter"].s if current.get("painter") else 1)  # (rows reach a little past the line's ends)
    return round(max(0.0, min(1.0, (x - left - margin) / max(1.0, right - left - 2 * margin))) * 100)

def dial_hit(x=None, y=None):
    # What the mouse is on: ("volume" / "bright", value) on a cell, ("mute" / "mic", None) on a button, or None
    p = current.get("painter")
    dial = p.dial if p else None
    if not dial:
        return None
    if x is None:
        mx, my = cursor()
        x, y = mx - current.get("left", spot["x"]), my - current.get("top", spot["y"])
    for name, bx, by, radius in dial["buttons"]:
        if math.hypot(x - bx, y - by) <= radius:
            return name, None
    for cell in dial["cells"]:
        name, left, top, right, bottom, way = cell
        if left - 4 <= x <= right + 4 and top - 6 <= y <= bottom + 6:
            return name, dial_value(cell, x, y)
    return None

    if x is None:
        mx, my = cursor()
        x, y = mx - current.get("left", spot["x"]), my - current.get("top", spot["y"])
    for name, bx, by, radius in dial["buttons"]:
        if math.hypot(x - bx, y - by) <= radius:
            return name, None
    distance = math.hypot(x - dial["cx"], y - dial["cy"])
    angle = math.degrees(math.atan2(y - dial["cy"], x - dial["cx"])) % 360
    upper = 180 - 12 <= angle <= 360 or angle <= 12
    lower = 0 <= angle <= 180 + 12 or angle >= 360 - 12
    if not (upper if dial["up"] else lower):
        return None
    reach = 10 * dial["s"]
    if abs(distance - dial["ro"]) <= reach and controls.get("volume") is not None:
        return "volume", dial_value(dial, x, y)
    if abs(distance - dial["ri"]) <= reach and controls.get("bright") is not None:
        return "bright", dial_value(dial, x, y)
    return None

def set_control(name, value):
    value = max(0, min(100, int(value)))
    if controls.get(name) == value:
        return
    controls[name] = value
    if name == "volume":
        controls["muted"] = controls.get("muted") and value == 0
    redraw_controls()
    control_asks.put((name, value))

def redraw_controls():
    p = current.get("painter")
    if p and p.hover is not None:
        p.hover = dict(controls)

def read_controls():
    import audio
    import brightness
    try:
        controls["volume"], controls["muted"] = audio.get_volume()
    except Exception:
        controls.setdefault("volume", None)
    controls["bright"] = brightness.get()
    controls["mic"] = not state.muted

def control_worker():
    # Applies the newest value of each control (dragging sends many: only the last one matters), then re-reads
    import audio
    import brightness
    import settings
    while True:
        asks = [control_asks.get()]
        time.sleep(0.03)
        while not control_asks.empty():
            asks.append(control_asks.get_nowait())
        newest = {}
        for name, value in asks:
            newest[name] = value
        try:
            if "volume" in newest:
                audio.set_volume(newest["volume"])
            if "bright" in newest:
                brightness.set(newest["bright"])
            if "mute" in newest:
                volume, muted = audio.get_volume()
                audio.set_volume(mute=not muted)
            if "mic" in newest:
                settings.set_mic(state.muted)  # (offline -> online, online -> offline)
            if any(k in newest for k in ("mute", "mic", "refresh")) or not control_asks.qsize():
                read_controls()
                redraw_controls()
        except Exception as e:
            print("Reactor controls:", str(e)[:100])

def press_control(action):
    if action in ("mute", "mic"):
        if action == "mute":
            controls["muted"] = not controls.get("muted")
        else:
            controls["mic"] = not controls.get("mic", True)
        redraw_controls()
        control_asks.put((action, None))
        return True
    return False

last_cursor = [(0, 0)]

def cursor():
    # Where the mouse is. Windows says "Access is denied" while the lock screen or an admin (UAC) prompt is up:
    # then the last known spot is used (that error used to kill the whole reactor).
    try:
        last_cursor[0] = win32api.GetCursorPos()
    except Exception:
        pass
    return last_cursor[0]

# ---------- Mouse: click = text box / stop M.I.N.D talking, wheel = size, hold and drag = move it ----------
spot = {"x": 0, "y": 0}  # where the window is now (screen pixels)
current = {}             # the painter in use (its size and which side the chat is on)
drag = None              # while the mouse button is down: where it started

def on_down(hwnd, msg, wparam, lparam):
    global drag
    hit = dial_hit()
    if hit and hit[0] in ("volume", "bright"):
        # pressed on an arc: dragging moves the value round the dial, not the reactor
        drag = {"slider": hit[0]}
        set_control(hit[0], hit[1])
        win32gui.SetCapture(hwnd)
        return 0
    if hit and hit[0] in ("mute", "mic"):
        press_control(hit[0])
        drag = {"slider": "button"}  # (nothing more on release)
        win32gui.SetCapture(hwnd)
        return 0
    drag = {"mouse": cursor(), "window": (spot["x"], spot["y"]), "moved": False,
            "picture": (current.get("left", spot["x"]), current.get("top", spot["y"]))}  # where the picture really is
    win32gui.SetCapture(hwnd)  # keep getting the mouse even if it leaves the window
    return 0

def on_move(hwnd, msg, wparam, lparam):
    if drag and drag.get("slider") in ("volume", "bright"):
        p = current.get("painter")
        cell = next((c for c in (p.dial or {}).get("cells", []) if c[0] == drag["slider"]), None) if p else None
        if cell:
            mx, my = cursor()
            set_control(drag["slider"], dial_value(cell, mx - current.get("left", spot["x"]), my - current.get("top", spot["y"])))
        return 0
    if drag and drag.get("slider"):
        return 0
    if drag:
        mx, my = cursor()
        dx, dy = mx - drag["mouse"][0], my - drag["mouse"][1]
        if abs(dx) + abs(dy) > 4:
            drag["moved"] = True  # a real drag, not a shaky click
        if drag["moved"]:
            spot["x"], spot["y"] = drag["window"][0] + dx, drag["window"][1] + dy
            # the last picture moves with the mouse as it is (whatever layout it has), so it never jumps
            win32gui.SetWindowPos(hwnd, 0, drag["picture"][0] + dx, drag["picture"][1] + dy, 0, 0,
                                  win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
    return 0

def on_up(hwnd, msg, wparam, lparam):
    global drag
    was, drag = drag, None
    win32gui.ReleaseCapture()
    if was and was.get("slider"):
        return 0
    if was and was["moved"]:
        dropped()
        return 0
    if pressed_button():
        return 0
    # One click = the text box at once (or stop it talking). A second quick click = open or close the HUD
    # (the box from the first click goes away again). No waiting to see if a second click comes.
    import typebox
    now = time.time()
    if now - clicks["last"] < DOUBLE_CLICK:
        clicks["last"] = 0.0
        if clicks.get("opened_box"):
            typebox.close()
        threading.Thread(target=toggle_hud, daemon=True).start()
        return 0
    clicks["last"] = now
    current["dismiss"] = True  # the chat next to the reactor goes away
    clicks["opened_box"] = single_click()
    return 0

DOUBLE_CLICK = 0.35  # seconds between two clicks to count as a double-click

def pressed_button():
    # A click on Copy / Replace (next to the reactor): do it. The reactor never takes the keyboard
    # focus, so the box you were typing in (WhatsApp...) still has it and Replace pastes right there.
    import writing
    p = current.get("painter")
    if not p or not p.chips:
        return False
    mx, my = cursor()
    x, y = mx - current.get("left", spot["x"]), my - current.get("top", spot["y"])
    for action, (left, top, right, bottom) in p.chips:
        if left <= x <= right and top <= y <= bottom:
            if action in ("copy", "replace"):
                threading.Thread(target=writing.copy_now if action == "copy" else writing.replace_now, daemon=True).start()
                return True
            return True
    return False
clicks = {"last": 0.0, "opened_box": False}

def single_click():
    # Returns True if it opened the text box
    import typebox
    if typebox.is_open():
        typebox.close()  # second click: the box goes away
        return False
    if state.status in ("speaking", "thinking"):
        # Stop it. (A Live talk has to be ended directly: nothing reads clicks during one.)
        def stop():
            import live_brain
            if not live_brain.stop_talk():
                state.click()
        threading.Thread(target=stop, daemon=True).start()
        return False
    open_type_box()  # a click never starts listening: say "Mind" for that
    return True

BOX_HEIGHT = 30  # the little text box (at 100% screen scale)

def type_box_spot():
    # Where the little text box goes: beside the reactor, towards the middle of the screen
    # (reactor on the right -> box on its left, and the other way round), centred on it.
    # Follows the reactor while you drag it.
    p = current.get("painter")
    if not is_shown() or not p or current.get("hidden"):
        return None
    width, height, gap = int(TEXT_WIDTH * p.s), int(BOX_HEIGHT * p.s), int(GAP * p.s)
    reactor_x, reactor_y = reactor_place(p)
    monitor = win32api.MonitorFromPoint((reactor_x + p.r // 2, reactor_y + p.r // 2), win32con.MONITOR_DEFAULTTONEAREST)
    info = win32api.GetMonitorInfo(monitor)
    left, top, right, bottom = info["Monitor"]
    if at_taskbar(reactor_y, p.r, info):
        # reactor down at the taskbar: the box sits right above it, centred (like the chat)
        x = reactor_x + p.r // 2 - width // 2
        y = reactor_y - gap - height
        return max(left, min(right - width, x)), max(top, y), width, height
    if reactor_x + p.r / 2 > (left + right) / 2:
        x = reactor_x - gap - width  # reactor on the right half: box on its left
    else:
        x = reactor_x + p.r + gap
    y = spot["y"] + (p.h - height) // 2  # same height as the reactor's centre
    return max(left, min(right - width, x)), max(top, min(bottom - height, y)), width, height

def open_type_box():
    # Click on the reactor: a small text box appears next to it
    import typebox
    if type_box_spot():
        typebox.show(type_box_spot)

def toggle_hud():
    # Double-click: the HUD comes up (opens, or comes to the front if it's behind other windows);
    # if it's already in front, it closes. The reactor stays.
    import hud
    windows = hud.hud_windows()
    in_front = win32gui.GetForegroundWindow() in windows or any(
        not win32gui.IsIconic(w) and hud_on_top(w) for w in windows)
    if windows and in_front:
        for hud_window in windows:
            win32gui.PostMessage(hud_window, win32con.WM_CLOSE, 0, 0)
    else:
        hud.open_hud()  # opens it, or brings the open one to the front

def hud_showing():
    # Is the HUD on screen, not behind other windows? (The reactor steps aside then; the HUD has its own core.)
    import settings
    if not settings.on("reactor_hide"):
        return False
    found = []
    def check(hwnd, _):
        if (win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd) and win32gui.GetWindowText(hwnd) in ("M.I.N.D", "M.I.N.D Jarvis")
                and win32gui.GetClassName(hwnd).startswith("Chrome_WidgetWin")):
            found.append(hwnd)
    win32gui.EnumWindows(check, None)
    return any(hud_on_top(h) for h in found)  # (hud_on_top checks several spots: Jarvis mode may have a window in its middle)

def hud_on_top(hwnd):
    # The HUD is the top window at its own centre (so it's visible, not hidden behind WhatsApp...)
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        spots = [((left + right) // 2, (top + bottom) // 2), (left + 40, top + 40), (right - 40, top + 40), (left + 40, bottom - 40)]
        return any(win32gui.GetAncestor(win32gui.WindowFromPoint(spot), 2) == hwnd for spot in spots)  # 2 = the top-level window
    except Exception:
        return False

def dropped():
    # Remember where it was dropped: as the nearest corner + how far from it (survives restarts).
    # The chat goes on the side with more room, and the reactor stays where you put it.
    p = current["painter"]
    reactor_x = spot["x"] + (p.w - p.r if p.mirrored else 0)
    monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
    left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
    corner = (("top" if spot["y"] + p.h / 2 < (top + bottom) / 2 else "bottom") + "-"
              + ("left" if reactor_x + p.r / 2 < (left + right) / 2 else "right"))
    x = reactor_x - (p.w - p.r if "right" in corner else 0)
    base_x, base_y = corner_spot(corner, p.w, p.h)
    offset = (round((x - base_x) / p.s), round((spot["y"] - base_y) / p.s))
    commands.put(("move", (corner, offset)))
    try:
        from memory import profile, save_profile
        profile.update(floating=True, floating_position=corner, floating_offset=list(offset))
        save_profile()
    except Exception as e:
        print("Couldn't save the floating window's place:", e)

def no_focus(hwnd, msg, wparam, lparam):
    return 3  # MA_NOACTIVATE: clicking it doesn't take the keyboard away from your app

def on_close(hwnd, msg, wparam, lparam):
    commands.put(("hide", None))
    return 0

def run(corner, offset):
    # Runs in its own thread: makes the window, then draws up to 24 frames a second
    try:
        user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # sharp on scaled screens
    except Exception:
        pass
    instance = win32api.GetModuleHandle(None)
    wc = win32gui.WNDCLASS()
    wc.lpszClassName = "MIND_floating"
    wc.hInstance = instance
    wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_HAND)
    wc.lpfnWndProc = {win32con.WM_LBUTTONDOWN: on_down, win32con.WM_MOUSEMOVE: on_move,
                      win32con.WM_LBUTTONUP: on_up, win32con.WM_MOUSEACTIVATE: no_focus, win32con.WM_MOUSEWHEEL: on_wheel,
                      win32con.WM_CLOSE: on_close}
    try:
        win32gui.RegisterClass(wc)
    except win32gui.error:
        pass  # already registered (shown before)
    ex = win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE
    hwnd = win32gui.CreateWindowEx(ex, "MIND_floating", TITLE, win32con.WS_POPUP, 0, 0, 10, 10, 0, 0, instance, None)
    scale = (user32.GetDpiForWindow(hwnd) or 96) / 96

    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = None
    painter = None
    blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, use each pixel's alpha
    shown, hide_it, hud_checked, raised = False, False, 0.0, 0.0
    last_front, resting, away = 0, 0.0, 0.0
    import typebox
    import settings
    typebox.warm()  # (the text box is built now, hidden, so a click shows it at once)
    if not workers["controls"]:
        workers["controls"] = True
        threading.Thread(target=control_worker, daemon=True).start()
    while True:
        win32gui.PumpWaitingMessages()
        try:
            action, arg = commands.get_nowait()
        except queue.Empty:
            action, arg = None, None
        if action == "hide":
            break
        if action in ("move", "size") or painter is None:
            if arg:
                corner, offset = arg
            old = painter
            painter = Painter(scale, mirrored="right" in corner, size=reactor_size() / 100)
            if old:  # (carries on as it was: same colour and turn, and the last chat doesn't pop up again)
                painter.color, painter.bright, painter.angle = old.color, old.bright, old.angle
                painter.seen_id, painter.hide_at = old.seen_id, old.hide_at
            bits = ctypes.c_void_p()
            header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), painter.w, -painter.h, 1, 32, 0)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
            gdi32.SelectObject(memory, bitmap)
            current["height"] = painter.h
            if action == "size" and old:
                # Grows and shrinks around its own centre, then that spot is remembered like a drop
                middle_x = spot["x"] + (old.w - old.r if old.mirrored else 0) + old.r // 2
                middle_y = spot["y"] + old.h // 2
                spot["x"] = middle_x - painter.r // 2 - (painter.w - painter.r if painter.mirrored else 0)
                spot["y"] = middle_y - painter.h // 2
                current["painter"] = painter
                dropped()
            else:
                spot["x"], spot["y"] = corner_spot(corner, painter.w, painter.h, offset, scale, (painter.h - painter.r) // 2)
                current["painter"] = painter

        if current.pop("dismiss", None):
            painter.hide_at = 0  # clicked: the chat next to the reactor goes away
        # The mouse resting on the reactor shows the quick controls; they go when it's been away a moment
        mx, my = cursor()
        reactor_left, reactor_top = reactor_place(painter)
        on_reactor = reactor_left <= mx <= reactor_left + painter.r and reactor_top <= my <= reactor_top + painter.r
        on_picture = (current.get("left", 0) <= mx <= current.get("left", 0) + current.get("width", 0)
                      and current.get("top", 0) <= my <= current.get("top", 0) + current.get("height", 0))
        if painter.hover is None:
            if on_reactor and not drag and not typebox.is_open() and settings.on("reactor_controls"):
                if not resting:
                    resting = time.time()
                elif time.time() - resting > hover_delay():
                    painter.hover = dict(controls)
                    control_asks.put(("refresh", None))
                    away = 0.0
            else:
                resting = 0.0
        elif on_reactor or on_picture or (drag and drag.get("slider")):
            away = 0.0
        elif not away:
            away = time.time()
        elif time.time() - away > HOVER_LEAVE or typebox.is_open():
            painter.hover, resting, away = None, 0.0, 0.0
        if typebox.is_open() and painter.hover is not None:
            painter.hover = None

        if drag and drag.get("moved") and shown:
            # Being dragged: only move the last picture (no redrawing), so it follows the mouse with no lag
            time.sleep(0.004)
            continue
        # Where the reactor itself is on the screen. Down at the taskbar = the chat goes above it.
        reactor_left, reactor_top = reactor_place(painter)
        monitor = win32api.MonitorFromPoint((reactor_left + painter.r // 2, reactor_top + painter.r // 2),
                                            win32con.MONITOR_DEFAULTTONEAREST)
        info = win32api.GetMonitorInfo(monitor)
        screen_left, screen_top, screen_right, screen_bottom = info["Monitor"]
        painter.above = at_taskbar(reactor_top, painter.r, info)
        painter.dial_up = reactor_top + painter.r / 2 > (screen_top + screen_bottom) / 2  # low on the screen: dial opens up
        if painter.above and painter.text_layer is not None:
            wide = max(painter.r, painter.text_layer.width)
            centred = reactor_left + painter.r // 2 - wide // 2
            on_screen = max(screen_left, min(screen_right - wide, centred))
            painter.text_shift = on_screen - centred
        img, busy = painter.frame(state.snapshot())
        if (img.width, img.height) != (current.get("width"), current.get("height")):
            # (a long message: a bigger picture; the reactor stays where it is)
            header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), img.width, -img.height, 1, 32, 0)
            gdi32.DeleteObject(bitmap)
            bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
            gdi32.SelectObject(memory, bitmap)
            current["width"], current["height"] = img.width, img.height
        if painter.above or painter.hover is not None:
            # pinned: the picture is placed so the reactor lands exactly where you put it (the chat only grows
            # upward; the quick-control dial is drawn round it)
            left = reactor_left - painter.spot_in_picture[0]
            top = reactor_top - painter.spot_in_picture[1]
        else:
            left = spot["x"]
            top = max(screen_top, min(screen_bottom - img.height, spot["y"] - (img.height - painter.h) // 2))
        current["left"], current["top"] = left, top
        data = img.convert("RGBa").tobytes("raw", "BGRa")  # Windows wants blue-green-red-alpha, premultiplied
        ctypes.memmove(bits, data, len(data))
        user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(wintypes.POINT(left, top)),
                                   ctypes.byref(wintypes.SIZE(img.width, img.height)), memory,
                                   ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), 2)  # ULW_ALPHA
        if time.time() - hud_checked > 0.5:
            hud_checked = time.time()
            hide_it = hud_showing()
            current["hidden"] = hide_it
        if not shown and not hide_it:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
            shown = True
        elif shown and hide_it:
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)  # it sat on top of the HUD's Send button and took its clicks
            shown = False
        if not shown:
            user32.MsgWaitForMultipleObjects(0, None, False, 200, 0x04FF)
            continue
        # Stay above other windows. Clicking the taskbar (clock, sound, Wi-Fi...) lifts the taskbar over it,
        # so whenever another window comes to the front it's put back on top at once (it used to wait a second).
        front = user32.GetForegroundWindow()
        if front != last_front or time.time() - raised > 1:
            last_front = front
            raised = time.time()
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        # Wait for the next frame, but wake up AT ONCE for the mouse (a click used to wait up to 0.1 s for this)
        wait = 1 / 24 if busy or painter.hover is not None else 1 / 10  # smooth while busy / controls showing, calm when idle
        user32.MsgWaitForMultipleObjects(0, None, False, int(wait * 1000), 0x04FF)  # 0x04FF = any input or message

    win32gui.DestroyWindow(hwnd)
    if bitmap:
        gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(None, screen)

def run_safely(corner, offset):
    # The reactor in its own thread; if something ever breaks inside it, it comes back by itself a second later
    # (a crash used to make it vanish until M.I.N.D was restarted). Windows removes a dead thread's window.
    for attempt in range(30):
        result = []

        def guarded():
            try:
                run(corner, offset)
                result.append("closed")
            except Exception as e:
                import traceback
                print("(Floating reactor hit a problem, starting it again)", "".join(traceback.format_exception_only(type(e), e)).strip()[:160])
                result.append("crashed")
        worker = threading.Thread(target=guarded, daemon=True)
        worker.start()
        worker.join()
        if result and result[0] == "closed":
            return
        time.sleep(1)
        try:
            from memory import profile
            corner = profile.get("floating_position", corner)
            offset = tuple(profile.get("floating_offset", offset))
        except Exception:
            pass

def is_shown():
    return thread is not None and thread.is_alive()

def show(corner="bottom-right", offset=(0, 0)):
    global thread
    if is_shown():
        commands.put(("move", (corner, tuple(offset))))
        return
    while not commands.empty():
        commands.get_nowait()
    thread = threading.Thread(target=run_safely, args=(corner, tuple(offset)), daemon=True)
    thread.start()

def hide():
    if is_shown():
        commands.put(("hide", None))
        thread.join(3)

def window_tool(action="show", position="", far=False, size=""):
    # The floating_window tool: show / hide / move to a corner / nudge a little up, down, left or right / resize.
    # Remembers the place and size in profile.json.
    from memory import profile, save_profile
    if str(size).strip():
        said = str(size).strip().lower().rstrip("%")
        step = 50 if far else 25
        wanted = {"bigger": reactor_size() + step, "smaller": reactor_size() - step}.get(said, said)
        try:
            return f"Floating reactor size is now {set_size(float(wanted))} percent (it stays that way)."
        except ValueError:
            return f"Floating reactor size must be bigger, smaller or {SMALLEST}-{BIGGEST} percent."
    if action == "hide":
        hide()
        profile["floating"] = False
        save_profile()
        return "Floating window hidden."
    corner = profile.get("floating_position", "bottom-right")
    dx, dy = profile.get("floating_offset", [0, 0])
    if position in CORNERS:
        corner, dx, dy = position, 0, 0  # a new corner starts fresh
    if position in ("up", "down", "left", "right"):
        step = NUDGE * (4 if far else 1)
        dx += {"left": -step, "right": step}.get(position, 0)
        dy += {"up": -step, "down": step}.get(position, 0)
    show(corner, (dx, dy))
    profile.update(floating=True, floating_position=corner, floating_offset=[dx, dy])
    save_profile()
    if position in ("up", "down", "left", "right"):
        return f"Floating window moved {'a lot' if far else 'a little'} {position}."
    return f"Floating window {'moved to' if action == 'move' else 'shown at'} the {corner.replace('-', ' ')}."
