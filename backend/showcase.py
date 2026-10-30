# Showcase: shows pictures and info about something on the HUD, like a hologram.
# "Mind, show me Iron Man suits" / "what is biryani" / "show me 3 good keyboards".
# Pictures come from Bing image search (free, no key), facts from Wikipedia.
# Also: shop links for picks, animations M.I.N.D writes itself, and lesson cards.
import os
import re
import json
import html
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, quote_plus
import urllib.request
import state
from memory import profile, save_profile, BASE_DIR

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

def get(url, timeout=8):
    page = urllib.request.Request(url, headers={"User-Agent": AGENT})
    for attempt in range(2):  # the internet sometimes drops a request
        try:
            with urllib.request.urlopen(page, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except OSError:
            if attempt == 1:
                raise

def images(query, count=6):
    # Bing image search (safe search on). Each picture: big url, small url (always loads), title, page
    page = get("https://www.bing.com/images/async?q=" + quote_plus(query) + "&first=0&count=20&adlt=strict")
    found, seen = [], set()
    for raw in re.findall(r'\bm="([^"]+)"', page):
        try:
            item = json.loads(html.unescape(raw))
        except ValueError:
            continue
        if not item.get("murl") or item.get("turl") in seen:
            continue
        seen.add(item.get("turl"))
        found.append({"url": item["murl"], "thumb": item.get("turl", ""),
                      "title": html.unescape(item.get("t", ""))[:80], "page": item.get("purl", "")})
        if len(found) >= count:
            break
    return found

def wikipedia(topic):
    # A short summary of the topic from Wikipedia ("" if there's no good page)
    search = json.loads(get("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=1&srsearch="
                            + quote_plus(topic)))
    hits = search.get("query", {}).get("search", [])
    if not hits:
        return {}
    title = hits[0]["title"]
    summary = json.loads(get("https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"))))
    if summary.get("type") == "disambiguation" or not summary.get("extract"):
        return {}
    return {"title": summary.get("title", title), "text": summary["extract"][:700],
            "link": summary.get("content_urls", {}).get("desktop", {}).get("page", "")}

def hide_later(shown_id, seconds):
    # The panel goes away by itself after a while (unless something newer is showing)
    time.sleep(seconds)
    if state.showcase and state.showcase["id"] == shown_id:
        state.showcase = None

# ---------- What was shown lately ("show me that again") ----------
# Pictures and animations M.I.N.D put on the HUD, so "show me those horror films again" brings back
# the SAME ones (it once searched a Claude chat instead, or made a new list). Kept in shown.json
# (personal, git-ignored), last 12 from the last 3 days.
SHOWN_FILE = os.path.join(BASE_DIR, "shown.json")

def load_shown():
    try:
        with open(SHOWN_FILE, encoding="utf-8") as f:
            return [s for s in json.load(f) if time.time() - s.get("at", 0) < 3 * 86400]
    except (OSError, ValueError):
        return []

shown = load_shown()

def remember_shown(show):
    if show.get("kind") not in ("pictures", "animation"):
        return  # (lesson and grammar cards aren't things to show again)
    shown.append({**show, "at": time.time()})
    del shown[:-12]
    try:
        with open(SHOWN_FILE, "w", encoding="utf-8") as f:
            json.dump(shown, f, ensure_ascii=False)
    except OSError:
        pass

LITTLE_WORDS = {"the", "and", "that", "this", "those", "you", "your", "me", "again", "show", "showed", "with", "for", "from"}

def show_again(topic=""):
    # The newest thing shown whose title shares a word with 'topic' (or simply the newest one)
    words = {w for w in re.findall(r"\w+", topic.lower()) if len(w) > 2} - LITTLE_WORDS
    kind = "animation" if words & {"animation", "animations"} else ""  # "show me that animation again"
    words -= {"animation", "animations", "pictures", "picture", "photos", "images"}
    for old in reversed(shown):
        if kind and old["kind"] != kind:
            continue
        if not words or words & set(re.findall(r"\w+", old["title"].lower())):
            show = {k: v for k, v in old.items() if k not in ("at", "id")}
            put_on_hud(show, minutes=10 if show["kind"] == "animation" else 5, again=True)
            return f"Showing again: '{old['title']}' ({show['kind']}, from {time.strftime('%I:%M %p', time.localtime(old['at']))})."
    return "Nothing like that was shown lately" + (f" (no '{topic}')." if topic else ".") + " Show it fresh instead."

