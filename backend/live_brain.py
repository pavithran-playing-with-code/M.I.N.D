# M.I.N.D Live: a real conversation. ONE brain hears your voice and speaks back (Gemini Live),
# instead of the old relay race (wake word -> Whisper -> brain -> Edge voice). You can talk over it
# and it stops and listens, like a person.
#
# The live page (live.html, in Chrome) sends your mic sound here over a websocket; this file passes it
# to Gemini and sends Gemini's voice back. The API key never leaves this laptop's Python side.
import os
import asyncio
import datetime
from google import genai
from google.genai import types
from memory import profile
import state

MODEL = "gemini-3.8-live"   # tested 2026-10-29 on the free plan: first sound ~2 s
VOICE = "Charon"            # one of Gemini's built-in voices (calm, deep)
MIC_RATE = 16000            # the page sends 16 kHz, 16-bit mono sound
active = {"on": False}      # a live talk is going on (the old ears stay quiet meanwhile)

def instructions():
    # Who M.I.N.D is and who it's talking to (said once at the start of a talk)
    name = profile.get("name", "Sir")
    real = profile.get("real_name", "")
    facts = "; ".join(profile.get("facts", [])[:30])
    return (
        f"You are Mind, a personal assistant and friend on {real or 'the owner'}'s laptop, like Jarvis. "
        f"Call them {name} now and then, not every sentence. You talk like a real friend: warm, casual, "
        "a bit witty, short sentences, contractions. Real conversation is messy: people change their mind, "
        "talk over you, trail off, say 'wait no' - go with it naturally. If they interrupt, stop and listen. "
        "Keep answers short (one to three sentences) unless they ask for more. Never pretend you did something "
        "on the computer: for now you can only talk. You can't see live facts yet (weather, news, battery, the "
        "screen): never guess them, say you can't check that yet (it once made up the weather). "
        "If you didn't catch something, ask. "
        "Speak English unless they speak Tamil; then reply in casual Chennai Tamil. "
        f"They live in {profile.get('city', 'India')}. "
        f"Right now it's {datetime.datetime.now():%A, %d %B %Y, %I:%M %p}. "
        + (f"Things you know about them: {facts}." if facts else "")
    )

def config():
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=instructions(),
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
        input_audio_transcription=types.AudioTranscriptionConfig(),   # what you said, as text (for the chat)
        output_audio_transcription=types.AudioTranscriptionConfig(),  # what it said, as text
    )

async def run(ws):
    # One live talk: the page's mic -> Gemini, Gemini's voice -> the page
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    was_muted = state.muted
    if not was_muted:
        state.toggle_mute()  # the old ears would hear "mind" and answer too
    active["on"] = True
    try:
        async with client.aio.live.connect(model=MODEL, config=config()) as session:
            await ws.send_json({"ready": True})

            async def from_page():
                while True:
                    message = await ws.receive()
                    if message.get("type") == "websocket.disconnect":
                        return
                    if message.get("bytes"):
                        await session.send_realtime_input(
                            audio=types.Blob(data=message["bytes"], mime_type=f"audio/pcm;rate={MIC_RATE}"))

            async def to_page():
                while True:  # receive() ends after each answer, so keep asking
                    async for reply in session.receive():
                        if reply.data:
                            await ws.send_bytes(reply.data)  # its voice: 24 kHz, 16-bit mono
                        said = reply.server_content
                        if not said:
                            continue
                        if said.interrupted:
                            await ws.send_json({"interrupted": True})  # you talked over it: stop playing
                        if said.input_transcription and said.input_transcription.text:
                            await ws.send_json({"you": said.input_transcription.text})
                        if said.output_transcription and said.output_transcription.text:
                            await ws.send_json({"mind": said.output_transcription.text})
                        if said.turn_complete:
                            await ws.send_json({"done": True})

            tasks = [asyncio.create_task(from_page()), asyncio.create_task(to_page())]
            done, waiting = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in waiting:
                task.cancel()
            for task in done:
                task.result()  # show a real error if one happened
    finally:
        active["on"] = False
        if not was_muted and state.muted:
            state.toggle_mute()  # the old ears listen again
