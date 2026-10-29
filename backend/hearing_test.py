# Hearing test: how well does M.I.N.D understand you? (real numbers instead of guessing)
#   1. Turn M.I.N.D off first (it would hear "Mind, ..." and act on it).
#   2. Record:  venv\Scripts\python.exe hearing_test.py record            (laptop mic)
#               venv\Scripts\python.exe hearing_test.py record airdopes   (a mic whose name has "airdopes")
#   3. Score:   venv\Scripts\python.exe hearing_test.py score
# Recordings are saved in backend/hearing_test/<mic>/ (git-ignored) so every future change
# to the ears can be scored on the same clips.
import os
import re
import sys
import json
import time
import wave
import difflib
from collections import deque
import numpy as np
import pyaudio
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
FOLDER = os.path.join(os.path.dirname(__file__), "hearing_test")
RATE, STEP = 16000, 1600  # same as ears.py: 16 kHz, 0.1 s steps

# Your real kind of commands (including ones Whisper got wrong before)
SENTENCES = [
    "Mind, open WhatsApp",
    "Mind, fix my grammar",
    "Mind, pause the song",
    "Mind, open the HUD",
    "Mind, play Rathinamo song",
    "Mind, open the dfresh project",
    "Mind, what's the weather today",
    "Mind, turn the volume down a little",
    "Mind, remind me to drink water in ten minutes",
    "Mind, close the YouTube tab",
    "Mind, what time is it",
    "Mind, how is my battery",
    "Mind, play some lofi music",
    "Mind, send hello to Jenny on WhatsApp",
    "Mind, take a screenshot and send it to my phone",
    "Mind, create an animation of a dog and a cat",
    "Mind, is Claude done with my prompt",
    "Mind, show me the best keyboards under two thousand rupees",
    "Mind, lock my laptop",
    "Mind, go offline",
]

# ---------- Recording ----------
def loudness(data):
    samples = np.frombuffer(data, np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(samples ** 2)))

def find_mic(audio, name):
    # The input device whose name contains `name` ("" = Windows' default mic)
    if not name:
        return None, audio.get_default_input_device_info()["name"]
    for i in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0 and name.lower() in info["name"].lower():
            return i, info["name"]
    sys.exit(f"No mic with '{name}' in its name.")

def record_one(stream, threshold):
    # Waits for you to talk, stops after 1 s of quiet (like M.I.N.D does)
    before, frames, quiet, talking = deque(maxlen=3), [], 0, False
    for _ in range(int(15 / 0.1)):
        data = stream.read(STEP, exception_on_overflow=False)
        loud = loudness(data) > threshold
        if not talking:
            before.append(data)
            if loud:
                talking, frames = True, list(before)
            continue
        frames.append(data)
        quiet = 0 if loud else quiet + 1
        if quiet >= 10:
            break
    return b"".join(frames)

def record(mic_name):
    audio = pyaudio.PyAudio()
    index, full_name = find_mic(audio, mic_name)
    folder = os.path.join(FOLDER, mic_name or "laptop")
    os.makedirs(folder, exist_ok=True)
    stream = audio.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True,
                        frames_per_buffer=STEP, input_device_index=index)
    print(f"Mic: {full_name}\nStay quiet for 1 second...")
    noise = [loudness(stream.read(STEP, exception_on_overflow=False)) for _ in range(10)]
    threshold = max(np.percentile(noise, 90) * 1.5, 35)
    print("Now read each line in your normal voice, like you'd talk to M.I.N.D.\n")
    for n, sentence in enumerate(SENTENCES, 1):
        input(f"[{n}/{len(SENTENCES)}] Press Enter, then say:  {sentence}")
        stream.read(stream.get_read_available(), exception_on_overflow=False)  # drop the Enter key sound
        sound = record_one(stream, threshold)
        with wave.open(os.path.join(folder, f"{n:02d}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(sound)
        print(f"   got {len(sound) / 2 / RATE:.1f} s")
    stream.close()
    with open(os.path.join(folder, "sentences.json"), "w", encoding="utf-8") as f:
        json.dump({"mic": full_name, "sentences": SENTENCES}, f, indent=1)
    print(f"\nSaved in {folder}. Now tell Claude, or run: hearing_test.py score")

# ---------- Scoring ----------
def words(text):
    return re.findall(r"[a-z0-9']+", text.lower().replace("whats app", "whatsapp"))

def accuracy(said, heard):
    # Share of the words you said that came out right (in order)
    a, b = words(said), words(heard)
    match = difflib.SequenceMatcher(None, a, b)
    return sum(block.size for block in match.get_matching_blocks()) / max(len(a), len(b), 1)

def score():
    from groq import Groq, RateLimitError
    sys.path.insert(0, os.path.dirname(__file__))
    import ears  # the real M.I.N.D ears (its hint and its ogg squeezing)
    cloud = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0, timeout=15)
    full_hint = ears.make_hint()
    # Ways to ask Whisper, to compare. "now" = exactly what M.I.N.D does today.
    ways = {
        "now (ogg + long hint)": (True, full_hint),
        "ogg + short hint": (True, "Pavithran talking to Mind."),
        "ogg + no hint": (True, None),
        "wav + short hint": (False, "Pavithran talking to Mind."),
    }
    for mic in sorted(os.listdir(FOLDER)):
        folder = os.path.join(FOLDER, mic)
        info = json.load(open(os.path.join(folder, "sentences.json"), encoding="utf-8"))
        print(f"\n===== Mic: {info['mic']} =====")
        totals = {}
        for name, (squeeze, hint) in ways.items():
            scores, wrong = [], []
            for n, said in enumerate(info["sentences"], 1):
                sound = open(os.path.join(folder, f"{n:02d}.wav"), "rb").read()[44:]
                audio = ("speech.ogg", ears.to_ogg(sound)) if squeeze else ("speech.wav", ears.to_wav(sound))
                while True:
                    try:
                        result = cloud.audio.transcriptions.create(
                            file=audio, model="whisper-large-v3", language="en",
                            prompt=hint, temperature=0)
                        break
                    except RateLimitError as e:
                        time.sleep(float(e.response.headers.get("retry-after", 10)) + 1)
                heard = result.text.strip()
                scores.append(accuracy(said, heard))
                if scores[-1] < 1:
                    wrong.append(f"     {said!r:58} -> {heard!r}")
                time.sleep(3.1)  # free limit: 20 a minute
            totals[name] = (sum(s == 1 for s in scores), 100 * sum(scores) / len(scores))
            print(f"\n  {name}: {totals[name][0]}/{len(scores)} perfect, {totals[name][1]:.0f}% of words right")
            print("\n".join(wrong) if wrong else "     (all perfect)")
        print("\n  Summary:")
        for name, (perfect, percent) in totals.items():
            print(f"    {name:24} {perfect:2}/{len(SENTENCES)} perfect   {percent:3.0f}% words")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "record":
        record(sys.argv[2] if len(sys.argv) > 2 else "")
    elif len(sys.argv) > 1 and sys.argv[1] == "score":
        score()
    else:
        print(__doc__ or "Use: hearing_test.py record [mic name]  |  hearing_test.py score")
