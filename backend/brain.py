# Brain: understands what you say (Groq LLM) and decides which tools to use.
import os
import re
import json
import threading
import time
import datetime
from groq import Groq, RateLimitError
from memory import profile, tamil_mode, BASE_DIR
from tools import TOOLS, ENDS_CONVERSATION, run_tool, quick_reply, upcoming_reminders, routines, tools_for
import diary
import pc
import state
import limits

# max_retries=0: if a model is busy, switch to the next one right away instead of waiting
client = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0)

PERSONALITY = """You are M.I.N.D, the user's AI buddy on their Windows laptop (like J.A.R.V.I.S., but chill).
Everything you say is spoken aloud. Rules:
- Talk like a close friend: casual, warm, a bit funny ("yeah", "got it", "oh nice"). Never "Certainly".
- One short sentence, two at most (briefing/news up to four). No lists, markdown or emojis.
- No "anything else?" endings.
- Be a person, not a command runner: add a tiny natural touch when it fits (the song, the late hour, a joke).
- If they're low (mood off, sad, tired, bored, stressed, angry), be a caring friend first: ask what's up,
  cheer them up, maybe offer a song or a joke. No tools unless they ask.
- Use tools to act (pick the best one even for vague asks). Never claim what a tool didn't do; if one
  fails, try another way or say so.
- Several asks at once ("open X, play Y and remind me Z"): do ALL of them, then ONE short reply for all.
- Weather, news, battery, live facts: ALWAYS use the tool, never guess. General knowledge: just answer.
- Hearing can be wrong: if the meaning is clear, go with it; else ask.
- Act only on the LATEST message. "(Already done: ...)" notes = finished: never redo or say them.
- Fillers ("oh", "hmm", "cool") get a short reply, no tools.
- After acting, confirm in a few words; no follow-up questions unless it failed.
- Always answer (they called you); short phrases like "study mode" may be a routine.
- Never invent facts about the user; change saved details only when clearly asked
  ("don't remember that" = remember_fact forget).
- Tamil: write it in Tamil script. "Say" means speak, never type.
- stop / wait / enough / not now / bye / that's all = end_conversation. "Stop" never means close or undo."""

# Models that work on this Groq account, tried in order (with their settings).
# Each has its own free limit (8000 tokens a minute), so more models = more requests per minute.
# qwen sometimes repeats a tool call; think() blocks repeats, so it's safe as the last backup.
# Fastest first. Groq answers in ~0.6s; Google Gemini (free, its own daily allowance per model)
# takes over when Groq's free limit is used up (~2s). Gemini needs GEMINI_API_KEY in .env.
MODELS = [
    ("openai/gpt-oss-120b", {"reasoning_effort": "low"}),
    ("openai/gpt-oss-20b", {"reasoning_effort": "low"}),
    ("gemini-3.5-flash-lite", {}),
    ("gemini-3.1-flash-lite", {}),
    ("gemini-3.5-flash", {}),
    ("qwen/qwen3.8-27b", {}),
]
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GeminiBusy = RateLimitError  # becomes the openai package's "busy" error once it's loaded
gemini = None
gemini_ready = threading.Event()

def load_gemini():
    # The openai package takes ~1 s to load, so it loads in the background (M.I.N.D starts faster)
    global gemini, GeminiBusy
    try:
        from openai import OpenAI, RateLimitError as busy
        GeminiBusy = busy
        gemini = OpenAI(api_key=GEMINI_KEY, max_retries=0, timeout=20,
                        base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    finally:
        gemini_ready.set()

if GEMINI_KEY:
    threading.Thread(target=load_gemini, daemon=True).start()
else:
    MODELS = [m for m in MODELS if not m[0].startswith("gemini")]
active = 0  # index of the model that worked last time

# Words that claim an action was done (if no tool ran, the model is pretending)
CLAIMS_ACTION = re.compile(r"\b(here's|here is|playing|opened|opening|turned|closed|locked|started|sent|saved|"
                           r"paused|skipped|muted|set (it|the|a|your)|done)\b"
                           r"|\b\w+ing (it|that|this|the|your|you|up|down|now)\b"  # "Locking it up", "Locking up"
                           r"|இதோ|ட்டேன்|ச்சேன்|ந்தேன்|த்தேன்|ஆச்சு|ட்டாச்சு", re.I)  # Tamil "done it", "there you go"
GLUED = re.compile(r"(?<=[a-z0-9%:)])[.!?](?=[A-Z][a-z])")
TAMIL_LETTERS = re.compile(r"[஀-௿]")
# "I can't / I don't have a way to..." (it may just have been missing the right tool)
CANT = re.compile(r"\b(can't|cannot|can not|unable|not able|no way to|don't have (a|the|any) (tool|way|access))\b", re.I)
# Words that join several requests ("open dai AND play lofi, THEN remind me...")
SEVERAL = re.compile(r"\b(and|then|also|plus)\b|,|அப்புறம்|அதோட", re.I)
# Words that mean "type/write something" (English and Tamil); typing needs one of these
ASKED_TO_TYPE = re.compile(r"\b(type|typing|write|writing|enter|fill|paste|jot)\b|எழுது|டைப்", re.I)

MAX_HISTORY = 12  # 6 things you said + 6 replies (all sent with every request, so kept small)
cancelled = threading.Event()  # set when you cancel a slow thought (orb tap or "stop")

# Past turns, saved in history.json so M.I.N.D remembers your chat after a restart
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)[-MAX_HISTORY:]
    except Exception:
        return []

