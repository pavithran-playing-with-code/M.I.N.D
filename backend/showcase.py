# Showcase: shows pictures and info about something on the HUD, like a hologram.
# "Mind, show me Iron Man suits" / "what is biryani" / "show me 3 good keyboards".
# Pictures come from Bing image search (free, no key), facts from Wikipedia.
import re
import json
import html
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, quote_plus
import urllib.request
import state

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
HIDE_AFTER = 5 * 60  # the panel goes away by itself after 5 minutes

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

def hide_later(shown_id):
    time.sleep(HIDE_AFTER)
    if state.showcase and state.showcase["id"] == shown_id:
        state.showcase = None

def show_on_hud(topic="", items=None, hide=False, facts=True):
    # topic: what to show ("iron man suits"). items: several things to show side by side
    # ([{"name": "Redragon K552", "note": "mechanical, ₹1,399"}]): one picture each.
    import hud
    if hide:
        state.showcase = None
        return "Cleared the HUD."
    items = [i if isinstance(i, dict) else {"name": str(i)} for i in (items or []) if i][:6]
    items = [i for i in items if str(i.get("name", "")).strip()]  # empty items ({}) = just show the topic
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
            cards = [{"name": i.get("name", ""), "note": str(i.get("note", ""))[:120], **pic}
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
    shown_id = int(time.time() * 1000)
    state.showcase = {"id": shown_id, "title": topic or "Here's what I found", "info": info, "cards": cards}
    threading.Thread(target=hide_later, args=(shown_id,), daemon=True).start()
    hud.open_hud()  # opens the HUD (or brings it to the front) so you can see it
    said = f"Showing {len(cards)} pictures on the HUD now."
    if info:
        said += " Wikipedia says: " + info["text"][:400]
    return said
