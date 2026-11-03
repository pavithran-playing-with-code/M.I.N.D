# Design choices shown ON THE HUD (not as picture files): the same 4 design families for the HUD core, the
# floating reactor, the taskbar button and the phone app, so one look can be picked for all of them.
#   1 Reactor   2 HUD core   3 HUD core + reactor   4 Minimal ring
# The pictures go into backend/designs/ (git-ignored) and the HUD shows them (showcase kind "designs").
import math
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import icons

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "designs")
CYAN, DARK, WHITE = (40, 200, 255), (3, 7, 13), (225, 250, 255)
OFF = (95, 110, 120)
FAMILIES = {1: "Reactor", 2: "HUD core", 3: "HUD core + reactor", 4: "Minimal ring"}
NOW = {"core": 2, "reactor": 1, "taskbar": 1, "app": 1}  # what each one uses today

def glow(big, c, radius, color, strength):
    m = Image.new("L", (big, big), 0)
    ImageDraw.Draw(m).ellipse((c - radius, c - radius, c + radius, c + radius), fill=strength)
    m = m.filter(ImageFilter.GaussianBlur(radius * 0.45))
    g = Image.new("RGBA", (big, big), color + (0,))
    g.putalpha(m)
    return g

def coils(d, c, r_in, r_out, color, big, alpha=0.9):
    for i in range(10):
        a0 = math.radians(i * 36 - 90 + 5)
        a1 = a0 + math.radians(26)
        pts = [(c + r_in * math.cos(a0), c + r_in * math.sin(a0)), (c + r_out * math.cos(a0), c + r_out * math.sin(a0)),
               (c + r_out * math.cos(a1), c + r_out * math.sin(a1)), (c + r_in * math.cos(a1), c + r_in * math.sin(a1))]
        d.polygon(pts, fill=color + (60,), outline=color + (int(255 * alpha),), width=max(2, int(big * 0.007)))

def hud_core(size, on=True, tile=False, with_coils=False, text=""):
    # The HUD core: a ring of segments lit like a voice meter, ticks, a dashed ring with bracket arcs,
    # an inner ring with small blocks and spokes, a glowing centre
    big = size * 4
    c = big / 2
    color = CYAN if on else OFF
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    if tile:
        ImageDraw.Draw(img).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=DARK + (255,))
    if on:
        img = Image.alpha_composite(img, glow(big, c, big * 0.36, color, 70))
    d = ImageDraw.Draw(img)
    rgba = lambda a: color + (int(255 * a),)
    R = big * (0.43 if tile else 0.48)
    small = size <= 48
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
    if with_coils:
        coils(d, c, R * 0.3, R * 0.5, color, big)
    elif not small:
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
    if text and not small:
        font = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", int(big * 0.07))
        box = d.textbbox((0, 0), text, font=font)
        d.text((c - (box[2] - box[0]) / 2 - box[0], c - (box[3] - box[1]) / 2 - box[1]), text, font=font, fill=WHITE + (255,))
    else:
        rw = rc * 0.45
        d.ellipse((c - rw, c - rw, c + rw, c + rw), fill=(WHITE if on else (150, 160, 168)) + (255,))
    return img.resize((size, size), Image.LANCZOS)

def minimal(size, on=True, tile=False):
    # One bold glowing ring and a core: simple, clear even tiny
    big = size * 4
    c = big / 2
    color = CYAN if on else OFF
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    if tile:
        ImageDraw.Draw(img).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=DARK + (255,))
    if on:
        img = Image.alpha_composite(img, glow(big, c, big * 0.3, color, 120))
    d = ImageDraw.Draw(img)
    r = big * (0.32 if tile else 0.4)
    d.ellipse((c - r, c - r, c + r, c + r), outline=color + (255,), width=int(big * 0.06))
    r2 = r * 0.62
    for start in (200, 20):
        d.arc((c - r2, c - r2, c + r2, c + r2), start, start + 140, fill=color + (200,), width=int(big * 0.025))
    if on:
        img = Image.alpha_composite(img, glow(big, c, big * 0.12, color, 255))
        d = ImageDraw.Draw(img)
    p = r * 0.23
    d.ellipse((c - p, c - p, c + p, c + p), fill=(WHITE if on else (150, 160, 168)) + (255,))
    return img.resize((size, size), Image.LANCZOS)

