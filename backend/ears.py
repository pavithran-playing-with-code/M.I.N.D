# Ears: wake word (Vosk, offline) and speech to text
# (Groq's free Whisper in the cloud: fast and accurate; local Whisper as a backup when offline).
import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import re
import json
import time
import numpy as np
import pyaudio
import speech_recognition as sr
from groq import Groq
from vosk import Model, KaldiRecognizer, SetLogLevel
from memory import profile, save_profile

DEFAULT_WAKE_WORD = "hey mind"
RATE = 16000   # sound samples per second
CHUNK = 4000   # a quarter second of sound

# Cloud hearing models, tried in order (both free on Groq)
CLOUD_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]
cloud = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0)
local_whisper = None  # only loaded if the cloud fails (saves RAM and startup time)

print("Loading wake word model...")
SetLogLevel(-1)  # hide Vosk's technical logs
vosk_model = Model(lang="en-us")  # downloads a small ~40MB model the first time
mic = pyaudio.PyAudio()
recognizer = sr.Recognizer()
recognizer.pause_threshold = 0.6  # seconds of silence that mean "I'm done talking" (raise if it cuts you off)

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
    # A short sentence that tells Whisper who's talking, so it spells names right
    hint = "Talking to my assistant Mind."
    if profile.get("real_name"):
        hint += f" I'm {profile['real_name']}."
    if profile.get("city"):
        hint += f" I live in {profile['city']}."
    words = list(profile.get("corrections", {}).values()) + list(profile.get("shortcuts", {}))
    if words:
        hint += " Words I use: " + ", ".join(words) + "."
    return hint

def transcribe_cloud(audio):
    wav = audio.get_wav_data(convert_rate=RATE, convert_width=2)
    for model in CLOUD_MODELS:
        try:
            result = cloud.audio.transcriptions.create(
                file=("speech.wav", wav), model=model, language="en",
                prompt=make_hint(), response_format="verbose_json", temperature=0)
            # Skip parts that are probably just noise, not speech
            return " ".join(s["text"] for s in result.segments if s["no_speech_prob"] < 0.6)
        except Exception as e:
            print(f"Cloud hearing ({model}) failed: {e}")
    return None

def transcribe_offline(audio):
    global local_whisper
    if local_whisper is None:
        print("No internet hearing, loading offline speech model...")
        from faster_whisper import WhisperModel
        local_whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
    raw = audio.get_raw_data(convert_rate=RATE, convert_width=2)
    samples = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    segments, _ = local_whisper.transcribe(samples, language="en", initial_prompt=make_hint(), beam_size=1)
    return " ".join(s.text for s in segments)

def transcribe(audio):
    text = transcribe_cloud(audio)
    if text is None:
        text = transcribe_offline(audio)
    return text.strip()

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
        start = time.time()
        text = fix_text(transcribe(audio)).strip(" .,!?")
        if text:
            print(f"You: {text}   (heard in {time.time() - start:.1f}s)")
        return text
    except Exception as e:
        print("Speech error:", e)
        return ""
