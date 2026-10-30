# Finding things you can't name:
# - a song you hum, whistle or sing a bit of: a free Gemini model listens to the clip and names it,
#   and lyrics it heard are checked with a web search (live_brain's identify_song records the clip)
# - a video you describe ("the one where a guy builds a pool in the jungle"): turned into a few YouTube
#   searches, the best matches picked by the brain and shown on the HUD as clickable thumbnails
import io
import os
import re
import json
import wave
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus

# ---------- Songs ----------
EARS = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.5-flash-lite"]  # models that can listen to sound
NAME_THAT_SONG = """Someone is humming, whistling or singing part of a song into their laptop mic (it may be English,
Tamil, Hindi or any language; film songs count). Identify the song from the melody, rhythm and any words.
Reply with JSON only:
{"heard": "the words you can make out, or 'just humming'",
 "guesses": [{"title": "...", "artist": "...", "from": "film or album, if any", "sure": 0-100}]}
Give up to 3 guesses, best first. Be honest: low "sure" when it's only a vague match; [] if you have no idea."""

def to_wav(sound, rate=16000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(sound)
    return buffer.getvalue()

def name_that_song(sound, rate=16000):
    # sound = the recorded clip (16-bit mono). Returns what to tell the brain.
    from google import genai
    from google.genai import types
    if len(sound) < rate * 2 * 2:
        return "The clip was too short (under 2 seconds). Ask them to hum or sing it again, a bit longer."
    # Whisper (M.I.N.D's normal hearing) listens at the same time: it catches sung WORDS reliably, even when the
    # melody model is busy or weak (a small model once called clear lyrics "just humming")
    import ears
    lyrics = ThreadPoolExecutor(1).submit(lambda: ears.to_text(sound if rate == 16000 else b"", show=False))
    # (12 s per model at most: an overloaded model once just hung)
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options=types.HttpOptions(timeout=12000))
    answer = ""
    for model in EARS:
        try:
            reply = client.models.generate_content(model=model, contents=[
                types.Part.from_bytes(data=to_wav(sound, rate), mime_type="audio/wav"), NAME_THAT_SONG])
            answer = reply.text or ""
            if answer.strip():
                print(f"  (listened with {model})")
                break
        except Exception as e:
            print(f"  (song ears: {model} failed: {str(e)[:80]})")
    found = re.search(r"\{.*\}", answer, re.S)
    try:
        result = json.loads(found.group(0), strict=False) if found else {}
    except ValueError:
        result = {}
    try:
        whisper = (lyrics.result(timeout=15) or "").strip()
    except Exception:
        whisper = ""
    heard = str(result.get("heard", "")).strip()
    if len(re.findall(r"\w+", whisper)) >= 3 and len(whisper) > len(heard if "humming" not in heard.lower() else ""):
        heard = whisper  # (Whisper's words win: it's made for words)
    if not result and not heard:
        return "Couldn't work out the song right now (the listening models are busy). Say so and offer to try again."
    guesses = [g for g in result.get("guesses", []) if isinstance(g, dict) and g.get("title")][:3]
    words = [w for w in re.findall(r"\w+", heard) if len(w) > 2]
    humming = len(words) < 3 or "humming" in heard.lower()
    if humming:
        # A melody alone is often matched to the wrong song with high confidence (a hummed "Happy Birthday"
        # came back as a Hindi film song, "95% sure"), so humming-only guesses are never more than a maybe
        for g in guesses:
            try:
                g["sure"] = min(int(g.get("sure") or 0), 40)
            except (TypeError, ValueError):
                g["sure"] = 30
    lines = [f"Heard: {heard or 'nothing clear'}."]
    if guesses:
        lines.append("Guesses: " + "; ".join(
            f"{g['title']}" + (f" by {g['artist']}" if g.get("artist") else "") + (f" ({g['from']})" if g.get("from") else "")
            + f", {g.get('sure', '?')}% sure" for g in guesses))
    if not humming:
        # Words it heard are a strong clue: what YouTube finds for them (a song's lyrics find the song)
        try:
            found = youtube_results(heard[:100], 4)
            if found:
                lines.append("YouTube results for those words: " + "; ".join(t for _, t in found))
        except Exception:
            pass
        lines.append("Tell them your best guess (the words and the YouTube results agreeing = sure); offer to play "
                     "it (play_youtube).")
    else:
        lines.append("Only humming: this is a GUESS. Say so honestly and ask them to sing a line with words to be "
                     "sure; offer to play the guess if they think it's right.")
    return "\n".join(lines)

