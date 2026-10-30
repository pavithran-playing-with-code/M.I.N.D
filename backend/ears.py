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
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import pyaudio
from groq import Groq, RateLimitError
from vosk import Model, KaldiRecognizer, SetLogLevel
from memory import profile, save_profile, tamil_mode
import state
import limits

DEFAULT_WAKE_WORD = "hey mind"
RATE = 16000   # sound samples per second
CHUNK = 4000   # a quarter second of sound (for Vosk)
STEP = 1600    # a tenth of a second of sound (for recording you)

# Recording settings (in seconds)
# People pause between sentences, so a short pause doesn't end your turn. After PAUSE, M.I.N.D
# already starts turning your words into text (so short commands stay fast), but it only answers
# once you've been quiet for DONE_PAUSE (or MORE_PAUSE if you stopped on "and", "then", "to"...).
# Start talking again and it throws that early guess away and keeps listening.
PAUSE = 0.6          # a pause this long: start working out what you said
DONE_PAUSE = 1.0     # this much quiet after a finished sentence = your turn is over
MORE_PAUSE = 2.0     # ...after an unfinished one ("open dai and", "remind me to")
MIN_SPEECH = 0.3     # shorter sounds are clicks/noise, not speech
START_TIMEOUT = 8    # give up if you don't start talking
MAX_LENGTH = 45      # longest turn (several sentences)

# Last words that mean you're not finished yet (English and Tamil)
UNFINISHED_WORDS = {"and", "then", "so", "because", "but", "or", "also", "plus", "the", "a", "an", "to",
                    "with", "for", "of", "in", "on", "at", "my", "your", "like", "um", "uh", "which", "too",
                    "that", "if", "when", "after", "before", "and then", "அப்புறம்", "அப்றம்", "அப்போ",
                    "ஆனா", "அதோட", "மற்றும்"}

# Cloud hearing models, tried in order (both free on Groq)
CLOUD_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]
cloud = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0, timeout=8)  # give up on a stuck request after 8s
listeners = ThreadPoolExecutor(max_workers=4)  # English and Tamil at the same time (and an early guess)
local_whisper = None  # only loaded if the cloud fails (saves RAM and startup time)

# Whisper sometimes "hears" these in plain noise
GHOST_PHRASES = {"thank you", "thanks for watching", "thank you for watching", "you", "bye"}

print("Loading wake word model...")
SetLogLevel(-1)  # hide Vosk's technical logs
vosk_model = Model(lang="en-us")  # downloads a small ~40MB model the first time
mic = pyaudio.PyAudio()
speech_threshold = 60  # how loud speech must be; set by calibrate()
noise_level = 20       # the room's background noise; set by calibrate()

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

last_wake = ""  # the wake phrase the listener heard last ("hey mind", "hi mind" or "mind")

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
            found = [p for p in phrases if p in heard]
            if found:
                global last_wake
                last_wake = max(found, key=len)  # "hey mind" is surer than just "mind"
                state.set_status("listening")
                import audio
                audio.duck()  # music down while you talk (main puts it back after answering)
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
    global noise_level
    noise_level = float(np.percentile(noise, 90))
    speech_threshold = max(noise_level * 1.5, 35)  # lower = hears quieter voices

def record(should_stop, start_timeout=START_TIMEOUT):
    # Records what you say (one or more sentences). Returns the sound, b"" if nobody spoke,
    # or None if should_stop() said stop (e.g. a command was typed in the HUD).
    stream = open_mic()
    state.set_status("listening")
    print("Listening...")
    before = deque(maxlen=3)  # keep a moment before you start, so the first word isn't cut
    waited = 0
    try:
        while True:
            if should_stop():
                return None
            data = stream.read(STEP, exception_on_overflow=False)
            volume = loudness(data)
            show_level(volume)
            before.append(data)
            if volume > speech_threshold:  # you started talking
                sound = keep_recording(stream, list(before), loud=1)
                if sound is not None:
                    return sound
                before.clear()  # just a click or bump, keep waiting
                continue
            waited += 1
            if waited * 0.1 >= start_timeout:
                return b""
    finally:
        state.set_level(0)
        close_mic(stream)

