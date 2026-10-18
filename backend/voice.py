# Voice: talks with Groq's Orpheus voice (most human; free but 100 requests a day),
# or a Microsoft Edge voice (free, no limit) when Orpheus is used up, or for Tamil,
# or the Windows voice when offline. Goes quiet if you say "stop", say the wake word,
# or click the orb in the HUD. You can also just talk over it (barge-in).
import io
import os
import re
import time
import queue
import ctypes
import asyncio
import hashlib
import tempfile
import threading
import difflib
import wave
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import comtypes.client
import edge_tts
import numpy as np
from groq import Groq, RateLimitError
import ears
from ears import open_mic, close_mic, phrase_listener, wake_words
from memory import profile
import state

# Voices. "voice" in profile.json picks the main one, e.g. "orpheus-austin" or "en-US-AndrewNeural".
EDGE_VOICE = "en-US-AndrewNeural"     # English Edge voice when Orpheus isn't available ("edge_voice" in profile.json)
TAMIL_VOICE = "ta-IN-ValluvarNeural"  # Orpheus only speaks English, so Tamil always uses Edge
ORPHEUS_MODEL = "canopylabs/orpheus-v1-english"
orpheus = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0, timeout=15)
orpheus_paused_until = 0  # when the daily Orpheus limit is used up: Edge until this time
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
# One background loop does all Edge downloads (several can run at the same time)
edge_loop = asyncio.new_event_loop()
threading.Thread(target=edge_loop.run_forever, daemon=True).start()

async def download(sentence, voice, path):
    # Gets the mp3 from Edge, plus when the last word ends (in seconds)
    talk = edge_tts.Communicate(sentence, voice, boundary="WordBoundary",
                                connect_timeout=4, receive_timeout=5)
    end = 0
    with open(path, "wb") as f:
        async for chunk in talk.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            else:
                end = max(end, (chunk["offset"] + chunk["duration"]) / 10_000_000)
    return end

TAMIL_LETTERS = re.compile(r"[஀-௿]")

def english_voice():
    # Your main voice, or the Edge voice while Orpheus's daily limit is used up
    voice = profile.get("voice", "")
    if voice.startswith("orpheus-"):
        if time.time() >= orpheus_paused_until:
            return voice
        voice = profile.get("edge_voice", "")
    return voice if voice and not voice.startswith(("ta-", "orpheus-")) else EDGE_VOICE

def voice_for(sentence):
    # Tamil letters need the Tamil voice (the English voices can't read them)
    voice = profile.get("voice", "")
    if TAMIL_LETTERS.search(sentence):
        return voice if voice.startswith("ta-") else TAMIL_VOICE
    return english_voice()

