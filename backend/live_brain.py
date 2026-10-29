# M.I.N.D Live: a real conversation. ONE brain hears your voice and speaks back (Gemini Live),
# instead of the old relay race (wake word -> Whisper -> brain -> Edge voice). You can talk over it
# and it stops and listens, like a person. It uses the same tools (hands) as the old brain (tools.py).
#
# The live page (live.html, in Chrome) sends your mic sound here over a websocket; this file passes it
# to Gemini and sends Gemini's voice back. The API key never leaves this laptop's Python side.
#
# Always ready: M.I.N.D keeps the page open in a hidden window of its own (live_window.py). It sleeps
# (mic closed, nothing sent anywhere) until the old ears hear "Mind" on the laptop; main.py then hands
# what you just said to wake(), and the talk goes on naturally until you say bye or go quiet.
import os
import json
import time
import asyncio
import datetime
from google import genai
from google.genai import types
from memory import profile
import state
import tools
import pc

MODEL = "gemini-3.8-live"   # tested 2026-10-29 on the free plan: first sound ~2 s
VOICE = "Charon"            # one of Gemini's built-in voices (calm, deep)
MIC_RATE = 16000            # the page sends 16 kHz, 16-bit mono sound
VOICE_BYTES = 48000         # its voice: 24 kHz x 2 bytes = one second
IDLE_SECONDS = 25           # nobody talked for this long after its last word: go back to sleep
NUDGE_SECONDS = 5           # a tool finished but no answer came this long after: ask for it

# Tools that don't fit a live talk: the old ears' voice lock and spelling fixes, and ways to end
# or switch off the old M.I.N.D (end_talk below ends a live talk)
NOT_LIVE = {"voice_lock", "add_correction", "go_offline", "end_conversation", "shut_down"}

RULES = """Rules:
- Real conversation is messy: people change their mind, talk over you, trail off, say "wait no". Go with it.
  If they interrupt, stop and listen. If you didn't catch something, ask.
- Keep answers short (one to three sentences) unless they ask for more. No lists or markdown: you're speaking.
- To DO anything on the laptop, call a tool. Several asks at once: do them all, then one short reply.
- Only say something is done when the tool result says it worked. If a tool fails or finds nothing, say so
  honestly and offer the closest option it gave ("I couldn't find Shiva on WhatsApp. Did you mean Siva Chithappa?").
- Weather, news, battery, the screen, live facts: always use the tool, never guess.
- If the request is unclear or a name might be misheard, ask one short question before acting.
- Never send a message, delete, buy or pay unless they clearly said so.
- "A new tab" = open_url with url "about:blank" (it opens a real new tab in their Chrome).
- If it can be pictured (a thing, food, place, product), you may show_on_hud while you talk about it.
- If they're low (sad, tired, stressed), be a caring friend first, no tools unless asked.
- Speak English unless they speak Tamil; then reply in casual spoken Chennai Tamil.
- Never invent facts about them. If they share something they love, remember_fact it.
- Call end_talk ONLY when they clearly say they're done: "bye", "that's all", "thanks, that's it", "stop",
  "not now", "go to sleep". Then say a very short goodbye (or nothing after "stop"). NEVER call it just because
  you answered a question: they may have more to say (you go to sleep by yourself if they stay quiet)."""

def instructions():
    # Who M.I.N.D is, who it's talking to, and what's on the laptop (said once at the start of a talk)
    real = profile.get("real_name", "")
    lines = [f"You are Mind, a personal assistant and close friend on {real or 'the owner'}'s Windows laptop, "
             f"like Jarvis but chill. Call them {profile.get('name', 'Sir')} now and then, not every sentence. "
             "Talk like a real friend: warm, casual, a bit witty, short sentences, contractions, never 'Certainly'.",
             RULES,
             f"Right now it's {datetime.datetime.now():%A, %d %B %Y, %I:%M %p}. "
             f"They live in {profile.get('city', 'India')}."]
    if profile.get("facts"):
        lines.append("Things you remember about them: " + "; ".join(profile["facts"][:40]))
    projects = pc.project_names(10)
    if projects:
        lines.append("Their code projects (open_folder): " + ", ".join(projects))
    accounts = pc.own_account_words()
    if accounts:
        lines.append("Their Chrome accounts (use as account= only when they name one): " + ", ".join(accounts))
    contacts = list(profile.get("contacts", {}))
    if contacts:
        lines.append("Saved contacts: " + ", ".join(contacts))
    lines.append("Routines (run_routine): " + ", ".join(tools.routines()))
    if tools.upcoming_reminders():
        lines.append("Upcoming reminders: " + "; ".join(tools.upcoming_reminders()))
    recent = recent_talk()
    if recent:
        lines.append("What you two said recently (so you can carry on; older things: use recall):\n" + recent)
    return "\n".join(lines)

