# Voice: talks with a natural Microsoft Edge voice (free, needs internet), or the
# Windows voice when offline. Goes quiet if you say "stop", say the wake word,
# or click the orb in the HUD.
import os
import re
import time
import queue
import ctypes
import asyncio
import hashlib
import tempfile
import threading
import unicodedata
import comtypes.client
import edge_tts
from ears import open_mic, close_mic, phrase_listener, hear, wake_word
from memory import profile
import state

DEFAULT_VOICE = "en-GB-RyanNeural"  # British male, very Jarvis. Change it with "voice" in profile.json
STOP_WORDS = ["stop", "quiet"]

# Finished sentences are saved here, so repeated ones ("Yes?") play instantly
CACHE_DIR = os.path.join(tempfile.gettempdir(), "mind_voice")
os.makedirs(CACHE_DIR, exist_ok=True)

# Windows voice (backup when there's no internet)
SPEAK_ASYNC = 1  # start talking and return right away, so we can listen at the same time
PURGE = 2        # cancel whatever is being said
windows_voice = comtypes.client.CreateObject("SAPI.SpVoice")

# ---------- Playing mp3 files with Windows' built-in player (no install needed) ----------
mci = ctypes.windll.winmm.mciSendStringW

speech_end = 0  # milliseconds where the words in the current file end

def play_file(path, end_seconds):
    global speech_end
    speech_end = end_seconds * 1000
    mci("close mind", None, 0, 0)
    mci(f'open "{path}" type mpegvideo alias mind', None, 0, 0)
    mci("set mind time format milliseconds", None, 0, 0)
    mci("play mind", None, 0, 0)

def mci_status(what):
    answer = ctypes.create_unicode_buffer(32)
    mci(f"status mind {what}", answer, 32, 0)
    return answer.value

def file_playing():
    # Edge adds about a second of silence at the end; treat that as finished
    position = mci_status("position")
    if position.isdigit() and int(position) >= speech_end:
        return False
    return mci_status("mode") == "playing"

def stop_file():
    mci("stop mind", None, 0, 0)
    mci("close mind", None, 0, 0)

# ---------- Making speech ----------
async def download(sentence, voice, path):
    # Gets the mp3 from Edge, plus when the last word ends (in seconds)
    talk = edge_tts.Communicate(sentence, voice, boundary="WordBoundary",
                                connect_timeout=5, receive_timeout=10)
    end = 0
    with open(path, "wb") as f:
        async for chunk in talk.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            else:
                end = max(end, (chunk["offset"] + chunk["duration"]) / 10_000_000)
    return end

def make_audio(sentence):
    # Turns one sentence into an mp3 with the Edge voice.
    # Returns (mp3 path, seconds until the words end).
    voice = profile.get("voice", DEFAULT_VOICE)
    name = hashlib.md5(f"{voice}|{sentence}".encode()).hexdigest()
    path = os.path.join(CACHE_DIR, name + ".mp3")
    end_file = path + ".end"  # remembers when the words end
    if not (os.path.exists(path) and os.path.exists(end_file)):
        temp = path + ".part"
        end = asyncio.run(download(sentence, voice, temp)) or 30  # 30 = unknown, play it all
        os.replace(temp, path)
        with open(end_file, "w") as f:
            f.write(str(end + 0.25))  # a quarter second extra so the last word isn't clipped
    with open(end_file) as f:
        return path, float(f.read())

def clean_old_audio(days=30):
    for name in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, name)
        if time.time() - os.path.getmtime(path) > days * 86400:
            os.remove(path)

clean_old_audio()

def split_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

def prepare(sentences, ready):
    # Runs in the background: makes each sentence's audio in order and hands it over.
    # If the Edge voice fails (no internet), hands over the rest for the Windows voice.
    for i, sentence in enumerate(sentences):
        try:
            ready.put(("file", make_audio(sentence)))
        except Exception as e:
            print("Edge voice failed, using Windows voice:", e)
            ready.put(("windows", " ".join(sentences[i:])))
            break
    ready.put(("done", None))

# ---------- Speaking ----------
def speak(text):
    # Says the text out loud. Returns True if you interrupted it.
    text = unicodedata.normalize("NFKC", text)  # turn odd symbols (special spaces, dashes) into normal ones
    text = re.sub(r"([a-z]{2}[.!?])(?=[A-Z])", r"\1 ", text)  # "done.Anything" -> "done. Anything"
    print("M.I.N.D:", text)
    if not text:
        return False
    state.add_message("mind", text)
    state.set_status("speaking")
    said = re.sub(r"M\.I\.N\.D\.?", "Mind", text)  # say "Mind", not "M I N D"

    # Start making the audio in the background; the first sentence plays as soon as it's ready
    ready = queue.Queue()
    threading.Thread(target=prepare, args=(split_sentences(said), ready), daemon=True).start()

    words = STOP_WORDS + [wake_word()]
    rec = phrase_listener(words)
    stream = open_mic()
    state.take_click()  # forget old clicks
    playing = None  # "file", "windows" or None
    try:
        while True:
            # Is the current piece still playing?
            if playing == "file" and not file_playing():
                playing = None
            if playing == "windows" and windows_voice.WaitUntilDone(0):
                playing = None
            # Start the next piece when the last one is finished
            if playing is None and not ready.empty():
                kind, item = ready.get()
                if kind == "done":
                    return False
                if kind == "file":
                    play_file(*item)
                else:
                    windows_voice.Speak(item, SPEAK_ASYNC)
                playing = kind
            # Listen for "stop" (also gives a short pause between sentences)
            heard = hear(rec, stream)
            if state.take_click() or any(w in heard for w in words):
                stop_file()
                windows_voice.Speak("", SPEAK_ASYNC | PURGE)
                print("(Interrupted)")
                return True
    finally:
        stop_file()
        state.set_level(0)
        close_mic(stream)