def orpheus_audio(sentence, voice, path):
    # Gets a wav from Groq's Orpheus, plus when the words end (in seconds)
    data = orpheus.audio.speech.create(model=ORPHEUS_MODEL, voice=voice.split("-", 1)[1],
                                       input=sentence, response_format="wav").read()
    with wave.open(io.BytesIO(data)) as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
        frames = w.readframes(w.getnframes())
    samples = np.frombuffer(frames[:len(frames) // 2 * 2], np.int16)
    loud = np.nonzero(np.abs(samples) > 500)[0]
    # Save it again with a correct header (Groq's says the length is unknown)
    with wave.open(path, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(frames)
    return loud[-1] / rate / channels if len(loud) else 0

def make_audio(sentence):
    # Turns one sentence into audio with the right voice.
    # Returns (audio file path, seconds until the words end).
    global orpheus_paused_until
    voice = voice_for(sentence)
    name = hashlib.md5(f"{voice}|{sentence}".encode()).hexdigest()
    path = os.path.join(CACHE_DIR, name + (".wav" if voice.startswith("orpheus-") else ".mp3"))
    end_file = path + ".end"  # remembers when the words end
    if not (os.path.exists(path) and os.path.exists(end_file)):
        temp = path + ".part"
        if voice.startswith("orpheus-"):
            try:
                end = orpheus_audio(sentence, voice, temp) or 30
            except RateLimitError as e:
                wait = float(e.response.headers.get("retry-after", 3600))
                orpheus_paused_until = time.time() + wait
                print(f"Orpheus voice used up for now, using Edge for the next {wait / 3600:.1f} hours")
                return make_audio(sentence)  # now uses the Edge voice
        else:
            # Runs on the shared background loop; give up after 6 seconds (then the Windows voice takes over)
            job = asyncio.run_coroutine_threadsafe(download(sentence, voice, temp), edge_loop)
            end = job.result(timeout=6) or 30  # 30 = unknown, play it all
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
    pieces = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if english_voice().startswith("orpheus-"):
        # Orpheus has a daily limit, so use few requests: the first sentence alone
        # (so it starts sooner), then the rest together. Tamil stays separate (it uses Edge).
        merged = pieces[:1]
        for piece in pieces[1:]:
            same = len(merged) > 1 and not TAMIL_LETTERS.search(piece + merged[-1])
            if same:
                merged[-1] += " " + piece
            else:
                merged.append(piece)
        return merged
    # Making audio takes longer for longer text, so cut a long first sentence at its
    # first comma: the short first piece starts playing sooner while the rest is made.
    if pieces and len(pieces[0].split()) > 6:
        first, comma, rest = pieces[0].partition(", ")
        if comma and rest:
            pieces[0:1] = [first + ",", rest]
    return pieces

def warm_up(lines):
    # Make the audio for everyday lines in the background, so they play instantly later
    # (not for Orpheus: it would use up the daily limit; its lines get saved as they're used)
    if english_voice().startswith("orpheus-"):
        return
    def work():
        for line in lines:
            for piece in split_sentences(re.sub(r"M\.I\.N\.D\.?", "Mind", line)):
                try:
                    make_audio(piece)
                except Exception:
                    return  # no internet: never mind
    threading.Thread(target=work, daemon=True).start()

def prepare(sentences, ready):
    # Runs in the background: makes all the pieces' audio at the same time,
    # and hands them over in order. If the Edge voice fails (no internet),
    # hands over the rest for the Windows voice.
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(make_audio, s) for s in sentences]
        for i, (sentence, job) in enumerate(zip(sentences, jobs)):
            try:
                ready.put(("file", job.result(), sentence))
            except Exception as e:
                print("Edge voice failed, using Windows voice:", e)
                rest = " ".join(sentences[i:])
                ready.put(("windows", rest, rest))
                break
    ready.put(("done", None, ""))

# ---------- Talking over M.I.N.D (barge-in) ----------
# While M.I.N.D talks, the mic also hears M.I.N.D's own voice from the speakers (echo).
# So you only "break in" when the mic is clearly louder than that echo for a moment.
echo_level = 0.0   # how loud M.I.N.D's own voice sounds in the mic (learned while talking)
echo_known = False # becomes True after the first sentence (the startup greeting)
BARGE_STEPS = 3    # 0.3 seconds of loud sound = you're talking

def barge_threshold():
    return max(ears.speech_threshold * 1.5, echo_level * 1.6)

def is_echo(heard, sentence):
    # True if what was heard is just M.I.N.D's own sentence coming back through the mic
    if not heard:
        return True
    heard_words = re.findall(r"[a-z']+", heard.lower())
    said_words = set(re.findall(r"[a-z']+", sentence.lower()))
    new_words = [w for w in heard_words if w not in said_words]
    similar = difflib.SequenceMatcher(None, heard.lower(), sentence.lower()).ratio()
    return similar > 0.5 or len(new_words) <= len(heard_words) * 0.3

# ---------- Speaking ----------
def pause(playing):
    if playing == "file":
        mci("pause mind", None, 0, 0)
    else:
        windows_voice.Pause()

def resume(playing):
    if playing == "file":
        mci("resume mind", None, 0, 0)
    else:
        windows_voice.Resume()

def speak(text):
    # Says the text out loud. Returns True if you interrupted it.
    # If you talk over it, what you said is saved in state.heard for the next turn.
    global echo_level, echo_known
    text = unicodedata.normalize("NFKC", text)  # turn odd symbols (special spaces, dashes) into normal ones
    text = re.sub(r"([a-z]{2}[.!?])(?=[A-Z])", r"\1 ", text)  # "done.Anything" -> "done. Anything"
    print("M.I.N.D:", text)
    if not text:
        return False
    shown = False  # the text appears in the HUD when the voice starts, so they match
    said = re.sub(r"M\.I\.N\.D\.?", "Mind", text)  # say "Mind", not "M I N D"

    # Start making the audio in the background; the first sentence plays as soon as it's ready
    ready = queue.Queue()
    threading.Thread(target=prepare, args=(split_sentences(said), ready), daemon=True).start()

    # Words that make M.I.N.D go quiet, except ones it's saying itself ("just say hey mind...")
    words = [w for w in STOP_WORDS + wake_words() if w not in said.lower()]
    rec = phrase_listener(words)
    stream = open_mic()
    state.take_click()  # forget old clicks
    playing = None      # "file", "windows" or None
    sentence = ""       # the sentence being said right now
    recent = deque(maxlen=BARGE_STEPS + 2)  # the last half second of mic sound
    loud = 0
    try:
        while True:
            # Is the current piece still playing?
            was_playing = playing
            if playing == "file" and not file_playing():
                playing = None
            if playing == "windows" and windows_voice.WaitUntilDone(0):
                playing = None
            if was_playing and playing is None and echo_level > 0:
                echo_known = True  # learned from one whole sentence
            # Start the next piece when the last one is finished
            if playing is None and not ready.empty():
                kind, item, sentence = ready.get()
                if kind == "done":
                    return False
                if kind == "file":
                    play_file(*item)
                else:
                    windows_voice.Speak(item, SPEAK_ASYNC)
                playing = kind
                if not shown:
                    state.add_message("mind", text)
                    state.set_status("speaking")
                    shown = True

            # Listen a tenth of a second
            data = stream.read(ears.STEP, exception_on_overflow=False)
            volume = ears.loudness(data)
            ears.show_level(volume)
            recent.append(data)

            # "stop", the wake word, or an orb click: go quiet
            heard = ears.check_phrase(rec, data)
            if state.take_click() or any(w in heard for w in words):
                print("(Interrupted)")
                return True

            if playing is None:
                continue
            if not echo_known:
                # First sentence ever (the startup greeting): just learn how loud the echo is
                echo_level = max(volume, echo_level)
                continue
            if volume < barge_threshold():
                echo_level = max(volume, echo_level * 0.995)  # learn the echo (slowly forgets)
                loud = 0
                continue
            loud += 1
            if loud < BARGE_STEPS:
                continue

            # Sounds like you're talking: pause, record you, and check it wasn't the echo
            pause(playing)
            state.set_status("listening")
            heard_text = ears.to_text(ears.finish_recording(stream, list(recent)))
            if is_echo(heard_text, sentence):
                echo_level = max(echo_level, max(ears.loudness(d) for d in recent))
                print("(Just my own echo, carrying on)")
                state.set_status("speaking")
                resume(playing)
                loud = 0
                continue
            print("(You talked over me)")
            state.add_message("you", heard_text)
            state.heard.append(heard_text)
            return True
    finally:
        if not shown:
            state.add_message("mind", text)  # interrupted before it started: still show the text
        stop_file()
        windows_voice.Speak("", SPEAK_ASYNC | PURGE)
        state.set_level(0)
        close_mic(stream)