def unfinished(text):
    # Did you stop in the middle of a sentence? ("play lofi and", "remind me to", "open the...")
    text = text.strip()
    if text.endswith((",", "...", "…")):
        return True
    words = text.rstrip(".!?").lower().split()
    return bool(words) and (words[-1] in UNFINISHED_WORDS or " ".join(words[-2:]) in UNFINISHED_WORDS)

guesser = ThreadPoolExecutor(max_workers=2)  # turns your words into text while you're still pausing
early = {}  # {"sound": the recording, "job": its text being worked out}, used by to_text()

def words_of(job):
    # The words of a finished early guess, simplified ("Mind, fix it." -> "mind fix it")
    try:
        return " ".join(re.findall(r"\w+", (job.result() or "").lower()))
    except Exception:
        return ""

def keep_recording(stream, frames, loud=0):
    # You've started talking (frames so far): keep recording until you're clearly done.
    # Returns the sound, or None if it was only a click or bump.
    quiet = 0
    guess = None  # (sound so far, its text being worked out in the background)
    earlier = []  # words of earlier guesses (to notice noise that adds no new words)
    while len(frames) * 0.1 < MAX_LENGTH:
        data = stream.read(STEP, exception_on_overflow=False)
        volume = loudness(data)
        show_level(volume)
        frames.append(data)
        # Once you're talking, softer words still count (trailing off, a quiet or stuck voice),
        # as long as they're clearly above the room's background noise
        if volume > max(speech_threshold * 0.7, noise_level * 1.3):
            if volume > speech_threshold:
                loud += 1
            quiet = 0
            if guess is not None and guess[1].done():
                earlier.append(words_of(guess[1]))
            guess = None  # you kept talking: that guess came too early
            continue
        quiet += 1
        silence = quiet * 0.1
        if silence < PAUSE:
            continue
        if loud * 0.1 < MIN_SPEECH:
            return None  # too short to be speech
        if guess is None:
            sound = b"".join(frames)
            guess = (sound, guesser.submit(transcribe, sound))
        if guess[1].done() and earlier and (words_of(guess[1]) == earlier[-1] or len(earlier) >= 4):
            # More sound came, but no new words (a fan, music, a TV): that was noise, your turn is over.
            # (It once kept "listening" for 30 s after a reactor click, working out the same words 9 times.)
            break
        if silence >= MORE_PAUSE:
            break  # long enough, even after "and..."
        if silence >= DONE_PAUSE and guess[1].done():
            try:
                done = not unfinished(guess[1].result())
            except Exception:
                done = True  # couldn't hear it early: to_text() will try again
            if done:
                break
    if guess is None:
        return b"".join(frames)  # hit the length limit while talking
    early.clear()
    early.update(sound=guess[0], job=guess[1])
    return guess[0]

def finish_recording(stream, frames):
    # You've already started talking (frames so far, e.g. "hey mind"): keep recording until you're done
    sound = keep_recording(stream, frames, loud=int(MIN_SPEECH * 10))
    return sound if sound is not None else b"".join(frames)

# ---------- Speech to text ----------
# How Whisper has misheard M.I.N.D's own words ("open HUD" came out as "open Hachiuri")
BUILT_IN_FIXES = {"hachiuri": "HUD", "hachi uri": "HUD", "hachidi": "HUD", "hachidee": "HUD", "hachadi": "HUD",
                  # "pause the song" over music came out as "the past two songs" (and went back a song)
                  "the past two songs": "pause the songs", "past the songs": "pause the songs",
                  "past the song": "pause the song", "past this song": "pause this song",
                  "past the music": "pause the music", "past the video": "pause the video",
                  "posts the song": "pause the song", "pose the song": "pause the song",
                  # "Mind, fix my grammar" came out as "mind if it's my grammar" / "mindfix, my sentence"
                  "if it's my grammar": "fix my grammar", "if it's my sentence": "fix my sentence",
                  "if its my grammar": "fix my grammar", "mindfix": "mind fix", "mind fix's": "mind fix",
                  "fix.dgrammar": "fix my grammar", "fixed grammar": "fix my grammar", "dgrammar": "grammar",
                  "grammer": "grammar", "if it's the grammar": "fix the grammar", "if it's grammar": "fix grammar",
                  # "open WhatsApp" came out as "open, what's up" / "open, watch the video"
                  "open what's up": "open WhatsApp", "open, what's up": "open WhatsApp", "open whats up": "open WhatsApp",
                  "open watch app": "open WhatsApp", "open, watch the video": "open WhatsApp",
                  "open watch the video": "open WhatsApp", "open what's app": "open WhatsApp"}