def save_history():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)

history = load_history()
MAX_STEPS = 5     # most tool rounds for one request

def system_prompt(user_text=""):
    now = datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    lines = [PERSONALITY, f"\nRight now it is {now}."]
    about = []
    if profile.get("name"):
        about.append(f"call them {profile['name']} (now and then)")
    if profile.get("real_name"):
        about.append(f"real name {profile['real_name']}")
    if profile.get("city"):
        about.append(f"lives in {profile['city']}")
    if about:
        lines.append("The user: " + "; ".join(about) + ".")
    projects = pc.project_names(10)
    if projects:
        # So "open dai" means their project, not some app (it once guessed "DaVinci Resolve")
        lines.append("Their code projects (open_folder): " + ", ".join(projects))
    if profile.get("facts"):
        lines.append("Things you remember about the user: " + "; ".join(profile["facts"]))
    if profile.get("shortcuts"):
        saved = ", ".join(f"{k} = {v}" for k, v in profile["shortcuts"].items())
        lines.append("The user's saved website shortcuts: " + saved)
    lines.append("All routines (run_routine): " + ", ".join(routines()))
    if state.tone:
        # From their voice (louder/faster = maybe frustrated or excited; quieter/slower = maybe tired or low)
        lines.append(f"Their voice just now: {state.tone}. Read it together with their words.")
        state.tone = ""  # only for this request
    if pc.in_front():
        lines.append("In front of them now: " + pc.in_front())  # so "pause this" / "close this" make sense
    if upcoming_reminders():
        lines.append("Upcoming reminders: " + "; ".join(upcoming_reminders()))
    if user_text and not TAMIL_LETTERS.search(user_text) and not tamil_mode():
        lines.append("LANGUAGE: reply in English (they spoke English).")
    if TAMIL_LETTERS.search(user_text) and not tamil_mode():
        lines.append("LANGUAGE: The user just spoke Tamil. Reply in natural spoken Tamil (Tamil script), "
                     "casual spoken Chennai Tamil, like friends talk (not formal written Tamil). Keep app, website and song names in English. "
                     "Talk like a friend.")
    if tamil_mode():
        lines.append("LANGUAGE: Tamil mode is on. Always reply in natural spoken Tamil (Tamil script), "
                     "casual spoken Chennai Tamil, like friends talk (not formal written Tamil). Keep app, website and song names in English. "
                     "The user may speak Tamil, English or a mix; their English words may be written in "
                     "Tamil letters (e.g. வொலியும் = volume). Talk like a friend (never formal, never திரு). "
                     "If they ask for English, you MUST call update_profile with language=english "
                     "(just saying it does nothing).")
    return {"role": "system", "content": "\n".join(lines)}

def for_groq(messages):
    # Groq doesn't accept Gemini's extra fields on tool calls, so leave them out for Groq
    clean = []
    for m in messages:
        if m.get("tool_calls"):
            m = {**m, "tool_calls": [{k: v for k, v in c.items() if k in ("id", "type", "function")}
                                     for c in m["tool_calls"]]}
        clean.append(m)
    return clean

def for_gemini(messages):
    # Gemini wants a "thought signature" on every earlier tool call. Calls made by Groq don't have one,
    # so give them Google's placeholder (meant for exactly this: history from another model)
    clean = []
    for m in messages:
        if m.get("tool_calls"):
            m = {**m, "tool_calls": [c if c.get("extra_content") else
                                     {**c, "extra_content": {"google": {"thought_signature": "skip_thought_signature_validator"}}}
                                     for c in m["tool_calls"]]}
        clean.append(m)
    return clean

