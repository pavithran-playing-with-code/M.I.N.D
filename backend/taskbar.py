# Taskbar: shows whether M.I.N.D is on or off on its pinned taskbar button
# (glowing cyan orb = on, grey orb = off). Run "python taskbar.py on|off" to set it by hand.
import os
import sys
import glob
import ctypes
import win32com.client

BACKEND = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(BACKEND, "icons")
ON_ICON = os.path.join(ICONS, "mind_on.ico")
OFF_ICON = os.path.join(ICONS, "mind_off.ico")
PLACES = [  # where M.I.N.D's button lives: the taskbar pin and the Start menu
    os.path.join(os.environ["APPDATA"], r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"),
    os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs"),
]

def make_icon(path, ring, core, glow):
    # A little orb like the HUD's: dark circle, a ring, a bright core
    from PIL import Image, ImageDraw, ImageFilter
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if glow:
        halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse((60, 60, 196, 196), fill=core[:3] + (170,))
        img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(22)))
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(base).ellipse((8, 8, 248, 248), fill=(3, 7, 13, 255))
    img = Image.alpha_composite(base, img)
    draw = ImageDraw.Draw(img)
    draw.ellipse((30, 30, 226, 226), outline=ring, width=16)
    draw.ellipse((90, 90, 166, 166), fill=core)
    img.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)])

def make_icons():
    os.makedirs(ICONS, exist_ok=True)
    if not os.path.exists(ON_ICON):
        make_icon(ON_ICON, ring=(62, 224, 255, 255), core=(160, 245, 255, 255), glow=True)
    if not os.path.exists(OFF_ICON):
        make_icon(OFF_ICON, ring=(80, 95, 105, 255), core=(70, 82, 90, 255), glow=False)

def mind_buttons():
    # Every shortcut that runs toggle_mind.bat
    shell = win32com.client.Dispatch("WScript.Shell")
    for folder in PLACES:
        for path in glob.glob(os.path.join(folder, "*.lnk")):
            shortcut = shell.CreateShortCut(path)
            if "toggle_mind" in shortcut.Arguments:
                yield path, shortcut

def show(on):
    try:
        make_icons()
        icon = ON_ICON if on else OFF_ICON
        for path, shortcut in mind_buttons():
            if shortcut.IconLocation.split(",")[0] != icon:
                shortcut.IconLocation = icon
                shortcut.Save()
        # Tell Windows the icons changed, so the taskbar redraws them
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception as e:
        print("Couldn't update the taskbar icon:", e)

if __name__ == "__main__":
    on = len(sys.argv) > 1 and sys.argv[1].lower() == "on"
    show(on)
    if not on:
        import hud
        hud.close_hud()  # M.I.N.D was turned off: close its HUD window too
        import telegram_bot
        telegram_bot.say_off()  # tell your phone