def fix_text(text):
    # Your own fixes, e.g. "when I say v v p I mean VVP"
    for wrong, right in list(BUILT_IN_FIXES.items()) + list(profile.get("corrections", {}).items()):
        text = re.sub(r"\b" + re.escape(wrong) + r"\b", right, text, flags=re.IGNORECASE)
    return text

# Words Whisper should expect, so it spells them right
COMMON_WORDS = ["HUD", "WhatsApp", "YouTube", "VS Code", "Chrome", "Claude", "lofi", "Tamil", "grammar", "volume"]

# Example commands in the hint teach Whisper that "Mind," is a NAME. With only a word list it kept
# turning "Mind, lock my laptop" into "I'm going to lock my laptop" or "Mind if I...", and then
# M.I.N.D ignored you. Hearing test (20 of the owner's commands, laptop mic): 77% -> 89% words right.
# (None of the test sentences are in here, so the test can't cheat.)
EXAMPLES = ["Mind, open Chrome.", "Mind, check my battery.", "Mind, play a Tamil song on YouTube."]
HINT_LENGTH = 600  # Whisper only reads ~224 tokens of hint; the old one was over that with junk

PLAIN_SONG_WORDS = {"song", "songs", "music", "mix", "tamil", "melody", "good", "upbeat", "some", "a", "the", "video"}

def song_names():
    # The names in the songs you played, newest first, without plain words
    # ("good Tamil melody song" adds nothing; "Rathinamo" is the word Whisper needs)
    names = []
    for song in reversed(profile.get("songs", [])):
        name = " ".join(w for w in song.split() if w.lower() not in PLAIN_SONG_WORDS)
        if name and name.lower() not in (n.lower() for n in names):
            names.append(name)
    return names[:8]

def hint_words():
    # Names Whisper should spell right: yours, your city, songs and projects
    words = [profile.get("city", "")] + COMMON_WORDS
    words += list(profile.get("corrections", {}).values()) + list(profile.get("shortcuts", {}))
    words += song_names()
    import pc
    words += pc.project_names(8)  # your newest projects ("dfresh" was heard as "Depression")
    words += pc.own_account_words()  # your Chrome accounts ("tigerboogipinky" was heard as "tigergojimayready")
    seen, kept = set(), []
    for w in words:
        if w and w.lower() not in seen:
            seen.add(w.lower())
            kept.append(w)
    return kept

def make_hint():
    # Your name + example commands + a short word list.
    # Never things like "I live in ...": on music or noise Whisper sometimes repeats the hint
    # back as if you said it ("I live in Kishore" became fake commands). copied_hint() catches that.
    who = f"{profile['real_name']} talking to Mind. " if profile.get("real_name") else ""
    hint = who + " ".join(EXAMPLES) + " Words: "
    for word in hint_words():
        if len(hint) + len(word) + 2 > HINT_LENGTH:
            break
        hint += word + ", "
    return hint.rstrip(", ")

def simple(text):
    return " ".join(re.findall(r"\w+", text.lower()))

def copied_hint(text):
    # True if Whisper just repeated the hint instead of hearing you. Only an in-order copy counts:
    # counting single words threw away real commands ("Mind, pause the song" has "pause" and "song").
    said = simple(text)
    if len(said.split()) < 3:
        return False
    if profile.get("real_name") and simple(f"{profile['real_name']} talking to Mind") in said:
        return True
    items = [simple(w) for w in hint_words()]
    if any(" ".join(items[i:i + 3]) in said for i in range(len(items) - 2)):
        return True  # 3 words from the list in a row ("Chennai, HUD, WhatsApp")
    return sum(simple(e) in said for e in EXAMPLES) >= 2  # 2 example commands at once

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

