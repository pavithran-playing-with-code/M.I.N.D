# Mini-apps on the HUD, so M.I.N.D doesn't have to say "I can't":
# - a book reader: free classic books from Project Gutenberg (search through gutendex.com, free, no key),
#   page by page on the HUD, turned by voice or the HUD's arrows, remembering where you stopped
# - typing practice: a passage on the HUD, you type it, M.I.N.D gets your speed and accuracy
# Books are kept in backend/books (git-ignored). Progress is in profile.json ("reading", "typing").
import os
import re
import html
import json
import time
import random
import urllib.parse
import urllib.request
import state
from memory import profile, save_profile, BASE_DIR

BOOKS = os.path.join(BASE_DIR, "books")
PAGE_CHARS = 1800  # about one screen of text
AGENT = {"User-Agent": "MIND-assistant/1.0 (personal reader)"}

def get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=timeout) as resp:
        return resp.read()

# ---------- Books ----------
found_books = []  # the last search results ("open the second one")

def find_books(query):
    # Search Project Gutenberg itself (its catalogue feed answers in ~1 s), most popular first:
    # [{id, title, author, summary}]. gutendex.com (has summaries) is only the backup: it often took 25 s+.
    try:
        feed = get("https://www.gutenberg.org/ebooks/search.opds/?query=" + urllib.parse.quote_plus(query)).decode("utf-8", "ignore")
        books = []
        for entry in re.findall(r"<entry>(.*?)</entry>", feed, re.S):
            found = re.search(r"/ebooks/(\d+)\.opds", entry)
            title = re.search(r"<title>(.*?)</title>", entry, re.S)
            author = re.search(r'<content type="text">(.*?)</content>', entry, re.S)
            if found and title and not re.search(r"\((?!English)[A-Z][a-z]+\)\s*$", title.group(1).strip()):
                # (other-language editions like "... (German)" are skipped)
                books.append({"id": int(found.group(1)), "title": html.unescape(title.group(1).strip()),
                              "author": html.unescape(author.group(1).strip()) if author else "", "summary": ""})
        if books:
            return books[:6]
    except Exception:
        pass
    data = json.loads(get("https://gutendex.com/books/?search=" + urllib.parse.quote(query), timeout=30))
    books = []
    for b in data.get("results", [])[:6]:
        author = (b.get("authors") or [{}])[0].get("name", "")
        if "," in author:  # "Doyle, Arthur Conan" -> "Arthur Conan Doyle"
            last, first = author.split(",", 1)
            author = f"{first.strip()} {last.strip()}"
        books.append({"id": b["id"], "title": b["title"], "author": author,
                      "summary": " ".join(b.get("summaries") or [])[:300]})
    return books

def book_text(book_id):
    # The book's text without Gutenberg's licence header and footer (downloaded once, then kept)
    os.makedirs(BOOKS, exist_ok=True)
    path = os.path.join(BOOKS, f"{book_id}.txt")
    if not os.path.exists(path):
        raw = get(f"https://www.gutenberg.org/ebooks/{book_id}.txt.utf-8", timeout=40).decode("utf-8", "ignore")
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")  # (Windows line endings split every line apart)
        start = re.search(r"\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", raw, re.I)
        end = re.search(r"\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG", raw, re.I)
        raw = raw[start.end() if start else 0:end.start() if end else len(raw)]
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(raw.strip())
    with open(path, encoding="utf-8") as f:
        return f.read()

def pages_of(text):
    # Split into pages at paragraph breaks, each about PAGE_CHARS long
    paragraphs = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    pages, page = [], ""
    for p in paragraphs:
        if not p:
            continue
        if page and len(page) + len(p) > PAGE_CHARS:
            pages.append(page)
            page = ""
        page += ("\n\n" if page else "") + p
    if page:
        pages.append(page)
    return pages or ["(This book has no text.)"]

