# The live voice for M.I.N.D's fixed lines ("Hi Sir, Mind online.", "Mind off."), so they sound
# like the M.I.N.D you talk to, not the old voice. They're said at moments when the live brain
# can't talk yet (starting up) or there's no time for it (turning off), so each line is recorded
# ONCE from Gemini Live and kept as a sound file; after that it plays instantly, with no internet.
import os
import re
import wave
import asyncio
import hashlib
import threading
import numpy as np
import settings

SAMPLE_RATE = 24000  # Gemini Live's voice: 24 kHz, 16-bit, mono

def clip_path(line):
    import voice
    name = hashlib.md5(f"live:{settings.get('live_voice')}|{line}".encode()).hexdigest()
    return os.path.join(voice.CACHE_DIR, name + ".wav")

def clip(line):
    # (path, seconds until the words end) if this line was recorded in the live voice, else None
    path = clip_path(line)
    try:
        with open(path + ".end") as f:
            return path, float(f.read())
    except (OSError, ValueError):
        return None

def simple(text):
    return re.sub(r"[^a-z ]", "", text.lower()).split()

async def record(line):
    # Asks Gemini Live to say exactly this line, and keeps its voice. Returns the sound, or None
    # if it said something else (it may add words: then the old voice stays for that line).
    from google import genai
    from google.genai import types
    import live_brain
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction="You are a voice recorder. Say exactly the words you're given, naturally and "
                           "warmly, like a friend. Nothing before or after them.",
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.get("live_voice")))),
        output_audio_transcription=types.AudioTranscriptionConfig())
    sound, said = b"", ""
    async with client.aio.live.connect(model=live_brain.MODEL, config=config) as session:
        await session.send_realtime_input(text=f"Say exactly: {line}")
        async for reply in session.receive():
            if reply.data:
                sound += reply.data
            talk = reply.server_content
            if talk and talk.output_transcription and talk.output_transcription.text:
                said += talk.output_transcription.text
            if talk and talk.turn_complete:
                break
    seconds = len(sound) / (SAMPLE_RATE * 2)
    if not said:
        # (its words sometimes don't come back as text: then the length must fit the line)
        return sound if 0.4 * len(line.split()) <= seconds <= 0.7 * len(line.split()) + 1.5 else None
    if simple(said) != simple(line):
        print(f"(Live voice: asked for {line!r}, it said {said!r})")
        return None
    return sound

def save(line, sound):
    # Keeps the sound as a .wav, and where the words end (so playing stops on time, not on silence)
    samples = np.frombuffer(sound, dtype=np.int16)
    loud = np.nonzero(np.abs(samples) > 500)[0]
    end = (loud[-1] / SAMPLE_RATE if len(loud) else len(samples) / SAMPLE_RATE) + 0.2
    path = clip_path(line)
    with wave.open(path + ".part", "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(sound)
    os.replace(path + ".part", path)
    with open(path + ".end", "w") as f:
        f.write(f"{end:.2f}")

def make_ready(lines):
    # In the background: record the lines that aren't recorded yet (once; a few seconds each)
    def work():
        for line in lines:
            if clip(line):
                os.utime(clip_path(line))  # (still used: the 30-day cleanup keeps it)
                os.utime(clip_path(line) + ".end")
                continue
            for _ in range(2):  # a second try if it added words
                try:
                    sound = asyncio.run(record(line))
                except Exception as e:
                    print("(Live voice: couldn't record a line:", str(e)[:100] + ")")
                    return  # no internet / limit: the old voice says it, try again next start
                if sound:
                    save(line, sound)
                    break
    threading.Thread(target=work, daemon=True).start()