def ask_model(messages, tools=TOOLS):
    # Try the model that worked last, then the others. Returns (reply message, problem).
    # problem is None, "busy" (free limit reached) or "offline".
    global active
    for attempt in range(2):
        # Fastest first, skipping models that are resting (they're tried last, just in case)
        order = sorted(range(len(MODELS)), key=lambda i: (limits.resting(MODELS[i][0]), i))
        wait = None  # shortest time until a busy model is free again
        for i in order:
            name, settings = MODELS[i]
            if name.startswith("gemini"):
                gemini_ready.wait(10)  # still loading (only right after start)
                if gemini is None:
                    continue
            api = gemini if name.startswith("gemini") else client
            try:
                raw = api.chat.completions.with_raw_response.create(
                    model=name, messages=for_groq(messages) if api is client else for_gemini(messages),
                    tools=tools, **settings)
                limits.note(name, raw.headers)  # how much is left today (for the HUD)
                active = i
                return raw.parse().choices[0].message, None
            except (RateLimitError, GeminiBusy) as e:
                seconds = float(e.response.headers.get("retry-after", 60))
                limits.note_busy(name, seconds)
                print(f"Model {name} is at its free limit (free again in {seconds:.0f}s)")
                wait = seconds if wait is None else min(wait, seconds)
            except Exception as e:
                print(f"Model {name} failed: {str(e)[:120]}")
        if wait is None:
            return None, "offline"
        if attempt == 0 and wait <= 8:
            print(f"All models busy, waiting {wait:.0f}s...")
            time.sleep(wait + 0.5)
    return None, "busy"

def remember(user_text, reply_text, actions):
    # Save one turn. What was DONE is saved too, so the brain knows it's finished
    # and doesn't do it again when you just say "oh" or "cool".
    diary.write(user_text, actions, reply_text)  # long-term memory ("what did you play yesterday?")
    if actions:
        reply_text += "\n(Already done: " + "; ".join(actions) + ")"
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply_text})
    del history[:-MAX_HISTORY]
    save_history()

def first_answer(reply):
    # Sometimes the model sends two answers stuck together ("...free on C:.All good, Sir. Battery at...").
    # The second one starts right after a full stop with no space: keep only the first.
    stuck = GLUED.search(reply)
    if stuck and len(reply) - stuck.end() > 15:
        return reply[:stuck.end()].strip()
    return reply

def looks_broken(reply):
    # Models sometimes glitch and return a long mess of dots
    return len(reply) > 500 or reply.count("…") + reply.count("...") > 4

thinking = threading.Lock()  # one thought at a time (phone and laptop could ask together)

def think(text):
    with thinking:
        return think_now(text)