def recently_shown():
    # For the live brain's instructions: what's been on the HUD today
    today = time.strftime("%Y%m%d")
    return [f"{time.strftime('%I:%M %p', time.localtime(s['at']))} {s['kind']}: {s['title']}"
            + (" (" + ", ".join(c["name"] for c in s.get("cards", []) if c.get("name"))[:120] + ")" if any(c.get("name") for c in s.get("cards", [])) else "")
            for s in shown if time.strftime("%Y%m%d", time.localtime(s["at"])) == today][-5:]

def put_on_hud(show, minutes=5, again=False):
    # Shows it on the HUD (opens the HUD if needed); it goes away by itself after a while
    import hud
    if not again:
        remember_shown(show)
    show["id"] = int(time.time() * 1000)
    state.showcase = show
    threading.Thread(target=hide_later, args=(show["id"], minutes * 60), daemon=True).start()
    hud.open_hud()

def shop_search(name, topic=""):
    # Amazon/Flipkart search pages for a product (search pages always work, even if the AI's name is a bit off)
    query = f"{name} {topic}" if topic and not any(w.lower() in name.lower() for w in topic.split() if len(w) > 3) else name
    return {"amazon": "https://www.amazon.in/s?k=" + quote_plus(query),
            "flipkart": "https://www.flipkart.com/search?q=" + quote_plus(query)}

SHOP_WORDS = re.compile(r"\b(suggest|recommend|buy|budget|price|under|cheap|best|order|shop|shopping|"
                        r"rs|rupees|amazon|flipkart|gift)\b|₹", re.I)

def shopping():
    # Shop buttons only when they're shopping ("suggest socks under 1500"), not for "what is parotta".
    # Also counts the message before, since "anything mixed in" answers Mind's question about socks.
    import brain
    asked = [m.get("content") or "" for m in brain.history[-4:] if m.get("role") == "user"]
    return any(SHOP_WORDS.search(t) for t in [state.last_user_text] + asked[-1:])

NOT_A_TOPIC = re.compile(r"^\s*(ask|asking|question|questions|clarify|options?|none|null|n/?a|\?+)(\s+(a\s+)?question)?\s*$", re.I)

def show_on_hud(topic="", items=None, hide=False, facts=True, again=False):
    # topic: what to show ("iron man suits"). items: several things to show side by side
    # ([{"name": "Redragon K552", "note": "mechanical, ₹1,399"}]): one picture each.
    # again: show the same pictures/animation as before ("show me that again")
    if again in (True, "true", "yes"):
        return show_again(topic)
    if hide:
        state.showcase = None
        return "Cleared the HUD."
    items = [i if isinstance(i, dict) else {"name": str(i)} for i in (items or []) if i][:6]
    items = [i for i in items if str(i.get("name", "")).strip()]  # empty items ({}) = just show the topic
    if len(items) == 1 and not topic:
        topic = items[0]["name"]
    if len(items) == 1:
        items = []  # one thing ("Parotta") = show many pictures of it, not one card
    if NOT_A_TOPIC.match(topic or "") and not items:
        # It once called this with topic "ask question" before asking its question
        return "Not shown: ask your question in words first; call show_on_hud after they answer."
    if not topic and not items:
        return "Nothing to show: give a topic or items."
    with ThreadPoolExecutor(8) as pool:
        if items:
            # One picture for each thing (searched together, so it's as fast as one)
            # Each search includes the topic, so "HP K2000" + "keyboard" isn't a graphics card
            def picture(item):
                name = item["name"]
                missing = topic and not any(w.lower() in name.lower() for w in topic.split() if len(w) > 3)
                return (images(f"{name} {topic}" if missing else name, 1) or [{}])[0]
            pictures = list(pool.map(picture, items))
            shop = shopping()
            cards = [{"name": i.get("name", ""), "note": str(i.get("note", ""))[:120], **pic,
                      **({"shops": shop_search(i["name"], topic)} if shop else {})}
                     for i, pic in zip(items, pictures)]
            info = {}
        else:
            got_images = pool.submit(images, topic, 6)
            got_info = pool.submit(wikipedia, topic) if facts else None
            cards = [{"name": "", "note": "", **pic} for pic in got_images.result()]
            try:
                info = got_info.result() if got_info else {}
            except Exception:
                info = {}  # no facts is fine, the pictures still show
    if not any(c.get("url") for c in cards):
        return f"Couldn't find pictures of {topic or items[0]['name']}."
    put_on_hud({"kind": "pictures", "title": topic or "Here's what I found", "info": info, "cards": cards})
    said = f"Showing {len(cards)} picture{'s' if len(cards) != 1 else ''} on the HUD now."
    if any(c.get("shops") for c in cards):
        said += " Each has Amazon/Flipkart buttons (shop_links opens them)."
    if info:
        said += " Wikipedia says: " + info["text"][:400]
    return said