def art(family, size, on=True, tile=False, text=""):
    if family == 1:
        return icons.draw(size, on, tile=tile)
    if family == 2:
        return hud_core(size, on, tile, text=text)
    if family == 3:
        return hud_core(size, on, tile, with_coils=True, text=text)
    return minimal(size, on, tile)

def on_dark(img, pad=0, color=(5, 12, 20)):
    back = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), color + (255,))
    back.alpha_composite(img, (pad, pad))
    return back

def taskbar_strip(family):
    # How the button looks on the Windows taskbar: on (glowing) next to off (dark), at real size
    strip = Image.new("RGBA", (300, 64), (32, 32, 36, 255))
    d = ImageDraw.Draw(strip)
    for x in (20, 60, 100):  # (other app buttons, for scale)
        d.rounded_rectangle((x, 16, x + 32, 48), radius=6, fill=(70, 72, 78, 255))
    strip.alpha_composite(art(family, 32, True, tile=True), (150, 16))
    d.line((152, 58, 180, 58), fill=(110, 200, 255, 255), width=3)  # (Windows' "open" line)
    strip.alpha_composite(art(family, 32, False, tile=True), (200, 16))
    font = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 11)
    d.text((150, 2), "on", font=font, fill=(200, 210, 220, 255))
    d.text((200, 2), "off", font=font, fill=(200, 210, 220, 255))
    return strip.resize((600, 128), Image.LANCZOS)

def phone_icon(family):
    # On a phone home screen: the icon in Android's circle, with a name under it
    screen = Image.new("RGBA", (220, 240), (0, 0, 0, 0))
    grad = Image.new("RGBA", (220, 240))
    gd = ImageDraw.Draw(grad)
    for y in range(240):
        gd.line((0, y, 220, y), fill=(40 + y // 6, 30 + y // 10, 80 + y // 5, 255))
    screen.alpha_composite(grad)
    icon = art(family, 140, True, tile=True)
    mask = Image.new("L", (140, 140), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 139, 139), fill=255)
    round_icon = Image.new("RGBA", (140, 140))
    round_icon.paste(icon, (0, 0), mask)
    screen.alpha_composite(round_icon, (40, 30))
    d = ImageDraw.Draw(screen)
    font = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 20)
    box = d.textbbox((0, 0), "M.I.N.D", font=font)
    d.text((110 - (box[2] - box[0]) / 2, 185), "M.I.N.D", font=font, fill=(255, 255, 255, 255))
    return screen

def make_and_show():
    # Puts the options on the HUD. The HUD draws them itself, live, with the orbits (src/components/Emblem.jsx);
    # the picture drawers above are for making the real icon files once a look is picked.
    import showcase
    sections = []
    for key, title, note in (("core", "HUD core", "The big core in the middle of the HUD, with its orbits"),
                             ("reactor", "Floating reactor", "The one that floats on your screen"),
                             ("taskbar", "Taskbar button", "On (glowing) and off (dark), real size"),
                             ("app", "Phone app icon", "On your phone's home screen")):
        items = [{"n": family, "name": name + (" (now)" if NOW[key] == family else "")}
                 for family, name in FAMILIES.items()]
        sections.append({"title": title, "part": key, "note": note, "items": items})
    showcase.put_on_hud({"kind": "designs", "title": "Pick a look: same number = same family",
                         "sections": sections, "cards": [], "info": {}}, minutes=30)
    return "The design options are on the HUD."

if __name__ == "__main__":
    print(make_and_show())
