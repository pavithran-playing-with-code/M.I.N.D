# Ears: wake word (Vosk, offline) and speech to text
# (Groq's free Whisper in the cloud: fast and accurate; local Whisper as a backup when offline).
import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import io
import re
import json
import time
import wave
from collections import deque
import numpy as np
import pyaudio
from groq import Groq
from vosk import Model, KaldiRecognizer, SetLogLevel
from memory import profile, save_profile, tamil_mode
import state

DEFAULT_WAKE_WORD = "hey mind"
RATE = 16000   # sound samples per second
CHUNK = 4000   # a quarter second of sound (for Vosk)
STEP = 1600    # a tenth of a second of sound (for recording you)

# Recording settings (in seconds)
PAUSE = 0.6          # silence that means "I'm done talking" (raise if it cuts you off)
MIN_SPEECH = 0.3     # shorter sounds are clicks/noise, not speech
START_TIMEOUT = 8    # give up if you don't start talking
MAX_LENGTH = 15      # longest sentence

# Cloud hearing models, tried in order (both free on Groq)
CLOUD_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]
cloud = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0)
local_whisper = None  # only loaded if the cloud fails (saves RAM and startup time)

# Whisper sometimes "hears" these in plain noise
GHOST_PHRASES = {"thank you", "thanks for watching", "thank you for watching", "you", "bye"}

print("Loading wake word model...")
SetLogLevel(-1)  # hide Vosk's technical logs
vosk_model = Model(lang="en-us")  # downloads a small ~40MB model the first time
mic = pyaudio.PyAudio()
speech_threshold = 60  # how loud speech must be; set by calibrate()

# Put the wake word in profile.json so you can change it there
profile.setdefault("wake_word", DEFAULT_WAKE_WORD)
save_profile()

def open_mic():
    return mic.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                    input=True, frames_per_buffer=CHUNK)

def close_mic(stream):
    stream.stop_stream()
    stream.close()

def loudness(data):
    samples = np.frombuffer(data, np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(samples ** 2)))

def show_level(volume):
    # Tell the HUD how loud the mic is (0 to 1), so the orb reacts to your voice
    state.set_level(min(volume / (speech_threshold * 6), 1.0))

# ---------- Wake word ----------
def wake_word():
    phrase = profile.get("wake_word", DEFAULT_WAKE_WORD).lower().strip(" .,!?")
    # Vosk only knows real dictionary words. If one is unknown, fall back.
    unknown = [w for w in phrase.split() if vosk_model.vosk_model_find_word(w) == -1]
    if not phrase or unknown:
        print(f"Wake word model doesn't know: {', '.join(unknown)}. Using '{DEFAULT_WAKE_WORD}'.")
        return DEFAULT_WAKE_WORD
    return phrase

def phrase_listener(phrases):
    # A Vosk listener that only knows these phrases; "[unk]" catches every other sound
    return KaldiRecognizer(vosk_model, RATE, json.dumps(phrases + ["[unk]"]))

def check_phrase(rec, data):
    # Give Vosk a piece of sound and return what it heard so far
    if rec.AcceptWaveform(data):
        return json.loads(rec.Result()).get("text", "")
    return json.loads(rec.PartialResult()).get("partial", "")

def hear(rec, stream):
    # Read a quarter second of sound and return what Vosk heard so far
    data = stream.read(CHUNK, exception_on_overflow=False)
    show_level(loudness(data))
    return check_phrase(rec, data)

def wait_for_wake(should_stop):
    # Returns True when the wake word is heard or the orb is clicked,
    # False when should_stop() says so (a reminder is due, or a command was typed)
    phrase = wake_word()
    rec = phrase_listener([phrase])
    stream = open_mic()
    state.set_status("waiting")
    print(f'Waiting for "{phrase}"...')
    try:
        while not should_stop():
            if state.take_click() or phrase in hear(rec, stream):
                return True
        return False
    finally:
        state.set_level(0)
        close_mic(stream)  # free the mic for the next listener

# ---------- Recording you ----------
def calibrate():
    # Measure room noise once at startup (stay quiet for 1 second)
    global speech_threshold
    print("Measuring room noise, stay quiet...")
    stream = open_mic()
    try:
        noise = [loudness(stream.read(STEP, exception_on_overflow=False)) for _ in range(10)]
    finally:
        close_mic(stream)
    # Speech must be clearly louder than the noisiest moments of the room
    speech_threshold = max(np.percentile(noise, 90) * 2, 60)

