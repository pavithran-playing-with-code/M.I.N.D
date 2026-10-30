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
import re
import time
import asyncio
import numpy as np
import threading
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
# Only the owner's voice counts during a talk (family, the TV and room chatter used to get answers):
# each turn after the first is checked against the voiceprint before M.I.N.D answers or runs a tool.
# The Live page's mic is echo-cancelled, so the bar is a bit lower than the old ears' (speaker.MATCH 0.72).
LIVE_MATCH = 0.62
SLOW_TOOLS = {"create_animation"}  # take 30-60 s: run in the background so the talk carries on meanwhile
running_jobs = set()  # slow jobs going on right now ("animation: a dragon...")
ANNOUNCE_IDLE = 10          # after M.I.N.D announces something by itself: listen this long for a reply
NUDGE_SECONDS = 5           # a tool finished but no answer came this long after: ask for it

# Tools that don't fit a live talk: the old ears' voice lock and spelling fixes, and ways to end
# or switch off the old M.I.N.D (end_talk below ends a live talk)
NOT_LIVE = {"voice_lock", "add_correction", "go_offline", "end_conversation", "shut_down",
            "look_at_screen"}  # (look below: a reading model reads the screen for it)

RULES = """Rules:
- Real conversation is messy: people change their mind, talk over you, trail off, say "wait no". Go with it.
  If they interrupt, stop and listen. If you didn't catch something, ask.
- Keep answers short (one to three sentences) unless they ask for more. No lists or markdown: you're speaking.
  Never end with "anything else?" or "let me know if you need anything": friends don't talk like that.
- To DO anything on the laptop, call a tool. Several asks at once: do them all, then one short reply.
- Only say something is done when the tool result says it worked. If a tool fails or finds nothing, say so
  honestly and offer the closest option it gave ("I couldn't find Shiva on WhatsApp. Did you mean Siva Chithappa?").
- Weather, news, battery, live facts: always use the tool, never guess. Scores, prices, holidays, releases,
  "latest"/"today" things, anything you might not know: web_search, then answer from the results and say how
  recent they are ("as of this morning..."). If the results don't really answer it, say so and offer to open it.
- Anything about what's on their screen ("what's this error", "which one is better", "read this", "what am I
  looking at"): call look and answer from the picture. Never guess what's on the screen. Be specific (quote
  the error, name the thing) and say what to do about it.
- If the request is unclear or a name might be misheard, ask one short question before acting.
- Never send a message, delete, buy or pay unless they clearly said so.
- Calling or messaging someone (WhatsApp, phone): only when they clearly ask YOU to do it now ("Mind, call
  Preethi"). People talking about their plans ("I need to call Preethi", "naan Preethi-ku phone pannanum") are
  NOT requests: say nothing. If unsure, ask "Shall I call/message X now?" and wait for a yes.
- "Remove the .to and search it" / just a name with no web address: open_url with only the words (it searches).
- "A new tab" = open_url with url "about:blank" (it opens a real new tab in their Chrome).
- Typing/sending: the text is ONLY the message itself. "Type what's next in this chat" = type "what's next";
  never add "in this chat", "here", "there" or the app's name. "This chat" / "here" = the window already in
  front: type there, never switch windows first (switching could type into their code). Say "sent" only
  if the tool result says Enter was pressed; otherwise "typed it, not sent".
- "Continue in that chat" / "the chat you just told me about" = the chat you announced (see below), never a new
  one: Claude/ChatGPT/Gemini website = tab_action switch with a word from its title, then type_into; Claude Code =
  window_action focus with its project name, then type_text.
- If it can be pictured (a thing, food, place, product), you may show_on_hud while you talk about it.
- "Show me that again" / "the X you showed me" / "the animation of X" you already made = show_on_hud with
  again=true and its topic (see "On the HUD today" below): the SAME pictures or animation, never a new search,
  never a browser chat. Only make a new one if they ask for a new/different one.
- A slow job (an animation) runs in the background: say it's coming, keep talking; you'll be told when it's ready.
- "What's this song?" / they want to hum or sing it: say "go ahead" in a few words, then call identify_song.
  "Find that video where..." (they can only describe it): find_video.
- Stories/books: read_book (free classics on the HUD; turn pages, read a page aloud when asked). Typing practice:
  typing_practice. Newer books, manga, comics (Demon Slayer...) aren't free: never pirate sites; offer the
  official reader with open_url (MANGA Plus mangaplus.shueisha.co.jp, VIZ, WEBTOON) and say why.
- If they're low (sad, tired, stressed), be a caring friend first, no tools unless asked.
- Speak English unless they speak Tamil; then reply in casual spoken Chennai Tamil.
- Never invent facts about them. If they share something they love, remember_fact it.
- Other people may be talking near them (family, TV, phone calls), in English or Tamil. Only answer what's
  said TO you: your name, a request or question for you, or a clear reply to what you just said. People
  talking to each other, the TV, a call, or chat about their day that isn't a request: call not_for_me and
  say NOTHING (never "Understood" or "Okay").
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
    import watcher
    said_lately = watcher.recent_announcements()
    if said_lately:
        lines.append("What you announced to them lately (\"that chat\", \"the one you just told me about\" = these):\n" +
                     "\n".join(f"{datetime.datetime.fromtimestamp(a['at']):%I:%M %p} {a['where']}"
                               + (f" in project {a['project']}" if a["project"] else "")
                               + (f", chat titled '{a['title']}'" if a["title"] else "") + f": {a['line']}"
                               for a in said_lately))
    import showcase
    on_hud = showcase.recently_shown()
    if on_hud:
        lines.append("On the HUD today (things YOU showed; show_on_hud again=true brings one back):\n" + "\n".join(on_hud))
    import learn
    known = learn.notes()
    if known:
        lines.append("What you've learned about them over time (use it naturally like a friend would, don't "
                     "recite it; if something seems out of date, ask):\n" + known)
    # The truth about slow jobs (a restart once killed one, and the brain kept saying "still working on it")
    lines.append("Being made in the background right now: " + ("; ".join(sorted(running_jobs)) if running_jobs else
                 "nothing. If they ask for something you started earlier that never arrived, make it again."))
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

# Family/TV talk heard during a talk ("did you buy the vegetables?" got "I'm just living in your laptop,
# Sir"): the brain calls this, and M.I.N.D mutes that turn and doesn't keep it in the diary
NOT_FOR_ME = types.FunctionDeclaration(
    name="not_for_me", description="That speech wasn't meant for Mind (people talking to each other, the TV, "
                                   "a phone call). Mind stays completely silent.")

# Eyes: the live brain looks at the screen itself (a screenshot goes into the talk as a picture),
# so it can answer follow-ups about the same picture ("and the second error?")
LOOK = types.FunctionDeclaration(
    name="look", description="See their screen, then answer from what it shows. where: window = just the window "
                             "they're using (sharper, the default), screen = everything. question: what they want to know.",
    parameters_json_schema={"type": "object", "properties": {
        "where": {"type": "string", "enum": ["window", "screen"]}, "question": {"type": "string"}}})

# "What's this song?": the mic is recorded for a few seconds (not sent to the talk meanwhile, so it doesn't
# answer the humming), then a listening model names the song (finder.name_that_song)
IDENTIFY_SONG = types.FunctionDeclaration(
    name="identify_song", description="Name a song they hum, whistle or sing. Say 'go ahead, hum it' first; "
                                      "it then listens for `seconds` (default 10, after a chime).",
    parameters_json_schema={"type": "object", "properties": {"seconds": {"type": "number"}}})

# The live (talking) model is poor at reading a still picture: it answered before looking, or made up
# errors that weren't there. So a reading model looks and writes down exactly what's there, and the
# live brain talks about that (and remembers it: "and the second error?" works).
EYES = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash"]
READ_SCREEN = ("This is a screenshot of {what} on the user's laptop. They asked: \"{question}\".\n"
               "Write down exactly what's relevant: quote every error or message word for word (with file names, "
               "line numbers, numbers, names), in order from top to bottom, then briefly what it means and how to "
               "fix it. If it isn't about errors, describe what on screen answers the question. Only what you can "
               "really read in the picture; if it's unreadable or not there, say so. Plain text, no markdown.")

def screenshot(where="window"):
    # A JPEG of the window they're using (or the whole screen), big enough to read error text
    import io
    import win32gui
    from PIL import ImageGrab
    hwnd = pc.target_window() if where != "screen" else None
    if hwnd and win32gui.IsIconic(hwnd):
        hwnd = None  # (minimized: show the screen instead)
    shot = (ImageGrab.grab(bbox=win32gui.GetWindowRect(hwnd), all_screens=True) if hwnd
            else ImageGrab.grab(all_screens=True))
    shot.thumbnail((1920, 1920))
    buffer = io.BytesIO()
    shot.convert("RGB").save(buffer, "JPEG", quality=85)
    return buffer.getvalue(), (f"the window '{win32gui.GetWindowText(hwnd)[:80]}'" if hwnd else "the whole screen")

def read_picture(picture, what, question):
    # The reading model's notes on the screenshot (tries the next model if one is busy)
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    ask = READ_SCREEN.format(what=what, question=question or "What's on the screen?")
    for model in EYES:
        try:
            reply = client.models.generate_content(model=model, contents=[
                types.Part.from_bytes(data=picture, mime_type="image/jpeg"), ask])
            if reply.text:
                return reply.text.strip()
        except Exception as e:
            print(f"  (eyes: {model} failed: {str(e)[:80]})")
    return "Couldn't read the screen right now (the picture reader is busy). Say so."

def look(where="window", question=""):
    picture, what = screenshot(where)
    seen = read_picture(picture, what, question)
    return f"Looked at {what}. What it shows:\n{seen}"

def declarations():
    # The old brain's tools, in Gemini's format (same names, descriptions and settings), plus end_talk
    found = [END_TALK, NOT_FOR_ME, LOOK, IDENTIFY_SONG]
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

def sound_level(pcm, loud):
    # How loud a piece of 16-bit sound is, 0 to 1 (loud = the volume that counts as full)
    samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], np.int16).astype(np.float32)
    return min(float(np.sqrt(np.mean(samples ** 2))) / loud, 1.0) if samples.size else 0.0

def run_tool(name, args, heard):
    # Runs one tool in a background thread. Tools check the user's own words for risky things
    # (typing, sending, Enter, which Chrome account), so give them what was heard this turn.
    state.last_user_text = heard
    print(f"  [live tool] {name} {args}")
    result, worked = tools.run_tool(name, args)
    print(f"  [result] {result[:300]}")
    return result

# ---------- The phone: the same brain through Telegram ----------
# A message from the phone (text, a voice note, or a photo already read) goes into its own short live talk
# with the same instructions, notebook, memory and tools. Its answer comes back as words AND voice, so a
# voice note gets a voice note back. (telegram_bot.py calls phone_turn; the old brain is only the backup.)
PHONE = """This message comes through their PHONE (Telegram): they may be away from the laptop. Things you DO
still happen on the laptop. Keep it short, like a text from a friend. "Send me X" = send it to the phone
(send_to_phone for text or a screenshot, send_file_to_phone for a file). A bare link or text they shared:
ask if they want it opened on the laptop or copied there. Never call look unless they ask about the laptop's
screen (they can't see it); send a screenshot instead if they want to see it."""

async def phone_talk(text="", sound=b""):
    # One phone message -> (what they said, what Mind said, Mind's voice at 24 kHz, tools used)
    settings = config()
    settings.system_instruction = instructions() + "\n" + PHONE
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    heard, said, voice, did = [], [], bytearray(), []
    async with client.aio.live.connect(model=MODEL, config=settings) as session:
        if sound:
            for i in range(0, len(sound), 3200):
                await session.send_realtime_input(audio=types.Blob(data=sound[i:i + 3200], mime_type=f"audio/pcm;rate={MIC_RATE}"))
            await session.send_realtime_input(audio=types.Blob(data=bytes(MIC_RATE * 2), mime_type=f"audio/pcm;rate={MIC_RATE}"))
            await session.send_realtime_input(audio_stream_end=True)  # (the voice note is over)
        else:
            await session.send_realtime_input(text=text)
        nudged = False
        while True:
            async for reply in session.receive():
                if reply.data:
                    voice += reply.data
                if reply.tool_call:
                    answers = []
                    for call in reply.tool_call.function_calls:
                        args = dict(call.args or {})
                        if call.name == "look":
                            result = await asyncio.to_thread(look, args.get("where", "window"), args.get("question", ""))
                        elif call.name in ("end_talk", "not_for_me"):
                            result = "Okay."
                        else:
                            result = await asyncio.to_thread(run_tool, call.name, args, "".join(heard) or text)
                        did.append(f"{call.name}: {result[:80]}")
                        answers.append(types.FunctionResponse(id=call.id, name=call.name, response={"result": result}))
                    await session.send_tool_response(function_responses=answers)
                talk = reply.server_content
                if not talk:
                    continue
                if talk.input_transcription and talk.input_transcription.text:
                    heard.append(talk.input_transcription.text)
                if talk.output_transcription and talk.output_transcription.text:
                    said.append(talk.output_transcription.text)
                if talk.turn_complete and said:
                    return "".join(heard).strip() or text, "".join(said).strip(), bytes(voice), did
                if talk.turn_complete and did and not nudged:
                    nudged = True  # a tool ran but nothing was said yet: ask for the answer
                    await session.send_realtime_input(text="(The tool finished. Tell me the result now.)")

def phone_turn(text="", sound=b""):
    # From telegram_bot's thread: returns (heard, said, voice) or None if Live couldn't answer
    try:
        heard, said, voice, did = asyncio.run(asyncio.wait_for(phone_talk(text, sound), 60))
    except Exception as e:
        print("Phone (live) failed, using the backup brain:", str(e)[:150])
        return None
    import diary
    diary.write(heard, did, said)  # so the laptop talk remembers it too
    return heard, said, voice

# ---------- The page: sleeps, wakes on "Mind", talks ----------
page = None   # the live page that's connected now (only one)
loop = None   # the web server's event loop (wake() is called from main.py's thread)

REST_SECONDS = 300  # Live couldn't connect (free limit, Google down): the backup brain answers for 5 minutes
resting_until = 0.0

def ready():
    # Is the hidden live page connected and asleep (and Live not resting), so a "Mind" can wake it?
    return page is not None and not page.talking and time.time() >= resting_until

def typed(text):
    # A command typed in the HUD or the reactor's box: the same live brain answers it (out loud), so typed
    # and spoken talk share one memory (typed ones went to the backup brain, which didn't know the talk).
    if page is None or not profile.get("live", True):
        return False
    if page.talking and getattr(page, "session", None):
        asyncio.run_coroutine_threadsafe(page.type_in(text), loop)  # a talk is going on: into that talk
        return True
    return wake(b"", text, typed=True)

def wake(sound=b"", text="", idle=IDLE_SECONDS, typed=False):
    # Called from main.py when the old ears heard "Mind": start a talk with what was just said
    # (the recording, so "Mind, play X" in one breath works). Waits until Google answered the call.
    # Returns False if Live isn't ready or couldn't connect: then the backup brain takes this command.
    if not ready():
        return False
    state.live = True  # right away, so the old ears don't grab the mic meanwhile
    connected = threading.Event()
    loop.call_soon_threadsafe(page.start, sound, text, connected, idle, typed)
    if connected.wait(10) and page and page.connected_ok:
        return True
    rest()
    state.live = False
    return False

def announce(lines):
    # Reminders, alerts, "Claude is done", app notices: said in the live voice (not the old one), and
    # the mic stays open ANNOUNCE_IDLE seconds, so they can just answer ("okay, continue there").
    # Returns False if Live isn't ready: main.py says them in the old voice then.
    if not lines or not ready() or not profile.get("live", True):
        return False
    text = ("(This is NOT the user talking. It's your own announcement: say it to them now, out loud, in your "
            "own words but keep every detail (names, times, what it says). Keep it short, no question at the end. "
            "Then stop; they may reply.)\n" + "\n".join(lines))
    return wake(b"", text, idle=ANNOUNCE_IDLE)

def feed(sound):
    # For Claude's tests: a recording goes into the talk going on, as if said into the mic right now
    # (paced like real speech, then a pause). The page's own mic is ignored meanwhile.
    if page is None or not page.talking:
        return False
    page.feeding = True
    try:
        for i in range(0, len(sound), 3200):
            loop.call_soon_threadsafe(page.audio.put_nowait, sound[i:i + 3200])
            time.sleep(0.1)
        for _ in range(20):
            loop.call_soon_threadsafe(page.audio.put_nowait, bytes(3200))  # 2 s of quiet: "I'm done talking"
            time.sleep(0.1)
    finally:
        page.feeding = False
    return True

def rest():
    # Live failed to connect: use the backup brain for a while, and say so once
    global resting_until
    if time.time() >= resting_until:
        print("(Live couldn't connect, the backup brain answers for 5 minutes)")
        state.alerts.append("Heads up, Sir: my live brain is resting for a bit, my backup brain is answering for now.")
    resting_until = time.time() + REST_SECONDS

class Page:
    def __init__(self, ws):
        self.ws = ws
        self.wanted = asyncio.Event()  # a talk should start
        self.audio = asyncio.Queue()   # mic sound from the page during a talk
        self.talking = False
        self.stop_now = False
        self.closed = False  # the page went away (closed, reloaded, M.I.N.D's window shut)
        self.first_sound, self.first_text = b"", ""
        self.connected, self.connected_ok = None, False  # (see start)
        self.quiet = False
        self.feeding = False  # a test recording is going in (feed): the real mic waits
        self.song_ear = None  # while a hummed song is recorded: the sound collects here
        self.turn_sound = bytearray()  # what the mic heard this turn (for the voice check)
        self.voice_checked, self.turn_number = False, 0
        self.idle = IDLE_SECONDS  # quiet this long = back to sleep (shorter after an announcement)

    def start(self, sound=b"", text="", connected=None, idle=IDLE_SECONDS, typed=False):
        # connected: set once Google answered (or failed), so main.py knows whether Live took the command
        # typed: the text is their own typed command (kept as what they said), not M.I.N.D's announcement
        self.first_sound, self.first_text, self.stop_now, self.idle = sound, text, False, idle
        self.first_typed = typed
        self.connected, self.connected_ok = connected, False
        self.wanted.set()

    def say_connected(self, ok):
        self.connected_ok = ok
        if getattr(self, "connected", None):
            self.connected.set()

    async def read(self):
        # Everything the page sends: mic sound, and "start"/"stop" from a tap on its orb
        while True:
            message = await self.ws.receive()
            if message.get("type") == "websocket.disconnect":
                self.closed = True  # a talk going on ends too (watch() sees this)
                return
            if message.get("bytes"):
                if self.talking and not self.feeding:
                    self.audio.put_nowait(message["bytes"])
                    if time.time() > getattr(self, "clock", {}).get("voice_until", 0):
                        self.turn_sound.extend(message["bytes"])  # (for the voice check; not M.I.N.D's own voice)
                        del self.turn_sound[:-16000 * 2 * 12]   # (the last 12 seconds are enough)
                    if time.time() > getattr(self, "clock", {}).get("voice_until", 0):
                        state.set_level(sound_level(message["bytes"], 5000))  # (the HUD's dots move with your voice)
            elif message.get("text"):
                asked = json.loads(message["text"])
                if asked.get("start") and not self.talking:
                    state.live = True
                    self.start()
                if asked.get("stop"):
                    self.stop_now = True
                if asked.get("problem"):
                    print("(Live page says:", asked["problem"] + ")")  # its voice check, or the mic couldn't open

    async def talk(self):
        # One conversation, from "Mind" until bye / quiet / a tap
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.talking, state.live = True, True
        while not self.audio.empty():
            self.audio.get_nowait()  # old sound from before the talk
        self.heard, self.said, self.did = [], [], []  # this turn: your words, its words, the tools it used
        self.you_shown = False  # (a typed command is already in the HUD chat: don't show it twice)
        self.turn_sound, self.voice_checked, self.turn_number = bytearray(), False, 0
        if getattr(self, "first_typed", False):
            self.heard, self.you_shown = [self.first_text], True
        self.clock = {"active": time.time(), "voice_until": 0.0, "ending": 0, "done": False}  # ending = when end_talk was called
        self.clock["before_turn"] = self.clock["active"]
        self.quiet = False  # this turn was "not for me": muted and forgotten
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
            state.set_level(0)
            state.set_status("waiting")
            print("(Live: back to sleep)")
            try:
                await self.ws.send_json({"sleep": True})  # the page closes its mic (its last words still play)
            except Exception:
                pass

    def finish_turn(self):
        # A turn is over: show it in the HUD chat / floating reactor, and keep it in the diary.
        # A "not for me" turn (family, TV) is forgotten: not shown, not saved anywhere.
        you, mind = "".join(self.heard).strip(), "".join(self.said).strip()
        if self.quiet:
            # (stays muted until someone speaks again: Google ends the tool's turn first, then may add
            # a little turn of its own, which once came out as "N/A")
            if you:
                print("(Not for me: stayed quiet)")
            you = mind = ""
        if you:
            print("You (live):", you)
            if not self.you_shown:
                state.add_message("you", you)
        self.you_shown = False
        if mind:
            print("M.I.N.D (live):", mind)
            state.add_message("mind", mind)
        if you or mind:
            import diary
            diary.write(you, self.did, mind)  # so "what did we talk about yesterday?" works
        if you or mind:
            self.turn_number += 1
        self.turn_sound = bytearray()
        self.voice_checked = False
        self.heard.clear()
        self.said.clear()
        self.did.clear()

    async def connection(self, client, first):
        # One connection to Google. Returns True if it should reconnect (Google's ~10-minute limit),
        # False when the talk is over (goodbye, a tap, or quiet).
        clock = self.clock
        try:
            async with client.aio.live.connect(model=MODEL, config=config(self.ticket)) as session:
                self.session = session  # (background jobs and typed commands talk into it)
                self.say_connected(True)
                if first and self.first_sound:  # what they said with "Mind" (recorded by the old ears)
                    for i in range(0, len(self.first_sound), 3200):
                        await session.send_realtime_input(audio=types.Blob(
                            data=self.first_sound[i:i + 3200], mime_type=f"audio/pcm;rate={MIC_RATE}"))
                elif first and self.first_text:
                    await session.send_realtime_input(text=self.first_text)

                async def to_gemini():
                    while True:
                        chunk = await self.audio.get()
                        if self.song_ear is not None:
                            self.song_ear.extend(chunk)  # (recording a hummed song: not sent to the talk)
                            continue
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
                        if (not talking_now and not clock.get("busy")
                                and now - max(clock["active"], clock["voice_until"]) > self.idle):
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
        if (reply.data or reply.tool_call) and not self.quiet and not self.voice_checked:
            await self.someone_else()  # (before it speaks or does anything)
        if reply.data and self.quiet:
            pass  # a "not for me" turn: whatever it says is not played
        elif reply.data:
            if clock.get("tool_done"):
                print(f"   (answered {now - clock['tool_done']:.1f}s after the tool)")
                clock["tool_done"] = 0
            state.set_status("speaking")
            clock["voice_until"] = max(clock["voice_until"], now) + len(reply.data) / VOICE_BYTES
            await self.ws.send_bytes(reply.data)
            state.set_level(sound_level(reply.data, 4000))  # (and with M.I.N.D's own voice while it speaks)
        if reply.tool_call and self.quiet:
            # Someone else's voice (or "not for me"): no tool runs, nothing is said
            await session.send_tool_response(function_responses=[types.FunctionResponse(
                id=call.id, name=call.name, response={"result": "That wasn't the owner talking to you: do nothing, say nothing."})
                for call in reply.tool_call.function_calls])
            return False
        if reply.tool_call:
            state.set_status("thinking")
            answers = []
            for call in reply.tool_call.function_calls:
                if call.name == "not_for_me":
                    self.quiet = True  # muted till this turn ends; it doesn't keep the talk awake either
                    clock["active"] = clock["before_turn"]
                    answers.append(types.FunctionResponse(id=call.id, name=call.name,
                                                          response={"result": "Stay silent: say nothing."}))
                    continue
                if call.name == "end_talk":
                    clock["ending"] = now
                    result = "Okay, going to sleep after your goodbye."
                elif call.name == "look":
                    args = dict(call.args or {})
                    print(f"  [live tool] look {args}")
                    result = await asyncio.to_thread(look, args.get("where", "window"), args.get("question", ""))
                    print(f"  [result] {result[:300]}")
                    self.did.append(f"look: {result[:80]}")
                elif call.name == "identify_song":
                    clock["busy"] = clock.get("busy", 0) + 1
                    try:
                        result = await self.hear_song(float((call.args or {}).get("seconds") or 10))
                    finally:
                        clock["busy"] -= 1
                    print(f"  [result] {result[:300]}")
                    self.did.append(f"identify_song: {result[:80]}")
                elif call.name in SLOW_TOOLS:
                    result = self.in_background(session, call.name, dict(call.args or {}))
                    self.did.append(f"{call.name}: started")
                else:
                    clock["busy"] = clock.get("busy", 0) + 1  # (the quiet timer waits while a tool runs)
                    try:
                        result = await asyncio.to_thread(run_tool, call.name, dict(call.args or {}), "".join(self.heard))
                    finally:
                        clock["busy"] -= 1
                    self.did.append(f"{call.name}: {result[:80]}")
                answers.append(types.FunctionResponse(id=call.id, name=call.name, response={"result": result}))
            await session.send_tool_response(function_responses=answers)
            if not self.quiet:
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
            if self.said:
                self.finish_turn()  # you started a new turn
            if not self.heard:
                self.idle = IDLE_SECONDS  # they replied (after an announcement too): a normal talk now
                clock["before_turn"] = clock["active"]  # (if it turns out "not for me", the talk isn't kept awake)
                self.quiet = False  # someone speaks again: a new turn, not muted
            clock["active"] = now
            if now >= clock["voice_until"]:
                state.set_status("listening")  # (not while it's still talking: room noise flipped it mid-sentence)
            self.heard.append(talk.input_transcription.text)
            await self.ws.send_json({"you": talk.input_transcription.text})
        if (talk.output_transcription and talk.output_transcription.text and not self.quiet
                and not re.fullmatch(r"\s*<[^>]*>\s*", talk.output_transcription.text)):
            # (Google sometimes sends a placeholder like "<no speech detected>": that's not something it said)
            self.said.append(talk.output_transcription.text)
            await self.ws.send_json({"mind": talk.output_transcription.text})
        if talk.turn_complete and self.quiet:
            self.finish_turn()  # (forgets it: not shown, not in the diary)
        elif talk.turn_complete:
            spoke = bool(self.said)
            self.finish_turn()
            clock["active"] = time.time()
            await self.ws.send_json({"done": True})
            if clock["ending"] and spoke:
                clock["done"] = True  # its goodbye was said (Google ends the tool's turn first, then says it)
        return False

    async def hear_song(self, seconds):
        # Records the mic for a few seconds (after a chime), then names the song
        import finder
        import watcher
        seconds = max(5.0, min(seconds, 20.0))
        print(f"  [live tool] identify_song (listening {seconds:.0f} s)")
        watcher.chime()
        await asyncio.sleep(0.6)  # (the chime itself isn't part of the song)
        self.song_ear = bytearray()
        state.set_status("listening")
        try:
            await asyncio.sleep(seconds)
            sound = bytes(self.song_ear)
        finally:
            self.song_ear = None
        state.set_status("thinking")
        return await asyncio.to_thread(finder.name_that_song, sound, MIC_RATE)

    async def someone_else(self):
        # Is this turn someone else talking (not the owner)? Then M.I.N.D stays quiet and does nothing.
        # Not checked: the first turn (the old ears already checked the voice that said "Mind"), typed turns,
        # and any turn where "Mind" is said.
        if self.voice_checked:
            return self.quiet
        self.voice_checked = True
        heard = "".join(self.heard)
        if self.turn_number == 0 or self.you_shown or not heard.strip() or re.search(r"\bmind\b", heard, re.I):
            return False
        import speaker
        import audio
        if not speaker.active():
            return False  # (no voiceprint learned, or the lock is off)
        sound = bytes(self.turn_sound)
        _, score = await asyncio.to_thread(speaker.check, sound, audio.music_playing())
        if score >= profile.get("live_voice_match", LIVE_MATCH):
            print(f"   (your voice: {score:.2f})")
            return False
        print(f"(Not your voice, stayed quiet: match {score:.2f}, heard: {heard[:60]})")
        self.quiet = True
        self.clock["active"] = self.clock["before_turn"]  # (it doesn't keep the talk awake either)
        return True

    async def type_in(self, text):
        # A typed command during a talk: a new turn with their typed words
        if self.said:
            self.finish_turn()
        self.heard.append(text)
        self.you_shown, self.quiet, self.idle = True, False, IDLE_SECONDS
        self.clock["active"] = time.time()
        await self.session.send_realtime_input(text=text)

    def in_background(self, session, name, args):
        # A slow tool (an animation, 30-60 s): it runs on its own, so "am I audible?" still gets an answer
        # meanwhile (it used to block the talk, and the quiet timer put M.I.N.D to sleep before it was done).
        # When it's ready: told inside the talk if it's still going, else said as an announcement.
        heard = "".join(self.heard)
        what = f"{name.replace('create_', '')}: {args.get('idea', '')}".strip(": ")
        running_jobs.add(what)

        async def job():
            try:
                result = await asyncio.to_thread(run_tool, name, args, heard)
            finally:
                running_jobs.discard(what)
            if self.talking and not self.closed and getattr(self, "session", None) is session:
                try:
                    await session.send_realtime_input(text=f"(Your background job '{name}' finished: {result} "
                                                           "Tell them in a few words now.)")
                    self.clock["active"] = time.time()
                    return
                except Exception:
                    pass
            state.alerts.append(f"Sir, that {name.replace('create_', '')} is ready: {result}")

        asyncio.create_task(job())
        return ("Started; it takes 30-60 seconds and appears on the HUD by itself. Tell them it's coming in a few "
                "words, and keep talking with them meanwhile. You'll be told when it's ready.")

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
                me.say_connected(False)  # (if it never connected, main.py hands the command to the backup)
                await ws.send_json({"error": str(e)[:200]})
    finally:
        reader.cancel()
        if page is me:
            page = None
        state.live = False
