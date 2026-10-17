# Ears: wake word (Vosk) and speech to text (faster-whisper). Both run offline.
import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import re
import json
import numpy as np
import pyaudio
import speech_recognition as sr
from faster_whisper import WhisperModel
from vosk import Model, KaldiRecognizer, SetLogLevel
from memory import profile, save_profile

DEFAULT_WAKE_WORD = "hey mind"
RATE = 16000   # sound samples per second
CHUNK = 4000   # a quarter second of sound

print("Loading speech model...")
whisper = WhisperModel("base", device="cpu", compute_type="int8")

print("Loading wake word model...")
SetLogLevel(-1)  # hide Vosk's technical logs
vosk_model = Model(lang="en-us")  # downloads a small ~40MB model the first time
mic = pyaudio.PyAudio()
recognizer = sr.Recognizer()

# Put the wake word in profile.json so you can change it there
profile.setdefault("wake_word", DEFAULT_WAKE_WORD)
save_profile()

# ---------- Wake word ----------
def wake_word():
    phrase = profile.get("wake_word", DEFAULT_WAKE_WORD).lower().strip(" .,!?")
    # Vosk only knows real dictionary words. If one is unknown, fall back.
    unknown = [w for w in phrase.split() if vosk_model.vosk_model_find_word(w) == -1]
    if not phrase or unknown:
        print(f"Wake word model doesn't know: {', '.join(unknown)}. Using '{DEFAULT_WAKE_WORD}'.")
        return DEFAULT_WAKE_WORD
    return phrase

def open_mic():
    return mic.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                    input=True, frames_per_buffer=CHUNK)

def phrase_listener(phrases):
    # A Vosk listener that only knows these phrases; "[unk]" catches every other sound
    return KaldiRecognizer(vosk_model, RATE, json.dumps(phrases + ["[unk]"]))

def hear(rec, stream):
    # Read a quarter second of sound and return what Vosk heard so far
    data = stream.read(CHUNK, exception_on_overflow=False)
    if rec.AcceptWaveform(data):
        return json.loads(rec.Result()).get("text", "")
    return json.loads(rec.PartialResult()).get("partial", "")

def wait_for_wake(should_stop):
    # Returns True when the wake word is heard, False when should_stop() says so
    phrase = wake_word()
    rec = phrase_listener([phrase])
    stream = open_mic()
    print(f'Waiting for "{phrase}"...')
    try:
        while not should_stop():
            if phrase in hear(rec, stream):
                return True
        return False
    finally:
        # Free the mic so the command listener can use it
        stream.stop_stream()
        stream.close()

# ---------- Speech to text ----------
def fix_text(text):
    # Your own fixes, e.g. "when I say v v p I mean VVP"
    for wrong, right in profile.get("corrections", {}).items():
        text = re.sub(r"\b" + re.escape(wrong) + r"\b", right, text, flags=re.IGNORECASE)
    return text

def make_hint():
    # Words Whisper should expect, so it spells your names right
    words = ["M.I.N.D"]
    for key in ("name", "real_name", "city"):
        if profile.get(key):
            words.append(profile[key])
    words += list(profile.get("corrections", {}).values())
    words += list(profile.get("shortcuts", {}))
    return ", ".join(words)

def transcribe(audio):
    raw = audio.get_raw_data(convert_rate=RATE, convert_width=2)
    samples = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    segments, _ = whisper.transcribe(
        samples, language="en", initial_prompt=make_hint(), beam_size=1
    )
    return " ".join(s.text for s in segments).strip()

def calibrate():
    # Measure room noise once at startup (stay quiet for 1 second).
    # Doing it before every command could mistake your voice for noise.
    with sr.Microphone() as source:
        print("Measuring room noise, stay quiet...")
        recognizer.adjust_for_ambient_noise(source, duration=1)

def listen():
    # Record one sentence and turn it into text ("" if nothing was heard)
    with sr.Microphone() as source:
        print("Listening...")
        try:
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return ""
    try:
        text = fix_text(transcribe(audio)).strip(" .,!?")
        if text:
            print("You:", text)
        return text
    except Exception as e:
        print("Speech error:", e)
        return ""