def record(should_stop):
    # Records one sentence. Returns the sound, b"" if nobody spoke,
    # or None if should_stop() said stop (e.g. a command was typed in the HUD).
    stream = open_mic()
    state.set_status("listening")
    print("Listening...")
    before = deque(maxlen=3)  # keep a moment before you start, so the first word isn't cut
    frames, loud, quiet, waited = [], 0, 0, 0
    try:
        while True:
            if should_stop():
                return None
            data = stream.read(STEP, exception_on_overflow=False)
            volume = loudness(data)
            show_level(volume)
            is_loud = volume > speech_threshold

            if not frames:  # still waiting for you to start
                before.append(data)
                if is_loud:
                    frames, loud, quiet = list(before), 1, 0
                else:
                    waited += 1
                    if waited * 0.1 >= START_TIMEOUT:
                        return b""
                continue

            frames.append(data)
            if is_loud:
                loud += 1
                quiet = 0
            else:
                quiet += 1
            if quiet * 0.1 >= PAUSE or len(frames) * 0.1 >= MAX_LENGTH:
                if loud * 0.1 >= MIN_SPEECH:
                    return b"".join(frames)
                frames = []  # just a click or bump, keep waiting
    finally:
        state.set_level(0)
        close_mic(stream)

def finish_recording(stream, frames):
    # You've already started talking (frames so far): keep recording until you pause
    quiet = 0
    while quiet * 0.1 < PAUSE and len(frames) * 0.1 < MAX_LENGTH:
        data = stream.read(STEP, exception_on_overflow=False)
        volume = loudness(data)
        show_level(volume)
        frames.append(data)
        quiet = 0 if volume > speech_threshold else quiet + 1
    return b"".join(frames)

# ---------- Speech to text ----------
def fix_text(text):
    # Your own fixes, e.g. "when I say v v p I mean VVP"
    for wrong, right in profile.get("corrections", {}).items():
        text = re.sub(r"\b" + re.escape(wrong) + r"\b", right, text, flags=re.IGNORECASE)
    return text

def make_hint():
    # A short sentence that tells Whisper who's talking, so it spells names right
    hint = "Talking to my assistant Mind."
    if profile.get("real_name"):
        hint += f" I'm {profile['real_name']}."
    if profile.get("city"):
        hint += f" I live in {profile['city']}."
    words = list(profile.get("corrections", {}).values()) + list(profile.get("shortcuts", {}))
    if words:
        hint += " Words I use: " + ", ".join(words) + "."
    if tamil_mode():
        hint += " நான் தமிழிலும் English-லும் பேசுவேன்."  # "I speak Tamil and English"
    return hint

def language():
    # English mode: tell Whisper it's English. Tamil mode: let it detect (Tamil, English or a mix).
    return None if tamil_mode() else "en"

def to_wav(sound):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(sound)
    return buffer.getvalue()

def is_ghost(segment):
    # True if this part is probably noise, not you
    words = re.sub(r"[^a-z ]", "", segment["text"].lower()).strip()
    if segment["no_speech_prob"] >= 0.6:
        return True
    return words in GHOST_PHRASES and (segment["no_speech_prob"] > 0.1 or segment["avg_logprob"] < -0.5)

def transcribe_cloud(sound):
    lang = {"language": language()} if language() else {}
    for model in CLOUD_MODELS:
        try:
            result = cloud.audio.transcriptions.create(
                file=("speech.wav", to_wav(sound)), model=model, **lang,
                prompt=make_hint(), response_format="verbose_json", temperature=0)
            return " ".join(s["text"] for s in result.segments if not is_ghost(s))
        except Exception as e:
            print(f"Cloud hearing ({model}) failed: {e}")
    return None

def transcribe_offline(sound):
    # English-only model in English mode, the all-languages one in Tamil mode
    global local_whisper
    name = "base" if tamil_mode() else "base.en"
    if local_whisper is None or local_whisper[0] != name:
        print("No internet hearing, loading offline speech model...")
        from faster_whisper import WhisperModel
        local_whisper = (name, WhisperModel(name, device="cpu", compute_type="int8"))
    samples = np.frombuffer(sound, np.int16).astype(np.float32) / 32768.0
    segments, _ = local_whisper[1].transcribe(samples, language=language(), initial_prompt=make_hint(), beam_size=1)
    return " ".join(s.text for s in segments)

def transcribe(sound):
    text = transcribe_cloud(sound)
    if text is None:
        text = transcribe_offline(sound)
    return text.strip()

def to_text(sound):
    # Recorded sound -> cleaned-up text ("" if nothing useful)
    try:
        start = time.time()
        text = fix_text(transcribe(sound)).strip(" .,!?")
        if text:
            print(f"You: {text}   (heard in {time.time() - start:.1f}s)")
        return text
    except Exception as e:
        print("Speech error:", e)
        return ""

def listen(should_stop=lambda: False):
    # Hear one sentence and turn it into text.
    # Returns "" if nothing was heard, None if should_stop() interrupted.
    sound = record(should_stop)
    if not sound:
        return sound
    state.set_status("thinking")
    text = to_text(sound)
    if text:
        state.add_message("you", text)
    return text