def shown_products():
    show = state.showcase or {}
    return [c for c in show.get("cards", []) if c.get("shops")]

def shop_links(store="amazon", which="all", to_phone=False):
    # Opens (or sends to your phone) the Amazon/Flipkart pages of the picks on the HUD
    import tools
    picks = shown_products()
    if not picks:
        return "No product picks are on the HUD right now (show some with show_on_hud items first)."
    store = "flipkart" if "flip" in (store or "").lower() else "amazon"
    which = str(which or "all").lower().strip()
    numbers = {"1": 0, "first": 0, "one": 0, "2": 1, "second": 1, "two": 1, "3": 2, "third": 2, "three": 2,
               "4": 3, "fourth": 3, "5": 4, "fifth": 4, "last": len(picks) - 1}
    if which in numbers and numbers[which] < len(picks):
        picks = [picks[numbers[which]]]
    elif which not in ("all", "", "them", "every", "everything"):
        named = [p for p in picks if which in p["name"].lower()]
        picks = named or picks
    links = [(p["name"], p["shops"][store]) for p in picks]
    if to_phone:
        tools.send_to_phone("\n".join(f"{name}: {url}" for name, url in links))
        return f"Sent {len(links)} {store.title()} link(s) to their phone."
    for _, url in links:
        tools.open_page(url)
    return f"Opened {len(links)} {store.title()} page(s): " + ", ".join(name for name, _ in links)

# ---------- Animations M.I.N.D makes ("create a cool flower animation") ----------
CREATIONS = os.path.join(BASE_DIR, "creations")  # saved here (git-ignored), shown on the HUD
ANIMATION_RULES = """You design holograms for Mind's hologram engine (glowing wireframe light, like Jarvis).
You DON'T write code: describe the scene as JSON, and the engine draws and animates it.
Reply with JSON only:
{"title": "short title", "colour": "gold|cyan|blue|red|green|purple|white|orange",
 "things": [{"name": "dog", "at": [x, y, z], "scale": 1, "colour": "optional",
   "move": {"type": "none|bob|spin|hop|pace|orbit|chase", "speed": 1, "radius": 4, "offset": 0},
   "parts": [ ...shapes... ]}]}
Space: y is up, the ground is y = 0, x is forward (a creature faces +x), z is sideways. A dog is about 4 long
and 3 tall. Build each thing at its own spot around 0,0,0 ("at" moves the whole thing).
Shapes (all numbers):
- {"shape": "sphere", "at": [x,y,z], "size": r}            heads, eyes, balls
- {"shape": "ellipsoid", "at": [x,y,z], "size": [rx,ry,rz]} bodies, snouts, leaves
- {"shape": "cylinder", "from": [x,y,z], "to": [x,y,z], "radius": r}   legs, necks, arms, trunks
- {"shape": "cone", "from": [base], "to": [tip], "radius": r}          ears, horns, teeth, beaks, spikes
- {"shape": "torus", "at": [x,y,z], "size": [R, r], "rot": [rx,ry,rz]}  rings, wheels, halos
- {"shape": "box", "at": [x,y,z], "size": [w,h,d]}           buildings, screens, tables
- {"shape": "curve", "points": [[x,y,z], ...3-8 points], "radius": r}  tails, snakes, tentacles, vines
Motion on a part (makes it alive):
- "swing": {"axis": "x|y|z", "amount": 0.5, "speed": 4, "phase": 0}: turns around its "from"/first point.
  Legs: axis "z", opposite legs phase 0 and 3.14. Tail wag: axis "y". Wings: axis "x".
- "wave": {"amount": 0.4, "speed": 3}: a ripple along it (snakes, flags, tentacles).
Moves for a whole thing: bob (floats), spin, hop, pace (walks back and forth), orbit (walks in a circle),
chase (orbit too; give the chaser the same radius and a smaller "offset" so it runs behind the other).
Rules:
- Real, recognisable shapes: 8-25 parts per creature (body, head, snout, both ears, eyes, 4 legs, tail...).
  Keep parts touching so the body is connected. Up to 3 things, 60 parts in total.
- Make it ALIVE and tell a little story: legs swing, tails wag, things move and interact.
- Colour: gold unless the idea suggests another colour; one thing may have its own colour."""

# Who writes the holograms, best first. Each page is checked before it's shown, because a busy
# Gemini ("overloaded") once handed the job to a backup that wrote a page that stayed black.
# Gemini 3.5 Flash draws by far the best ones, so when it's "overloaded" it gets a second try after a short
# wait (animations run in the background now, so a few more seconds don't block the talk).
ANIMATION_WRITERS = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.5-flash", "openai/gpt-oss-120b",
                     "gemini-3.1-flash-lite"]