def to_ogg(sound, rate=RATE):
    # Squeeze the recording ~10x (Opus, like WhatsApp voice notes) so it uploads fast,
    # even on a slow connection (raw audio took 5.6s to send, this takes under 1s).
    # Also makes M.I.N.D's Telegram voice notes (rate=24000: the live voice).
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="ogg") as out:
        stream = out.add_stream("libopus", rate=rate)
        stream.bit_rate = 24000
        frame = av.AudioFrame.from_ndarray(np.frombuffer(sound, np.int16).reshape(1, -1),
                                           format="s16", layout="mono")
        frame.sample_rate = rate
        for packet in list(stream.encode(frame)) + list(stream.encode(None)):
            out.mux(packet)
    return buffer.getvalue()

MIN_CONFIDENCE = -1.0  # below this it's probably noise, not words

def hear_as(ogg, language, model):
    # One Whisper try in one language on an ogg recording. Returns (text, confidence); higher = surer.
    raw = cloud.audio.transcriptions.with_raw_response.create(
        file=("speech.ogg", ogg), model=model, language=language, prompt=make_hint(),
        response_format="verbose_json", temperature=0)
    limits.note(model, raw.headers)  # how much is left today (for the HUD)
    result = raw.parse()
    parts = [s for s in result.segments if not is_ghost(s)]
    seconds = sum(s["end"] - s["start"] for s in parts)
    if not parts or seconds <= 0:
        return "", -99
    confidence = sum(s["avg_logprob"] * (s["end"] - s["start"]) for s in parts) / seconds
    return " ".join(s["text"] for s in parts), confidence

model_free_at = {}  # Whisper model -> when its free per-minute limit lets us use it again

def transcribe_cloud(sound, ogg=None):
    # One request, in English (it used to send every recording twice, as English AND Tamil, and kept
    # hitting the free limit of 20 a minute, so real commands got lost). In Tamil mode it still does both.
    # If a model is at its limit, the other model is used right away.
    languages = ("en", "ta") if tamil_mode() else ("en",)
    ogg = ogg or to_ogg(sound)
    order = sorted(CLOUD_MODELS, key=lambda m: model_free_at.get(m, 0) > time.time())  # resting ones last
    if languages == ("en",):
        return hear_fast(ogg, order)
    for model in order:
        tries = {lang: listeners.submit(hear_as, ogg, lang, model) for lang in languages}
        heard = []
        for lang, job in tries.items():
            try:
                heard.append(job.result())
            except RateLimitError as e:
                pause = float(e.response.headers.get("retry-after", 30))
                model_free_at[model] = time.time() + pause
                print(f"Hearing model {model} is at its free limit for {pause:.0f}s, using the other one")
            except Exception as e:
                print(f"Cloud hearing ({model}, {lang}) failed: {str(e)[:100]}")
        if heard:
            text, confidence = max(heard, key=lambda h: h[1])
            return text if confidence >= MIN_CONFIDENCE else ""
    return None

HEDGE_SECONDS = 1.5  # no answer by then (a stuck request on a shaky connection)? ask the other model too

def hear_fast(ogg, order):
    # Asks the first model; if it's slow or fails, the other model is asked as well, and whichever
    # answers first wins. A single stuck request used to freeze M.I.N.D for up to 8 seconds.
    jobs = {listeners.submit(hear_as, ogg, "en", order[0]): order[0]}
    waiting, backup_asked = set(jobs), False
    while waiting:
        done, waiting = wait(waiting, timeout=None if backup_asked else HEDGE_SECONDS, return_when=FIRST_COMPLETED)
        answer = None
        for job in done:
            model = jobs[job]
            try:
                text, confidence = job.result()
                answer = text if confidence >= MIN_CONFIDENCE else ""
            except RateLimitError as e:
                pause = float(e.response.headers.get("retry-after", 30))
                model_free_at[model] = time.time() + pause
                print(f"Hearing model {model} is at its free limit for {pause:.0f}s, using the other one")
            except Exception as e:
                print(f"Cloud hearing ({model}) failed: {str(e)[:100]}")
        if answer is not None:
            return answer
        if not backup_asked:  # slow or failed: ask the other model(s) too
            backup_asked = True
            for model in order[1:]:
                job = listeners.submit(hear_as, ogg, "en", model)
                jobs[job] = model
                waiting.add(job)
            if not done:
                print("(Hearing is slow, asked the backup too)")
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