def recent_talk(hours=3, turns=8):
    # The last few turns from the diary, so a new talk remembers the last one ("play that song again")
    import diary
    since = time.time() - hours * 3600
    found = [e for e in diary.entries() if e["t"] >= since][-turns:]
    lines = []
    for e in found:
        when = datetime.datetime.fromtimestamp(e["t"]).strftime("%I:%M %p")
        did = f" [did: {e['did'][:120]}]" if e.get("did") else ""
        lines.append(f"{when} they: {e['you'][:150]} | you: {e['said'][:150]}{did}")
    return "\n".join(lines)

END_TALK = types.FunctionDeclaration(  # (no settings at all: an empty settings list may have crashed a talk)
    name="end_talk", description="ONLY when they SAY they're done (bye / that's all / stop / not now / go to sleep). "
                                 "Never after just answering. Mind goes back to sleep until they say 'Mind' again.")
RECONNECTS = 2  # most reconnects in one talk (a resume once failed 29 times in a row, hammering Google)

def declarations():
    # The old brain's tools, in Gemini's format (same names, descriptions and settings), plus end_talk
    found = [END_TALK]
    for t in tools.TOOLS:
        f = t["function"]
        if f["name"] not in NOT_LIVE:
            found.append(types.FunctionDeclaration(name=f["name"], description=f["description"],
                                                   parameters_json_schema=f["parameters"]))
    return [types.Tool(function_declarations=found)]

def config(ticket=None):
    # ticket: Google's resume ticket from the last connection (the same talk goes on), or None (a new talk)
    return types.LiveConnectConfig(
        session_resumption=types.SessionResumptionConfig(handle=ticket),
        response_modalities=["AUDIO"],
        system_instruction=instructions(),
        tools=declarations(),
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
        input_audio_transcription=types.AudioTranscriptionConfig(),   # what you said, as text (for the chat)
        output_audio_transcription=types.AudioTranscriptionConfig(),  # what it said, as text
        # Without this, Google ends a talk after 15 minutes (it drops the oldest part instead)
        context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
    )

def run_tool(name, args, heard):
    # Runs one tool in a background thread. Tools check the user's own words for risky things
    # (typing, sending, Enter, which Chrome account), so give them what was heard this turn.
    state.last_user_text = heard
    print(f"  [live tool] {name} {args}")
    result, worked = tools.run_tool(name, args)
    print(f"  [result] {result[:300]}")
    return result

# ---------- The page: sleeps, wakes on "Mind", talks ----------
page = None   # the live page that's connected now (only one)
loop = None   # the web server's event loop (wake() is called from main.py's thread)

def ready():
    # Is the hidden live page connected and asleep, so a "Mind" can wake it?
    return page is not None and not page.talking

def wake(sound=b"", text=""):
    # Called from main.py when the old ears heard "Mind": start a talk with what was just said
    # (the recording, so "Mind, play X" in one breath works). Returns False if Live isn't ready.
    if not ready():
        return False
    state.live = True  # right away, so the old ears don't grab the mic meanwhile
    loop.call_soon_threadsafe(page.start, sound, text)
    return True