def think_now(text):
    # Returns (reply to speak, action). action is None, "end" or "shutdown".
    cancelled.clear()
    messages = [system_prompt(text)] + history + [{"role": "user", "content": text}]
    action = None
    done = set()  # tools already run for this request (so nothing runs twice)
    nudged = False  # already asked it once to answer properly
    pretends = 0  # times it claimed an action without calling a tool
    english_asked = False  # already asked it to answer in English
    checked_all = False  # already asked "did you do everything?" (several asks in one go)
    offered = tools_for(text)  # only the tools this request may need (smaller, faster requests)
    actions = []  # results of the tools, saved in history
    for _ in range(MAX_STEPS):
        msg, problem = ask_model(messages, offered)
        if problem == "busy":
            return "I've hit my free thinking limit for the moment, Sir. Give me a minute.", action
        if problem == "offline":
            return "Sorry, I couldn't reach my brain. Check the internet.", action

        # No tools needed: this is the final answer
        if not msg.tool_calls:
            reply = re.sub(r"<think>.*?</think>", "", msg.content or "", flags=re.S)
            reply = re.sub(r"\(Already done:.*?\)", "", reply, flags=re.S).strip()  # private note, never say it
            reply = re.sub(r"^\s*\[[a-z ]+\]\s*", "", reply, flags=re.I)  # drop tags like "[speech]"
            reply = first_answer(reply)
            if not reply and not actions and not nudged:
                # An empty answer with no action (it once made the phone say "Done." for nothing): try again
                print("  (Empty answer, asking again)")
                nudged = True
                messages.append({"role": "user", "content": "You gave no answer. Do what I asked using your "
                                 "tools (several if needed), or reply in words."})
                continue
            if reply.lower() in ("[silent]", "silent", "") and not actions:
                return "", action  # nothing to say
            if not actions and CLAIMS_ACTION.search(reply):
                if pretends < 2:
                    # It SAID it did something ("here's Rathinamo") without using a tool: make it really do it
                    print("  (Said it did something without doing it, asking again)")
                    pretends += 1
                    messages.append({"role": "assistant", "content": reply})
                    messages.append({"role": "user", "content": "You didn't call any tool, so nothing happened. "
                                     "If I asked for an action, call the right tool now (a function call, not words). "
                                     "If not, just repeat your answer."})
                    continue
                print("  (Still pretending, saying so honestly)")
                reply = "Hmm, I didn't manage that one. Say it again?"
            if (TAMIL_LETTERS.search(reply) and not TAMIL_LETTERS.search(text) and not tamil_mode()
                    and "tamil" not in text.lower() and not english_asked):
                # You spoke English but it answered in Tamil (old Tamil chat in the history): redo in English.
                # Tamil only when you speak Tamil, ask for it, or switch to Tamil mode.
                print("  (Answered in Tamil to English, asking for English)")
                english_asked = True
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": "I spoke English: say that again in English."})
                continue
            if offered is not TOOLS and not actions and CANT.search(reply):
                # It only had some of its tools and says it can't: give it all of them and try again
                print("  (Said it can't with only some tools, giving it all tools)")
                offered = TOOLS
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": "You now have ALL your tools. Do what I asked."})
                continue
            tools_used = {key[:key.index("{")] for key in done}
            if SEVERAL.search(text) and len(tools_used) == 1 and not checked_all:
                # You asked for several things but only one kind of action ran ("open dai and play lofi"
                # once only played lofi): make sure nothing was skipped
                print("  (Several asks but one action, checking nothing was skipped)")
                checked_all = True
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": "Did you do EVERYTHING I asked? If something is "
                                 "left, do it now with tools. If all is done, just repeat your answer."})
                continue
            if looks_broken(reply):
                print("(Brain gave a broken reply, not saying it)")
                reply = "Done, Sir." if actions else "Sorry, I got muddled there. Say that again?"
            reply = reply or ("Done." if actions else "Sorry, I didn't catch that.")  # did it, just no words
            remember(text, reply, actions)
            return reply, action

        # The brain wants to use tools: run each one and give it the results
        # Keep each tool call exactly as the model sent it (Gemini adds a hidden "thought signature"
        # it needs back on the next step)
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [c.model_dump(exclude_none=True) for c in msg.tool_calls]})
        quick = []  # short replies, if every tool this round was a simple one that worked
        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            key = name + json.dumps(args, sort_keys=True)
            if key in done:
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": "Already done just now, don't repeat it."})
                continue
            done.add(key)
            if cancelled.is_set():
                return "", None  # you cancelled: don't do anything
            print(f"  [tool] {name} {args}")
            if name == "type_text" and not ASKED_TO_TYPE.search(text):
                # Typing goes into whatever window is open, so only when the user asked for it
                result, worked = "Not done: only type when the user asks to type or write something.", False
            else:
                if cancelled.is_set():
                    return "", None  # you cancelled: don't do anything
                result, worked = run_tool(name, args)
            print(f"  [result] {result}")
            line = quick_reply(name, args, result) if worked else None
            quick.append(line)
            if name == "end_conversation":
                action = "end"
            elif name == "shut_down":
                action = "shutdown"
            else:
                state.add_message("tool", result[:150])  # show what was done in the HUD
                actions.append(result[:100])
                if name in ENDS_CONVERSATION and action is None:
                    action = "end"
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

        # Only simple actions that worked: answer right away, no need to ask the brain again
        # (quick replies are English, so in Tamil mode the brain answers instead)
        # If you asked for several things but only one was done this round, the brain may still be
        # doing the rest: let it finish instead of answering early ("open dai and play lofi")
        several_asked = SEVERAL.search(text) and len(quick) < 2
        if quick and None not in quick and not several_asked and not tamil_mode() and not TAMIL_LETTERS.search(text):
            lines = list(dict.fromkeys(quick))[:3]  # one short line per thing done ("Here's dai. Playing lofi.")
            reply = " ".join(line if line[-1] in ".!?" else line + "." for line in lines)
            remember(text, reply, actions)
            return reply, action
    return "Sorry, that took too many steps.", action