# ---------- Videos ----------
last_found = []  # the videos shown last ("play the second one")

def youtube_results(query, count=8):
    # [(video id, title)] for a YouTube search, top first (the results page, no key needed)
    page = urllib.request.Request("https://www.youtube.com/results?search_query=" + quote_plus(query),
                                  headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"})
    html = urllib.request.urlopen(page, timeout=8).read().decode("utf-8", "ignore")
    found = []
    for video, title in re.findall(r'"videoId":"([\w-]{11})","thumbnail".*?"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"', html):
        try:
            title = json.loads(f'"{title}"')
        except ValueError:
            pass
        if video not in [v for v, _ in found]:
            found.append((video, title))
        if len(found) >= count:
            break
    return found

SEARCHES = """They're looking for a YouTube video they can only describe. Write 3 different short YouTube search
queries that would find it (the likely title words, the channel or creator if you can guess it, key details).
Reply with JSON only: {"searches": ["...", "...", "..."]}"""
PICK = """They described a video. From the search results below, pick the ones that really match the description
(up to 4, best first). Reply with JSON only: {"picks": [{"id": "video id", "why": "a few words"}]}
Use [] if none really match."""

def find_video(about):
    description = about
    # Tool: a video they describe -> the best matches on the HUD (click one, or "play the second one")
    import brain
    import showcase
    global last_found
    wanted = re.search(r"\{.*\}", brain.write(SEARCHES, description, seconds=12, writers=brain.QUICK_WRITERS) or "", re.S)
    try:
        searches = json.loads(wanted.group(0), strict=False)["searches"][:3] if wanted else []
    except (ValueError, KeyError, TypeError):
        searches = []
    searches = [str(s) for s in searches if s] or [description]
    with ThreadPoolExecutor(3) as pool:
        lists = list(pool.map(lambda q: youtube_results(q, 6), searches))
    candidates = {}
    for results in lists:
        for video, title in results:
            candidates.setdefault(video, title)
    if not candidates:
        return "YouTube didn't answer. Offer to open a YouTube search instead (open_url)."
    listing = "\n".join(f"{v}: {t}" for v, t in candidates.items())
    picked = re.search(r"\{.*\}", brain.write(PICK, f"Description: {description}\n\nResults:\n{listing}",
                                             seconds=12, writers=brain.QUICK_WRITERS) or "", re.S)
    try:
        picks = [p for p in json.loads(picked.group(0), strict=False)["picks"] if p.get("id") in candidates][:4]
    except (ValueError, KeyError, TypeError, AttributeError):
        picks = [{"id": v, "why": ""} for v in list(candidates)[:4]]  # (the picker failed: the top results)
    if not picks:
        return ("No video really matches. Searched: " + "; ".join(searches)
                + ". Ask for one more detail (who's in it, roughly when, the channel).")
    last_found = [(p["id"], candidates[p["id"]]) for p in picks]
    cards = [{"name": candidates[p["id"]][:90], "note": str(p.get("why", ""))[:120],
              "url": f"https://i.ytimg.com/vi/{p['id']}/hqdefault.jpg",
              "page": f"https://www.youtube.com/watch?v={p['id']}"} for p in picks]
    showcase.put_on_hud({"kind": "pictures", "title": "Videos like that", "info": {}, "cards": cards})
    return ("Best matches, now on the HUD (they can click one): " + "; ".join(
        f"{i}. {candidates[p['id']]} ({p.get('why', '')}) https://www.youtube.com/watch?v={p['id']}"
        for i, p in enumerate(picks, 1)) + ". To play one: open_url with its link.")
