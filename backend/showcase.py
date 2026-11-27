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

# Wikimedia asks scripts to name themselves (a browser-looking script gets 429 "suspect automated")
BOT_AGENT = "MIND-voice-assistant/1.0 (personal assistant; https://github.com/pavithran-playing-with-code/M.I.N.D)"

def get(url, timeout=8):
    agent = BOT_AGENT if "wikipedia.org" in url or "wikimedia.org" in url else AGENT
    page = urllib.request.Request(url, headers={"User-Agent": agent})
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

def youtube_images(query, must=""):
    # A product's review video thumbnail = a clear photo of the real thing (no key, works for every user).
    # Only videos whose title names it (must = the product's own name, "Redragon K552").
    import finder
    found = []
    searches = [must + " review", query + " review"] if must and must != query else [query + " review"]
    results = []
    for search in searches:  # (its own name first: "Zebronics Zeb-Transformer keyboard under 2000" found nothing)
        results = [(v, t) for v, t in finder.youtube_results(search, 8) if about_it(must or query, t)]
        if results:
            break
    for video, title in results[:1]:  # (one good picture per product is enough: the others cost time)
        found.append({"url": big_thumbnail(video),
                      "thumb": f"https://i.ytimg.com/vi/{video}/mqdefault.jpg",  # (exists for every video)
                      "title": title[:80], "page": f"https://www.youtube.com/watch?v={video}"})
    return found

def big_thumbnail(video):
    # 1280x720 with no black bars when the video has one; some don't (404), then the 480x360 one
    big = f"https://i.ytimg.com/vi/{video}/hq720.jpg"
    try:
        urllib.request.urlopen(urllib.request.Request(big, method="HEAD"), timeout=3)
        return big
    except OSError:
        return f"https://i.ytimg.com/vi/{video}/hqdefault.jpg"

def images(query, count=6, must="", products=False):
    # Only pictures that are really of it, from wherever has them. None is better than a wrong one.
    # products: shop things first from YouTube review thumbnails (Bing answers scripts with random pictures,
    # Wikimedia has almost no products)
    found = []
    sources = (youtube_images, bing_images, commons_images) if products else (bing_images, commons_images)
    for source in sources:
        try:
            if source is youtube_images:
                found += source(query, must)
                continue
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

# ---- Live check on Amazon (2026-11-26: the AI's own prices were stale: "Realme Buds Wireless 2 Neo, approx. 999"
# was really 1,599, and one pick had no picture). Amazon's normal search page, no key; real price, photo, link.
NOT_THE_THING = re.compile(r"compatible|replacement|\bcases?\b|\bcovers?\b|ear ?tips|cushions?|\bstraps?\b|"
                           r"\bskins?\b|protector|\bfor (realme|boat|oneplus|samsung|apple|redmi|noise|jbl|sony)\b", re.I)

FLUFF = {"bluetooth", "wireless", "in-ear", "in", "neckband", "earphones", "earbuds", "headphones", "tws", "true",
         "over-ear", "on-ear", "wired", "gaming", "smart", "with"}

def short_name(title):
    # "boAt Rockerz 113, 40 Hours Battery, Dual Pair..." -> "boAt Rockerz 113"
    name = re.split(r",| with | \| | - |\(|\[", title)[0].strip()
    name = re.sub(r"\b(newly launched|new launch|just launched|latest)\s+", "", name, flags=re.I)
    words = name.split()
    for i, word in enumerate(words[2:], 2):  # "Portronics Harmonics Prime Wireless Neckband..." -> stop at the fluff
        if word.lower() in FLUFF:
            name = " ".join(words[:i])
            break
    return name if len(name) <= 48 else name[:46].rsplit(" ", 1)[0] + "…"

def amazon_results(query, budget=0):
    # Real listings from Amazon.in's search page: title, price, rating, photo, product link.
    # budget: Amazon's own price filter (rupees). [] when Amazon doesn't answer (then nothing is checked).
    url = "https://www.amazon.in/s?k=" + quote_plus(query) + (f"&rh=p_36%3A-{int(budget) * 100}" if budget else "")
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Language": "en-IN,en;q=0.9"})
    for attempt in range(2):  # (Amazon now and then answers a script with an empty page: one more try)
        with urllib.request.urlopen(request, timeout=10) as resp:
            page = resp.read().decode("utf-8", "replace")
        if 's-search-result"' in page:
            break
        time.sleep(1.5)
    else:
        if "No results for" not in page:
            raise OSError("Amazon sent an empty page")  # (not "nothing fits": it just didn't answer properly)
    found = []
    for block in page.split('data-component-type="s-search-result"')[1:]:
        block = block[:40000]
        heads = [html.unescape(re.sub(r"<[^>]+>", "", h)).strip() for h in re.findall(r"<h2[^>]*>(.*?)</h2>", block, re.S)]
        heads = [h for h in heads if h and h != "Related searches"]
        price = re.search(r'a-price-whole">([\d,]+)', block)
        asin = re.search(r'data-asin="(\w{10})"', block)
        if not heads or not price or not asin:
            continue
        title = " ".join(heads[:2]) if len(heads) > 1 and heads[0].lower() not in heads[1].lower() else heads[-1]
        if NOT_THE_THING.search(title):
            continue
        rating = re.search(r'a-icon-alt">([\d.]+) out of 5', block)
        photo = re.search(r'class="s-image" src="([^"]+)"', block)
        found.append({"title": title, "price": int(price.group(1).replace(",", "")),
                      "rating": float(rating.group(1)) if rating else 0.0,
                      "photo": re.sub(r"\._AC_[^.]+_\.", "._AC_SL500_.", photo.group(1)) if photo else "",
                      "link": f"https://www.amazon.in/dp/{asin.group(1)}"})
    return found