def looks_empty(path):
    # Opens the page in a hidden Chrome for 3 seconds and takes a picture: almost all one colour = broken
    # (a real 3-second wait: Chrome's fake fast-forward clock hung on some holograms)
    import subprocess
    import tempfile
    import hud
    from PIL import Image
    chrome = hud.chrome_path()
    if not chrome:
        return False  # (can't check: show it anyway)
    folder = tempfile.mkdtemp(prefix="mind_check_")
    shot = os.path.join(folder, "shot.png")
    try:
        subprocess.run([chrome, "--headless=new", "--disable-gpu", f"--user-data-dir={folder}",
                        "--window-size=800,450", "--timeout=3000", f"--screenshot={shot}",
                        "file:///" + path.replace("\\", "/")],
                       capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        colours = Image.open(shot).convert("L").getcolors(256 * 256) or []
        biggest = max(count for count, _ in colours)
        return biggest > 0.985 * 800 * 450  # 98.5 % of the picture is one shade
    except Exception:
        return False
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)

SHAPES = {"sphere", "ellipsoid", "cylinder", "cone", "torus", "box", "curve"}
ENGINE = os.path.join(BASE_DIR, "holo_engine.js")  # draws the scene (the AI only describes it)

def scene_from(answer):
    # The writer's JSON -> a clean scene (unknown shapes dropped), or None if it isn't usable
    found = re.search(r"\{.*\}", answer or "", re.S)
    if not found:
        return None
    try:
        scene = json.loads(found.group(0), strict=False)
    except ValueError:
        return None
    things = []
    for thing in (scene.get("things") or [])[:3]:
        if not isinstance(thing, dict):
            continue
        parts = [p for p in (thing.get("parts") or []) if isinstance(p, dict) and p.get("shape") in SHAPES][:40]
        if parts:
            things.append({**thing, "parts": parts})
    if sum(len(t["parts"]) for t in things) < 3:
        return None  # (too little to be a real hologram)
    return {"title": str(scene.get("title", ""))[:80], "colour": str(scene.get("colour", "gold")), "things": things}

def hologram_page(scene):
    # One self-contained page: the engine with the scene inside (works offline, in a locked frame)
    engine = open(ENGINE, encoding="utf-8").read().replace("__SCENE__", json.dumps(scene, ensure_ascii=False))
    return ("<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;height:100%;"
            "background:#02050a;overflow:hidden}canvas{display:block;width:100vw;height:100vh}</style></head>"
            "<body><canvas id='c'></canvas><script>" + engine + "</script></body></html>")

def create_animation(idea):
    import brain
    os.makedirs(CREATIONS, exist_ok=True)
    name = re.sub(r"[^a-z0-9]+", "-", idea.lower()).strip("-")[:40] or "animation"
    file = f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.html"
    path = os.path.join(CREATIONS, file)
    # Meanwhile the HUD shows a golden globe of light "assembling" (it was an empty panel before)
    put_on_hud({"kind": "building", "title": idea, "cards": [], "info": {}}, minutes=3)
    tried = set()
    for writer in ANIMATION_WRITERS:
        if writer in tried:
            time.sleep(8)  # (its second try: give it a moment)
        tried.add(writer)
        scene = scene_from(brain.write(ANIMATION_RULES, "Make this hologram: " + idea, writers=[writer]))
        if not scene:
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(hologram_page(scene))
        if not looks_empty(path):
            break
        print(f"  ({writer}'s hologram stayed blank, trying the next writer)")
    else:
        if os.path.exists(path):
            os.remove(path)
        if state.showcase and state.showcase.get("kind") == "building":
            state.showcase = None  # (no globe spinning forever)
        return "Couldn't make it this time (the writers are busy). Try again in a minute?"
    put_on_hud({"kind": "animation", "title": scene.get("title") or idea, "src": "/api/creation/" + file,
                "cards": [], "info": {}}, minutes=10)
    return "Made it: the hologram is playing on the HUD now."

# ---------- Lessons ("help me learn Spanish") ----------
def show_lesson(topic, title, points, example="", question=""):
    points = [str(p)[:160] for p in (points or []) if p][:5]
    put_on_hud({"kind": "lesson", "title": title or topic, "topic": topic, "cards": [], "info": {},
                "points": points, "example": str(example)[:300], "question": str(question)[:200]}, minutes=20)
    learning = profile.setdefault("learning", {})
    done = learning.get(topic.lower(), {}).get("lessons", 0)
    learning[topic.lower()] = {"lessons": done + 1, "last": title, "date": time.strftime("%Y-%m-%d")}
    save_profile()
    return f"Lesson card is on the HUD (lesson {done + 1} of {topic})."
