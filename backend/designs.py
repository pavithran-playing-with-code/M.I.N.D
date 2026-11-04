# Draws M.I.N.D's icon (icons.py uses it for the phone app and the taskbar button): the HUD core
# with its "solar system" of three tilted orbits (same tilts as the HUD's CoreAura.jsx).
import math
from PIL import Image, ImageDraw, ImageFilter

CYAN, DARK, WHITE = (40, 200, 255), (3, 7, 13), (225, 250, 255)
OFF = (95, 110, 120)  # the dim grey "off" look
ORBITS = ((0.76, 0.28, 17, 0.10), (0.875, 0.5, -34, 0.45), (0.975, 0.18, 63, 0.78))  # size, tilt, turn, comet spot

def orbits(big, color, scale=1.0):
    # Each orbit: a faint path, dots along it and a bright comet with a tail
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, half = big / 2, big / 2 * scale
    for rx, tilt, turn, where in ORBITS:
        t = math.radians(turn)
        def place(a, rx=rx, tilt=tilt, t=t):
            x, y = math.cos(a) * rx * half, math.sin(a) * rx * tilt * half
            return c + x * math.cos(t) - y * math.sin(t), c + x * math.sin(t) + y * math.cos(t)
        d.line([place(i / 180 * math.tau) for i in range(181)], fill=color + (95,), width=max(2, int(big * 0.005)))
        dot = big * 0.0042
        for i in range(0, 180, 6):
            x, y = place(i / 180 * math.tau)
            d.ellipse((x - dot, y - dot, x + dot, y + dot), fill=color + (200,))
        for j in range(10):  # the comet, head first
            x, y = place((where - j * 0.012) * math.tau)
            r = big * (0.011 - j * 0.0009)
            d.ellipse((x - r, y - r, x + r, y + r), fill=color + (int(255 * (1 - j / 10)),))
    return img

def app_icon(size, safe=1.0, on=True):
    # A dark rounded tile, the orbits, and the HUD core in the middle
    big = size * 4
    color = CYAN if on else OFF
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=DARK + (255,))
    img = Image.alpha_composite(img, orbits(big, color, scale=0.98 * safe))
    img = img.resize((size, size), Image.LANCZOS)
    core = hud_core(int(size * 0.62 * safe), on=on)
    # a soft round edge, and a dark disc behind the core so the orbits pass BEHIND it
    fade = Image.new("L", core.size, 0)
    ImageDraw.Draw(fade).ellipse((core.width * 0.04,) * 2 + (core.width * 0.96,) * 2, fill=255)
    fade = fade.filter(ImageFilter.GaussianBlur(core.width * 0.03))
    core.putalpha(Image.composite(core.getchannel("A"), Image.new("L", core.size, 0), fade))
    behind = Image.new("RGBA", core.size, (0, 0, 0, 0))
    ImageDraw.Draw(behind).ellipse((core.width * 0.06,) * 2 + (core.width * 0.94,) * 2, fill=DARK + (255,))
    spot = ((size - core.width) // 2, (size - core.height) // 2)
    img.alpha_composite(behind.filter(ImageFilter.GaussianBlur(core.width * 0.02)), spot)
    img.alpha_composite(core, spot)
    return img

def glow(big, c, radius, color, strength):
    m = Image.new("L", (big, big), 0)
    ImageDraw.Draw(m).ellipse((c - radius, c - radius, c + radius, c + radius), fill=strength)
    m = m.filter(ImageFilter.GaussianBlur(radius * 0.45))
    g = Image.new("RGBA", (big, big), color + (0,))
    g.putalpha(m)
    return g

def hud_core(size, on=True):
    # The HUD core: a ring of segments lit like a voice meter, ticks, a dashed ring with bracket arcs,
    # an inner ring with small blocks and spokes, a glowing centre
    big = size * 4
    c = big / 2
    color = CYAN if on else OFF
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    if on:
        img = Image.alpha_composite(img, glow(big, c, big * 0.36, color, 70))
    d = ImageDraw.Draw(img)
    rgba = lambda a: color + (int(255 * a),)
    R = big * 0.48
    small = size <= 48  # (tiny icons get fewer, thicker marks)
    for i in range(24 if small else 48):
        a = math.radians(i * (15 if small else 7.5) - 90)
        long = i % (3 if small else 6) == 0
        r1 = R * (0.93 if long else 0.96)
        d.line((c + r1 * math.cos(a), c + r1 * math.sin(a), c + R * math.cos(a), c + R * math.sin(a)),
               fill=rgba(0.95 if long else 0.45), width=max(2, int(big * (0.012 if long else 0.006) * (2 if small else 1))))
    segs = 16 if small else 30
    ro, ri = R * 0.9, R * 0.76
    for i in range(segs):
        a0 = math.radians(i * 360 / segs - 90 + 2)
        a1 = a0 + math.radians(360 / segs - 4)
        lit = i < segs * 0.72
        d.polygon([(c + ri * math.cos(a0), c + ri * math.sin(a0)), (c + ro * math.cos(a0), c + ro * math.sin(a0)),
                   (c + ro * math.cos(a1), c + ro * math.sin(a1)), (c + ri * math.cos(a1), c + ri * math.sin(a1))],
                  fill=rgba(0.95 if lit and on else 0.18))
    rd = R * 0.66
    if not small:
        for i in range(36):
            d.arc((c - rd, c - rd, c + rd, c + rd), i * 10, i * 10 + 5, fill=rgba(0.55), width=max(2, int(big * 0.006)))
    for start in (200, 20):
        d.arc((c - rd, c - rd, c + rd, c + rd), start, start + 40, fill=rgba(0.95), width=max(2, int(big * 0.014)))
    rin = R * 0.55
    d.ellipse((c - rin, c - rin, c + rin, c + rin), outline=rgba(0.55), width=max(2, int(big * 0.006)))
    if not small:
        for i in range(12):
            a = math.radians(i * 30 + 15)
            d.line((c + R * 0.3 * math.cos(a), c + R * 0.3 * math.sin(a), c + R * 0.5 * math.cos(a), c + R * 0.5 * math.sin(a)),
                   fill=rgba(0.4), width=max(2, int(big * 0.005)))
        for i in range(10):
            a = math.radians(i * 36)
            x, y, s = c + rin * math.cos(a), c + rin * math.sin(a), big * 0.018
            d.rectangle((x - s, y - s, x + s, y + s), fill=rgba(0.8))
    if on:
        img = Image.alpha_composite(img, glow(big, c, R * 0.38, color, 230))
        d = ImageDraw.Draw(img)
    rc = R * 0.27
    d.ellipse((c - rc, c - rc, c + rc, c + rc), fill=rgba(0.55))
    rw = rc * 0.45
    d.ellipse((c - rw, c - rw, c + rw, c + rw), fill=(WHITE if on else (150, 160, 168)) + (255,))
    return img.resize((size, size), Image.LANCZOS)