def on_amazon(name):
    # The real listing of the AI's pick (brand + model words must match), or None
    try:
        listings = amazon_results(name)
    except OSError:
        return "unchecked"
    for listing in listings[:12]:
        if about_it(name, listing["title"]):
            return listing
    return None

BUDGET = re.compile(r"\b(?:under|below|within|less than|upto|up to|max(?:imum)?|budget(?: of)?)\s*(?:rs\.?|₹|inr)?\s*"
                    r"(\d[\d,]*)\s*(k\b)?", re.I)

def budget_from(text):
    # "under 1000" / "below ₹1,500" / "within 2k" -> rupees (0 = no budget said)
    found = BUDGET.search(text or "")
    if not found:
        return 0
    amount = int(found.group(1).replace(",", ""))
    return amount * 1000 if found.group(2) else amount

def real_products(items, topic, budget):
    # Checks the AI's picks on Amazon: real price/photo/link, drops ones over budget or not found,
    # and fills up with Amazon's own matches for the topic under the budget. Returns (cards, report) or
    # (None, why) when Amazon couldn't be checked.
    with ThreadPoolExecutor(6) as pool:
        try:
            search = BUDGET.sub("", topic or "").strip()  # "neckbands under 1000 with dual pairing" -> no price words
            more = pool.submit(amazon_results, search, budget) if search else None
            checked = list(pool.map(on_amazon, [i["name"] for i in items]))
            extra = more.result() if more else []
        except (OSError, ValueError):
            extra = []  # (the picks themselves may still be checked)
    cards, dropped, seen = [], [], set()
    def add(listing, note=""):
        bits = [f"₹{listing['price']:,} on Amazon now"] + ([f"★{listing['rating']}"] if listing["rating"] else [])
        note = re.sub(r"(approx\.?|about|around|~)?\s*(₹|rs\.?|inr)?\s*\d[\d,]*\s*(inr|rupees|rs)?[,;.]?\s*", "", note,
                      flags=re.I).strip(" ,;.") if note else ""
        cards.append({"name": short_name(listing["title"]), "note": (" · ".join(bits) + (" · " + note if note else ""))[:140],
                      "url": listing["photo"], "page": listing["link"], "title": listing["title"], "price": listing["price"],
                      "shops": {"amazon": listing["link"],
                                "flipkart": "https://www.flipkart.com/search?q=" + quote_plus(short_name(listing["title"]))}})
        seen.add(listing["link"])
    if all(c == "unchecked" for c in checked) and not extra:
        return None, "Amazon didn't answer properly"
    for item, listing in zip(items, checked):
        if listing == "unchecked":
            dropped.append(f"{item['name']} (Amazon didn't answer for it)")
        elif not listing:
            dropped.append(f"{item['name']} (not found on Amazon)")
        elif budget and listing["price"] > budget:
            dropped.append(f"{item['name']} (really ₹{listing['price']:,}, over the budget)")
        elif listing["link"] not in seen:
            add(listing, str(item.get("note", "")))
    # Fill up to 4 with good-rated real listings for the topic (already under the budget by Amazon's filter)
    # (the asked features first: "with dual pairing" -> titles that say "Dual Pair" come first)
    wanted = [w[:4] for w in re.findall(r"[a-z0-9]+", (topic or "").lower().split(" with ", 1)[-1]) if len(w) > 2]         if " with " in (topic or "").lower() else []
    def fits(listing):
        title = {w[:4] for w in re.findall(r"[a-z0-9]+", listing["title"].lower())}
        return sum(w in title for w in wanted)
    for listing in sorted(extra[:16], key=lambda l: (-fits(l), -l["rating"])):
        if len(cards) >= 4:
            break
        if listing["link"] not in seen and listing["rating"] >= 3.8 and (not budget or listing["price"] <= budget):
            add(listing)
    lines = [f"{i + 1}. {c['title'][:110]} — ₹{c['price']:,}" for i, c in enumerate(cards)]
    report = ("Checked live on Amazon.in just now (real listings, real prices; say THESE, not your guesses): "
              + "; ".join(lines) + ".")
    if dropped:
        report += " Dropped: " + "; ".join(dropped) + "."
    report += (" Only say a feature they asked for if the listing title shows it; otherwise say to check it. "
               "Prices change, so say 'right now on Amazon'.")
    return cards, report

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
    if items and products in (True, "true", "yes"):
        # Things to buy: every pick checked on Amazon first (real price, photo, link; over budget = dropped)
        budget = budget_from(state.last_user_text) or budget_from(topic)
        cards, report = real_products(items, topic, budget)
        if cards:
            put_on_hud({"kind": "pictures", "title": topic or "Here's what I found", "info": {}, "cards": cards})
            return f"On the HUD: {len(cards)} real picks. " + report
        if cards is not None:
            return report + " Nothing fit: tell them honestly and offer a slightly higher budget."
        print("(" + report + ", showing the AI's own picks)")
        unchecked = True
    else:
        unchecked = False
    with ThreadPoolExecutor(8) as pool:
        if items:
            # One picture for each thing (searched together, so it's as fast as one)
            # Each search includes the topic, so "HP K2000" + "keyboard" isn't a graphics card
            def picture(item):
                name = item["name"]
                missing = topic and not any(w.lower() in name.lower() for w in topic.split() if len(w) > 3)
                return (images(f"{name} {topic}" if missing else name, 1, must=name, products=True) or [{}])[0]
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
    if unchecked:
        said += " Amazon couldn't be checked just now: say the prices are only rough guesses."
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