def from_ogg(ogg, rate=RATE):
    # A voice note (ogg) -> raw 16-bit mono sound at this rate (what the live brain hears)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
    pieces = []
    with av.open(io.BytesIO(ogg)) as voice_note:
        for frame in voice_note.decode(audio=0):
            for out in resampler.resample(frame):
                pieces.append(out.to_ndarray().tobytes())
    for out in resampler.resample(None):
        pieces.append(out.to_ndarray().tobytes())
    return b"".join(pieces)

def transcribe_ogg(ogg):
    # A recording that's already ogg (a Telegram voice note) -> text
    try:
        return fix_text(transcribe_cloud(None, ogg) or "").strip(" .,!?")
    except Exception as e:
        print("Voice note error:", e)
        return ""

def to_text(sound, show=True):
    # Recorded sound -> cleaned-up text ("" if nothing useful).
    # show=False: don't write it in the log (it may be people talking around you, not to M.I.N.D)
    try:
        start = time.time()
        text = None
        if early.get("sound") is sound:  # already worked out while you were pausing
            try:
                text = early["job"].result(timeout=15)
            except Exception:
                text = None
            early.clear()
        if text is None:
            text = transcribe(sound)
        text = fix_text(text).strip(" .,!?")
        if copied_hint(text):
            return ""
        measure(sound, text)
        if text and show:
            print(f"You: {text}   (heard in {time.time() - start:.1f}s)")
        return text
    except Exception as e:
        print("Speech error:", e)
        return ""

# ---------- Tone of voice (a rough idea of your mood from HOW you said it) ----------
# Real emotion AI is too heavy for this laptop, so this just compares your loudness and talking
# speed with your usual ones (learned over time). Clearly louder/faster or quieter/slower is told
# to the brain, which reads it together with your words.
last_measure = None  # (loudness, words per second) of the last thing heard

def measure(sound, text):
    global last_measure
    last_measure = None
    try:
        steps = [sound[i:i + STEP * 2] for i in range(0, len(sound), STEP * 2)]
        speech = [v for v in (loudness(s) for s in steps) if v > speech_threshold]
        words = len(text.split())
        if len(speech) >= 5 and words >= 3:
            last_measure = (float(np.median(speech)), words / (len(speech) * 0.1))
    except Exception:
        pass

def judge_tone():
    # Called when what you said really was for M.I.N.D: sets state.tone and learns your usual voice
    state.tone = ""
    if not last_measure:
        return
    loud, rate = last_measure
    usual = profile.setdefault("voice_baseline", {"loud": loud, "rate": rate, "n": 0})
    if usual["n"] >= 5:  # only after it knows your usual voice
        hints = []
        if loud > usual["loud"] * 1.6:
            hints.append("louder")
        elif loud < usual["loud"] * 0.6:
            hints.append("quieter")
        if rate > usual["rate"] * 1.35:
            hints.append("faster")
        elif rate < usual["rate"] * 0.65:
            hints.append("slower")
        if hints:
            state.tone = " and ".join(hints) + " than usual"
    step = 0.15 if usual["n"] >= 5 else 1 / (usual["n"] + 1)  # learn slowly once it knows you
    usual["loud"] += (loud - usual["loud"]) * step
    usual["rate"] += (rate - usual["rate"]) * step
    usual["n"] += 1
    save_profile()

def listen(should_stop=lambda: False, start_timeout=START_TIMEOUT):
    # Hear one sentence and turn it into text.
    # Returns "" if nothing was heard, None if should_stop() interrupted.
    sound = record(should_stop, start_timeout)
    if not sound:
        return sound
    import speaker
    import audio
    # someone else talking (TV, family)? not for M.I.N.D (music over your voice lowers the match)
    mine, match = speaker.check(sound, music=bool(audio.ducked) or audio.music_playing())
    if not mine:
        print(f"(Not your voice, ignored: match {match:.2f})")
        return ""
    state.set_status("thinking")
    text = to_text(sound)
    if text:
        state.add_message("you", text)
        judge_tone()  # it was said to M.I.N.D: how did it sound?
    return text
