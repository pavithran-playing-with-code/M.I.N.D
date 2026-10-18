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
import av
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import pyaudio
from groq import Groq
from vosk import Model, KaldiRecognizer, SetLogLevel
from memory import profile, save_profile, tamil_mode
import state
import limits

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
cloud = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0, timeout=8)  # give up on a stuck request after 8s
listeners = ThreadPoolExecutor(max_workers=2)  # English and Tamil at the same time
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
EXTRA_WAKE_WORDS = ["hi mind", "mind"]  # also always work ("mind" alone is safe: Whisper checks it was really said)

def wake_words():
    # Every phrase that wakes M.I.N.D: the one in profile.json (if it's safe) plus "hi mind".
    # One-word wake words are refused: "mind" is inside "remind", "never mind"...
    phrase = profile.get("wake_word", DEFAULT_WAKE_WORD).lower().strip(" .,!?")
    unknown = [w for w in phrase.split() if vosk_model.vosk_model_find_word(w) == -1]
    if len(phrase.split()) < 2 or unknown:
        phrase = DEFAULT_WAKE_WORD  # Vosk only knows real dictionary words
    return [phrase] + [w for w in [DEFAULT_WAKE_WORD] + EXTRA_WAKE_WORDS if w != phrase]

def wake_word():
    # The main wake word (to show and say)
    return wake_words()[0]

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
    # Waits for "mind". Returns what you said, from just before "mind" until you pause
    # (so "Mind, play a song" in one breath works), b"" if the orb was tapped,
    # or None if should_stop() says so (a reminder is due, a command was typed...).
    phrases = wake_words()
    rec = phrase_listener(phrases)
    stream = open_mic()
    state.set_status("waiting")
    print(f'Waiting for {" or ".join(repr(p) for p in phrases)}...')
    before = deque(maxlen=8)  # the last 2 seconds, so "hey mind" itself is in the recording
    try:
        while not should_stop():
            if state.take_click():
                return b""
            data = stream.read(CHUNK, exception_on_overflow=False)
            show_level(loudness(data))
            before.append(data)
            heard = check_phrase(rec, data)
            if any(p in heard.split() or p in heard for p in phrases):
                state.set_status("listening")
                return finish_recording(stream, list(before))  # keep going until you pause
        return None
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
    speech_threshold = max(np.percentile(noise, 90) * 1.5, 45)  # lower = hears quieter voices

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

# Words Whisper should expect, so it spells them right
COMMON_WORDS = ["Mind", "Tamil", "song", "YouTube", "VS Code", "Chrome", "weather", "volume", "reminder"]

def make_hint():
    # A tiny sentence with your name (so it's spelled right) plus a list of words.
    # Never things like "I live in ...": on music or noise Whisper sometimes repeats the hint
    # back as if you said it ("I live in Kishore" became fake commands). copied_hint() catches that.
    words = [profile.get("city", "")] + COMMON_WORDS
    words += list(profile.get("corrections", {}).values()) + list(profile.get("shortcuts", {}))
    who = f"{profile['real_name']} talking to Mind. " if profile.get("real_name") else ""
    return who + ", ".join(w for w in words if w)

def copied_hint(text):
    # True if Whisper just repeated the hint words instead of hearing you
    hint_words = set(re.findall(r"\w+", make_hint().lower()))
    words = re.findall(r"\w+", text.lower())
    return len(words) >= 3 and sum(w in hint_words for w in words) >= len(words) * 0.7

def language():
    # For the offline backup: English only, or detect (Tamil/English) in Tamil mode
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

def to_ogg(sound):
    # Squeeze the recording ~10x (Opus, like WhatsApp voice notes) so it uploads fast,
    # even on a slow connection (raw audio took 5.6s to send, this takes under 1s)
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="ogg") as out:
        stream = out.add_stream("libopus", rate=RATE)
        stream.bit_rate = 24000
        frame = av.AudioFrame.from_ndarray(np.frombuffer(sound, np.int16).reshape(1, -1),
                                           format="s16", layout="mono")
        frame.sample_rate = RATE
        for packet in list(stream.encode(frame)) + list(stream.encode(None)):
            out.mux(packet)
    return buffer.getvalue()

MIN_CONFIDENCE = -1.0  # below this it's probably noise, not words

def hear_as(sound, language, model):
    # One Whisper try in one language. Returns (text, confidence); higher confidence = surer.
    raw = cloud.audio.transcriptions.with_raw_response.create(
        file=("speech.ogg", to_ogg(sound)), model=model, language=language, prompt=make_hint(),
        response_format="verbose_json", temperature=0)
    limits.note(model, raw.headers)  # how much is left today (for the HUD)
    result = raw.parse()
    parts = [s for s in result.segments if not is_ghost(s)]
    seconds = sum(s["end"] - s["start"] for s in parts)
    if not parts or seconds <= 0:
        return "", -99
    confidence = sum(s["avg_logprob"] * (s["end"] - s["start"]) for s in parts) / seconds
    return " ".join(s["text"] for s in parts), confidence

def transcribe_cloud(sound):
    # You can speak English, Tamil or a mix: Whisper listens as English AND as Tamil
    # at the same time, and we keep whichever it is more sure about.
    for model in CLOUD_MODELS:
        tries = {lang: listeners.submit(hear_as, sound, lang, model) for lang in ("en", "ta")}
        heard = []
        for lang, job in tries.items():
            try:
                heard.append(job.result())
            except Exception as e:
                print(f"Cloud hearing ({model}, {lang}) failed: {str(e)[:100]}")
        if heard:
            text, confidence = max(heard, key=lambda h: h[1])
            return text if confidence >= MIN_CONFIDENCE else ""
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
        if copied_hint(text):
            print(f"(Ignored, Whisper just repeated its hint: {text})")
            return ""
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
