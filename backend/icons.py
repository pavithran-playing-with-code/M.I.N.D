# M.I.N.D's icon, drawn once and used everywhere (phone app, HUD tab, taskbar button, Chrome extension), so it
# always looks like the floating reactor and the HUD core: ticks, three arcs, ten coils and a glowing core on a
# dark tile. Run "python icons.py" to make them all again (it also runs by itself when one is missing).
import math
import os
from PIL import Image, ImageDraw, ImageFilter

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
ICONS = os.path.join(BACKEND, "icons")
CYAN, WHITE, DARK = (40, 200, 255), (225, 250, 255), (3, 7, 13)
OFF = (95, 110, 120)  # M.I.N.D off: the light is out

def draw(size, on=True, tile=True, safe=1.0):
    # One icon picture. tile: the dark rounded square behind it. safe: how much of the picture the reactor may
    # fill (Android's "maskable" icons cut the edges, so the reactor stays inside the middle 80 %).
    big = size * 4  # (drawn 4x bigger, then shrunk: smooth edges)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = big / 2
    color = CYAN if on else OFF
    small = size <= 32  # (tiny icons get fewer, thicker lines, or they turn to mush)
    if tile:
        d.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * (0.0 if safe < 1 else 0.22), fill=DARK + (255,))
        if on:  # a soft cyan glow behind the reactor
            glow = Image.new("L", (big, big), 0)
            ImageDraw.Draw(glow).ellipse((c - big * 0.36, c - big * 0.36, c + big * 0.36, c + big * 0.36), fill=90)
            glow = glow.filter(ImageFilter.GaussianBlur(big * 0.12))
            tint = Image.new("RGBA", (big, big), CYAN + (0,))
            tint.putalpha(glow)
            img = Image.alpha_composite(img, tint)
            d = ImageDraw.Draw(img)
    r = big * 0.44 * safe if tile else big * 0.48

    def rgba(alpha, rgb=color):
        return rgb + (int(255 * alpha),)

    def ring(radius, width, alpha):
        d.ellipse((c - radius, c - radius, c + radius, c + radius), outline=rgba(alpha), width=max(1, int(width)))

    # outer ticks
    ticks = 24 if small else 60
    for i in range(ticks):
        a = math.radians(i * 360 / ticks - 90)
        long = i % (3 if small else 5) == 0
        r_in, r_out = r * (0.86 if long else 0.91), r * 0.98
        d.line((c + r_in * math.cos(a), c + r_in * math.sin(a), c + r_out * math.cos(a), c + r_out * math.sin(a)),
               fill=rgba(0.95 if long else 0.5), width=max(2, int(big * (0.022 if small else 0.01) * (1.4 if long else 1))))
    # three arcs
    arc_r = r * 0.78
    for i in range(3):
        start = -60 + i * 120
        d.arc((c - arc_r, c - arc_r, c + arc_r, c + arc_r), start, start + 72, fill=rgba(1), width=max(2, int(big * (0.045 if small else 0.028))))
    if not small:
        ring(r * 0.68, big * 0.006, 0.45)
    # ten coils
    r_in, r_out = r * 0.42, r * 0.62
    for i in range(10):
        a0 = math.radians(i * 36 - 90 + 5)
        a1 = a0 + math.radians(26)
        pts = [(c + r_in * math.cos(a0), c + r_in * math.sin(a0)), (c + r_out * math.cos(a0), c + r_out * math.sin(a0)),
               (c + r_out * math.cos(a1), c + r_out * math.sin(a1)), (c + r_in * math.cos(a1), c + r_in * math.sin(a1))]
        d.polygon(pts, fill=rgba(0.28 if on else 0.18), outline=rgba(0.95 if on else 0.6), width=max(2, int(big * (0.012 if small else 0.007))))
    ring(r * 0.38, big * (0.02 if small else 0.012), 0.9)
    # the glowing core
    core = r * 0.24
    if on:
        halo = Image.new("L", (big, big), 0)
        ImageDraw.Draw(halo).ellipse((c - core * 1.9, c - core * 1.9, c + core * 1.9, c + core * 1.9), fill=200)
        halo = halo.filter(ImageFilter.GaussianBlur(core * 0.7))
        glow = Image.new("RGBA", (big, big), CYAN + (0,))
        glow.putalpha(halo)
        img = Image.alpha_composite(img, glow)
        d = ImageDraw.Draw(img)
    d.ellipse((c - core, c - core, c + core, c + core), fill=rgba(0.95))
    inner = core * 0.55
    d.ellipse((c - inner, c - inner, c + inner, c + inner), fill=(WHITE if on else (150, 160, 168)) + (255,))
    return img.resize((size, size), Image.LANCZOS)

def make_all():
    # Every icon M.I.N.D uses, from the one drawing
    os.makedirs(ICONS, exist_ok=True)
    for size in (180, 192, 512):  # the phone app (180 = iPhone home screen)
        draw(size).save(os.path.join(ICONS, f"app-{size}.png"))
    draw(512, safe=0.8).save(os.path.join(ICONS, "app-maskable-512.png"))  # (Android shapes: circle, squircle...)
    draw(64).save(os.path.join(ROOT, "public", "favicon.png"))  # the HUD's browser tab
    for size in (16, 32, 48, 128):  # the Chrome extension
        draw(size).save(os.path.join(ROOT, "extension", "icons", f"icon{size}.png"))
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)]
    for name, on in (("mind_on.ico", True), ("mind_off.ico", False), ("mind.ico", True)):  # the taskbar button
        pictures = [draw(s, on) for s, _ in sizes]
        pictures[-1].save(os.path.join(ICONS, name), sizes=sizes, append_images=pictures[:-1])

def ensure():
    # Makes them if any is missing (a fresh copy of M.I.N.D)
    needed = [os.path.join(ICONS, n) for n in ("app-192.png", "app-512.png", "app-maskable-512.png", "mind_on.ico", "mind_off.ico")]
    if not all(os.path.exists(p) for p in needed):
        make_all()

if __name__ == "__main__":
    make_all()
    print("Made every M.I.N.D icon.")
