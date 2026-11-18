# Showcase: shows pictures and info about something on the HUD.
# "Mind, show me Iron Man suits" / "what is biryani" / "show me 3 good keyboards".
# Pictures come from Bing image search (free, no key), facts from Wikipedia.
# Also: shop links for picks.
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
from memory import BASE_DIR

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

LITTLE_WORDS = {"the", "for", "and", "with", "from", "of", "my", "me", "mom", "dad", "best", "good", "great"}

def word_stems(text):
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w
            for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 and w not in LITTLE_WORDS}

def about_it(query, title):
    # Is this picture really of what was asked? Most of the words must be in its title or address.
    # (Bing started answering scripts with random pictures: socks came back as a wedding and a face.)
    wanted = word_stems(query)
    return bool(wanted) and len(wanted & word_stems(title)) >= (len(wanted) * 3 + 4) // 5  # (60 %, rounded up)

def bing_images(query):
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
    return found

def commons_images(query):
    # Wikimedia Commons, the open picture library: good for things, places and food, almost no shop products
    answer = json.loads(get("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
                            "&gsrnamespace=6&gsrlimit=20&prop=imageinfo&iiprop=url&iiurlwidth=480&gsrsearch="
                            + quote_plus(query + " filetype:bitmap")))
    pages = sorted((answer.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    return [{"url": p["imageinfo"][0]["url"], "thumb": p["imageinfo"][0].get("thumburl", ""),
             "title": p["title"].removeprefix("File:").rsplit(".", 1)[0][:80],
             "page": p["imageinfo"][0].get("descriptionurl", "")} for p in pages if p.get("imageinfo")]

def images(query, count=6):
    # Only pictures that are really of it, from wherever has them. None is better than a wrong one.
    found = []
    for source in (bing_images, commons_images):
        try:
            found += [p for p in source(query) if about_it(query, p["title"] + " " + p["page"])]
        except (OSError, ValueError, KeyError) as e:
            print("Picture search problem:", str(e)[:80])
        if len(found) >= count:
            break
    return found[:count]

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
# Pictures M.I.N.D put on the HUD, so "show me those horror films again" brings back
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
    if show.get("kind") != "pictures":
        return  # (grammar cards aren't things to show again)
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
    words -= {"pictures", "picture", "photos", "images"}
    for old in reversed(shown):
        if old.get("kind") != "pictures":
            continue
        if not words or words & set(re.findall(r"\w+", old["title"].lower())):
            show = {k: v for k, v in old.items() if k not in ("at", "id")}
            put_on_hud(show, minutes=5, again=True)
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

def show_on_hud(topic="", items=None, hide=False, facts=True, again=False, products=False):
    # topic: what to show ("iron man suits"). items: several things to show side by side
    # ([{"name": "Redragon K552", "note": "mechanical, ₹1,399"}]): one picture each.
    # products: things to buy, so each card gets Amazon/Flipkart buttons.
    # again: show the same pictures as before ("show me that again")
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
            shop = products in (True, "true", "yes") or shopping()
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
    pictured = sum(1 for c in cards if c.get("url"))
    if not pictured and not any(c.get("shops") for c in cards):
        return f"Couldn't find real pictures of {topic or items[0]['name']}. Tell them so."
    put_on_hud({"kind": "pictures", "title": topic or "Here's what I found", "info": info, "cards": cards})
    said = f"Showing {len(cards)} picture{'s' if len(cards) != 1 else ''} on the HUD now."
    if pictured < len(cards):
        said = (f"On the HUD: {len(cards)} cards, but only {pictured} with a real picture (none found for the others). "
                "Tell them that honestly; don't describe how they look.")
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

