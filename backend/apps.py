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

def typing_practice(level="medium", topic=""):
    # Tool: a typing passage on the HUD (their own topic = a passage written about it)
    import showcase
    level = level if level in PASSAGES else "medium"
    text = ""
    if topic:
        import brain
        text = brain.write("Write ONE typing-practice passage of 25-40 words about the topic, plain text only, "
                           "no title, no quotes around it. " + {"easy": "Simple words.", "hard": "Use numbers and "
                           "punctuation too."}.get(level, ""), topic, seconds=12, writers=brain.QUICK_WRITERS)
        text = " ".join((text or "").split())[:300]
    if len(text) < 40:
        text = random.choice(PASSAGES[level])
    showcase.put_on_hud({"kind": "typing", "title": f"Typing practice · {level}", "text": text,
                         "level": level, "cards": [], "info": {}}, minutes=30)
    best = max((r["wpm"] for r in profile.get("typing", [])), default=0)
    return (f"{'An' if level == 'easy' else 'A'} {level} passage is on the HUD; they just start typing (the timer starts with the first key). "
            + (f"Their best so far: {best} words per minute." if best else "First time: no record yet."))

def typing_result(wpm, accuracy, seconds):
    # From the HUD when a passage is finished: kept, and M.I.N.D says how it went
    history = profile.setdefault("typing", [])
    best = max((r["wpm"] for r in history), default=0)
    history.append({"wpm": wpm, "accuracy": accuracy, "seconds": seconds, "at": time.strftime("%Y-%m-%d %H:%M")})
    del history[:-30]
    save_profile()
    note = " That's a new best!" if wpm > best and history[:-1] else (f" Your best is {best}." if best else "")
    state.alerts.append(f"Typing done: {wpm} words per minute with {accuracy}% accuracy.{note}")