class Page:
    def __init__(self, ws):
        self.ws = ws
        self.wanted = asyncio.Event()  # a talk should start
        self.audio = asyncio.Queue()   # mic sound from the page during a talk
        self.talking = False
        self.stop_now = False
        self.closed = False  # the page went away (closed, reloaded, M.I.N.D's window shut)
        self.first_sound, self.first_text = b"", ""

    def start(self, sound=b"", text=""):
        self.first_sound, self.first_text, self.stop_now = sound, text, False
        self.wanted.set()

    async def read(self):
        # Everything the page sends: mic sound, and "start"/"stop" from a tap on its orb
        while True:
            message = await self.ws.receive()
            if message.get("type") == "websocket.disconnect":
                self.closed = True  # a talk going on ends too (watch() sees this)
                return
            if message.get("bytes"):
                if self.talking:
                    self.audio.put_nowait(message["bytes"])
            elif message.get("text"):
                asked = json.loads(message["text"])
                if asked.get("start") and not self.talking:
                    state.live = True
                    self.start()
                if asked.get("stop"):
                    self.stop_now = True
                if asked.get("problem"):
                    print("Live page problem:", asked["problem"])  # e.g. the mic couldn't open

    async def talk(self):
        # One conversation, from "Mind" until bye / quiet / a tap
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.talking, state.live = True, True
        while not self.audio.empty():
            self.audio.get_nowait()  # old sound from before the talk
        self.heard, self.said, self.did = [], [], []  # this turn: your words, its words, the tools it used
        self.clock = {"active": time.time(), "voice_until": 0.0, "ending": 0, "done": False}  # ending = when end_talk was called
        self.ticket = None  # Google's resume ticket: a talk outlives its ~10-minute connection limit
        await self.ws.send_json({"listen": True})  # the page opens its mic
        state.set_status("listening")
        print("(Live: awake and listening)")
        try:
            tries = 0
            while await self.connection(client, tries == 0):  # True = Google asked us to reconnect
                tries += 1
                if tries > RECONNECTS or self.closed:
                    print("(Live: couldn't reconnect, going to sleep; say 'Mind' to start again)")
                    break
                print("(Live: reconnecting, the talk carries on)")
                await asyncio.sleep(1.5)  # give Google a moment to let go of the old connection
        finally:
            self.finish_turn()
            self.talking, state.live = False, False  # the old ears listen again
            state.set_status("waiting")
            print("(Live: back to sleep)")
            try:
                await self.ws.send_json({"sleep": True})  # the page closes its mic (its last words still play)
            except Exception:
                pass

    def finish_turn(self):
        # A turn is over: show it in the HUD chat / floating reactor, and keep it in the diary
        you, mind = "".join(self.heard).strip(), "".join(self.said).strip()
        if you:
            print("You (live):", you)
            state.add_message("you", you)
        if mind:
            print("M.I.N.D (live):", mind)
            state.add_message("mind", mind)
        if you or mind:
            import diary
            diary.write(you, self.did, mind)  # so "what did we talk about yesterday?" works
        self.heard.clear()
        self.said.clear()
        self.did.clear()

    async def connection(self, client, first):
        # One connection to Google. Returns True if it should reconnect (Google's ~10-minute limit),
        # False when the talk is over (goodbye, a tap, or quiet).
        clock = self.clock
        try:
            async with client.aio.live.connect(model=MODEL, config=config(self.ticket)) as session:
                if first and self.first_sound:  # what they said with "Mind" (recorded by the old ears)
                    for i in range(0, len(self.first_sound), 3200):
                        await session.send_realtime_input(audio=types.Blob(
                            data=self.first_sound[i:i + 3200], mime_type=f"audio/pcm;rate={MIC_RATE}"))
                elif first and self.first_text:
                    await session.send_realtime_input(text=self.first_text)

                async def to_gemini():
                    while True:
                        chunk = await self.audio.get()
                        await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={MIC_RATE}"))

                async def from_gemini():
                    while True:  # receive() ends after each answer, so keep asking
                        async for reply in session.receive():
                            if await self.handle(session, reply):
                                return True  # Google says this connection ends soon: reconnect

                async def watch():
                    # Back to sleep: after a goodbye, a tap, or IDLE_SECONDS of quiet after its last word
                    while True:
                        await asyncio.sleep(0.5)
                        now = time.time()
                        talking_now = now < clock["voice_until"]
                        if not talking_now and state.status == "speaking":
                            state.set_status("listening")  # its voice finished: the reactor shows listening
                        if self.closed or self.stop_now or (clock["done"] and not talking_now):
                            return False
                        if clock["ending"] and now - clock["ending"] > 5 and not talking_now:
                            return False  # end_talk with no goodbye after it ("stop"): sleep anyway
                        if (clock.get("tool_done") and not clock.get("nudged")
                                and clock["active"] <= clock["tool_done"]  # (they haven't spoken since)
                                and now - clock["tool_done"] > NUDGE_SECONDS):
                            # A tool finished but no answer came (seen 2 times in ~6 tests): ask for it,
                            # so they're never left in silence
                            clock["nudged"] = True
                            print("   (no answer after the tool, nudging)")
                            await session.send_realtime_input(text="(The tool finished. Tell me the result now.)")
                        if not talking_now and now - max(clock["active"], clock["voice_until"]) > IDLE_SECONDS:
                            return False

                jobs = [asyncio.create_task(job()) for job in (to_gemini, from_gemini, watch)]
                done, waiting = await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
                for job in waiting:
                    job.cancel()
                return any(job.result() for job in done)  # (a real error shows here)
        except Exception as e:
            if self.closed:
                return False  # the page closed (that's what broke): the talk is over
            if self.ticket and not (clock["done"] or self.stop_now):
                print("Live connection dropped, resuming:", str(e)[:120])
                return True  # Google's side broke mid-talk: carry on with the resume ticket
            raise

    async def handle(self, session, reply):
        # One message from Google: its voice, a tool to run, words, or news about the connection.
        # Returns True when Google says this connection will end soon.
        clock, now = self.clock, time.time()
        if reply.session_resumption_update and reply.session_resumption_update.resumable:
            self.ticket = reply.session_resumption_update.new_handle or self.ticket
        if reply.go_away:
            return True
        if reply.data:
            if clock.get("tool_done"):
                print(f"   (answered {now - clock['tool_done']:.1f}s after the tool)")
                clock["tool_done"] = 0
            state.set_status("speaking")
            clock["voice_until"] = max(clock["voice_until"], now) + len(reply.data) / VOICE_BYTES
            await self.ws.send_bytes(reply.data)
        if reply.tool_call:
            state.set_status("thinking")
            answers = []
            for call in reply.tool_call.function_calls:
                await self.ws.send_json({"tool": call.name})
                if call.name == "end_talk":
                    clock["ending"] = now
                    result = "Okay, going to sleep after your goodbye."
                else:
                    result = await asyncio.to_thread(run_tool, call.name, dict(call.args or {}), "".join(self.heard))
                    self.did.append(f"{call.name}: {result[:80]}")
                answers.append(types.FunctionResponse(id=call.id, name=call.name, response={"result": result}))
            await session.send_tool_response(function_responses=answers)
            clock["active"] = clock["tool_done"] = time.time()
            clock["nudged"] = False
        talk = reply.server_content
        if not talk:
            return False
        if talk.interrupted:
            await self.ws.send_json({"interrupted": True})  # you talked over it: stop playing
            clock["voice_until"] = now
            self.finish_turn()
        if talk.input_transcription and talk.input_transcription.text:
            clock["active"] = now
            if self.said:
                self.finish_turn()  # you started a new turn
            state.set_status("listening")
            self.heard.append(talk.input_transcription.text)
            await self.ws.send_json({"you": talk.input_transcription.text})
        if talk.output_transcription and talk.output_transcription.text:
            self.said.append(talk.output_transcription.text)
            await self.ws.send_json({"mind": talk.output_transcription.text})
        if talk.turn_complete:
            spoke = bool(self.said)
            self.finish_turn()
            clock["active"] = time.time()
            await self.ws.send_json({"done": True})
            if clock["ending"] and spoke:
                clock["done"] = True  # its goodbye was said (Google ends the tool's turn first, then says it)
        return False

async def run(ws, auto=False):
    # The live page is connected: sleep until "Mind" (or a tap), talk, sleep again... until it closes.
    # auto = M.I.N.D's hidden window: the one "Mind" wakes. A normal tab only talks when its orb is tapped.
    global page, loop
    loop = asyncio.get_running_loop()
    me = Page(ws)
    if auto:
        page = me
    await ws.send_json({"ready": True})
    reader = asyncio.create_task(me.read())
    try:
        while True:
            waiter = asyncio.create_task(me.wanted.wait())
            done, _ = await asyncio.wait({reader, waiter}, return_when=asyncio.FIRST_COMPLETED)
            if reader in done:
                waiter.cancel()
                return  # the page closed
            me.wanted.clear()
            try:
                await me.talk()
            except Exception as e:
                print("Live talk stopped:", str(e)[:200])
                await ws.send_json({"error": str(e)[:200]})
    finally:
        reader.cancel()
        if page is me:
            page = None
        state.live = False