def show_page(book, page):
    # Puts the page on the HUD and remembers where you are
    import showcase
    pages = pages_of(book_text(book["id"]))
    page = max(0, min(page, len(pages) - 1))
    profile["reading"] = {**book, "page": page, "pages": len(pages)}
    save_profile()
    showcase.put_on_hud({"kind": "book", "title": book["title"], "author": book.get("author", ""),
                         "page": page + 1, "pages": len(pages), "text": pages[page], "cards": [], "info": {}},
                        minutes=60)
    return pages[page], page, len(pages)

def read_book(action="open", title="", page=0):
    # Tool. action: find (search), open (a title, a number from the search, or the book you were reading),
    # next / previous / page (go to a page), read_aloud (the page's text, for the brain to read out)
    global found_books
    reading = profile.get("reading")
    if action == "find" or (action == "open" and title and not title.strip().isdigit()
                            and not (reading and title.lower() in reading["title"].lower())):
        try:
            found_books = find_books(title or "fairy tales")
        except Exception as e:
            return f"Couldn't reach the free library right now ({str(e)[:60]})."
        if not found_books:
            return (f"No free copy of '{title}'. Only old books (out of copyright) are free here; for newer "
                    "books or manga, offer the official site (open_url).")
        if action == "find":
            return "Free books found: " + "; ".join(
                f"{i}. {b['title']} by {b['author']}" + (f": {b['summary'][:120]}" if b["summary"] else "")
                for i, b in enumerate(found_books, 1)) + ". Ask which one to open."
        book = found_books[0]
    elif action == "open" and title.strip().isdigit() and found_books:
        book = found_books[min(int(title) - 1, len(found_books) - 1)]
    elif reading:
        book = reading
    else:
        return "No book open yet. Ask what they'd like to read (or search with action find)."
    if action == "open":
        start = reading["page"] if reading and reading["id"] == book["id"] else 0
    elif action == "next":
        start = book.get("page", 0) + 1
    elif action == "previous":
        start = book.get("page", 0) - 1
    elif action == "page":
        start = int(page or 1) - 1
    else:
        start = book.get("page", 0)
    try:
        text, at, total = show_page({k: book[k] for k in ("id", "title", "author")}, start)
    except Exception as e:
        return f"Couldn't load that book ({str(e)[:60]})."
    said = f"'{book['title']}' by {book['author']}, page {at + 1} of {total}, is on the HUD."
    if action == "read_aloud":
        return said + " Read this page aloud to them, naturally, word for word:\n" + text
    return said + " It starts: " + text[:200]

def turn_page(step):
    # The HUD's ‹ › buttons and arrow keys
    reading = profile.get("reading")
    if reading:
        show_page({k: reading[k] for k in ("id", "title", "author")}, reading["page"] + step)

# ---------- Typing practice ----------
PASSAGES = {
    "easy": ["The sun is warm and the sky is blue. A small bird sings on the tree near my window.",
             "I like to read books at night. My cat sleeps next to me and the room is quiet.",
             "We went to the beach and built a big sand castle. Then the waves came and took it away."],
    "medium": ["Learning to type fast is like learning music: slow and correct practice builds speed that lasts.",
               "Chennai wakes up early. Tea stalls open, buses fill up, and the smell of filter coffee is everywhere.",
               "A good programmer reads the error message first, then the code, and only then starts to change things."],
    "hard": ["Jarvis, analyse the telemetry: thrust at 87%, altitude 12,400 ft, and fuel reserves dropping by 3.5% a minute!",
             "\"Quick,\" she whispered, \"the zebra jumped over 2 lazy dogs at 9:45 PM; nobody noticed (except me).\"",
             "Debugging tip #1: if `x == null` throws, check the API response {status: 404} before blaming React."],
}

TIMED_WORDS = 400  # a timed test needs more text than anyone can type in the time

def typing_practice(level="medium", topic="", seconds=0):
    # Tool: typing practice on the HUD. seconds=0: one passage. seconds=30/60/120: a timed test with endless
    # lines and a countdown. Their own topic = text written about it.
    import showcase
    level = level if level in PASSAGES else "medium"
    seconds = int(float(seconds or 0))
    seconds = min((30, 60, 120), key=lambda s: abs(s - seconds)) if seconds > 0 else 0
    text = ""
    if topic:
        import brain
        length = "a long typing-test text of about 250 words" if seconds else "ONE typing-practice passage of 25-40 words"
        text = brain.write(f"Write {length} about the topic, plain text only, no title, no quotes around it. "
                           + {"easy": "Simple words.", "hard": "Use numbers and punctuation too."}.get(level, ""),
                           topic, seconds=15, writers=brain.QUICK_WRITERS)
        text = " ".join((text or "").split())[:2500 if seconds else 300]
    if len(text) < 40:
        text = random.choice(PASSAGES[level])
    if seconds:
        pool = PASSAGES[level][:]
        while len(text.split()) < TIMED_WORDS:  # (keep adding the level's passages in a new order)
            random.shuffle(pool)
            text += " " + " ".join(pool)
    mode = f"{seconds}s" if seconds else "passage"
    title = f"Typing test · {seconds} seconds · {level}" if seconds else f"Typing practice · {level}"
    showcase.put_on_hud({"kind": "typing", "title": title, "text": text.strip(), "level": level, "seconds": seconds,
                         "best": best_typing(mode), "cards": [], "info": {}}, minutes=30)
    best = best_typing(mode)
    start = (f"A {seconds}-second test is on the HUD; the countdown starts with their first key." if seconds
             else f"{'An' if level == 'easy' else 'A'} {level} passage is on the HUD; they just start typing (the timer starts with the first key).")
    return start + (f" Their best here: {best} words per minute." if best else " First time: no record yet.")

def best_typing(mode):
    return max((r["wpm"] for r in profile.get("typing", []) if r.get("mode", "passage") == mode), default=0)

def typing_result(wpm, accuracy, seconds, mode="passage"):
    # From the HUD when a passage or a timed test is finished: kept, and M.I.N.D says how it went
    history = profile.setdefault("typing", [])
    best = best_typing(mode)
    history.append({"wpm": wpm, "accuracy": accuracy, "seconds": seconds, "mode": mode, "at": time.strftime("%Y-%m-%d %H:%M")})
    del history[:-30]
    save_profile()
    note = " That's a new best!" if best and wpm > best else (f" Your best is {best}." if best else "")
    state.alerts.append(f"Typing done: {wpm} words per minute with {accuracy}% accuracy.{note}")

# ---------- Little games on the HUD (src/components/Games.jsx) ----------
GAMES = {"snake": "Snake", "2048": "2048", "tictactoe": "Tic-tac-toe"}

def play_game(game="snake"):
    # Tool: "Mind, let's play snake / 2048 / tic tac toe"
    import showcase
    said = str(game or "snake").lower().replace("-", "").replace(" ", "")
    game = next((g for g in GAMES if g in said), "tictactoe" if "tic" in said or "noughts" in said else "snake")
    record = profile.get("games", {}).get(game, {})
    showcase.put_on_hud({"kind": "game", "game": game, "title": GAMES[game], "best": record.get("best", 0),
                         "record": {k: record.get(k, 0) for k in ("won", "lost", "draw")}, "cards": [], "info": {}}, minutes=60)
    how = "they click a square; M.I.N.D plays the circles" if game == "tictactoe" else "arrow keys or WASD; Space starts again"
    best = f" Their best: {record['best']}." if record.get("best") else ""
    return f"{GAMES[game]} is on the HUD ({how}).{best} Say it in a few words."

def game_result(game, score, won, draw=False):
    # From the HUD at the end of a game: the record is kept; a new best is said out loud
    if game not in GAMES:
        return
    record = profile.setdefault("games", {}).setdefault(game, {})
    record["played"] = record.get("played", 0) + 1
    if game == "tictactoe":
        key = "draw" if draw else "won" if won else "lost"
        record[key] = record.get(key, 0) + 1
    else:
        old = record.get("best", 0)
        if score > old:
            record["best"] = score
            if old:
                state.alerts.append(f"New best in {GAMES[game]}: {score} (was {old})!")
    save_profile()

