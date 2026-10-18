# Brain: understands what you say (Groq LLM) and decides which tools to use.
import os
import re
import json
import threading
import time
import datetime
from groq import Groq, RateLimitError
from memory import profile, tamil_mode, BASE_DIR
from tools import TOOLS, ENDS_CONVERSATION, run_tool, quick_reply, upcoming_reminders, routines
import state
import limits

# max_retries=0: if a model is busy, switch to the next one right away instead of waiting
client = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0)

PERSONALITY = """You are M.I.N.D, the user's AI buddy on their Windows laptop (like J.A.R.V.I.S., but chill).
Everything you say is spoken aloud. Rules:
- Talk like a close friend: casual, warm, a bit funny ("yeah", "got it", "oh nice"). Never "Certainly".
- One short sentence, two at most (briefing/news up to four). No lists, markdown or emojis.
- Use their name only now and then. Vary your phrases. No "anything else?" endings.
- To get things done, use tools; pick the best one yourself even for vague asks. Never claim you did
  something a tool didn't do; if a tool fails, try another way or say so.
- Weather, news, battery, time-sensitive facts: ALWAYS call the tool, never guess numbers.
- Hearing makes mistakes: if the meaning is clear, go with it; if it makes no sense, ask again (no tools).
- Act only on the LATEST message; never redo earlier actions. "(Already done: ...)" notes mean finished;
  never say them.
- Fillers ("oh", "hmm", "cool") get a short reply, no tools.
- The user said your name (or typed) to talk to you, so always answer; short phrases like "study mode"
  may be a routine name.
- Only state facts about the user that are given below; never invent. Change saved details only when
  clearly asked. "Don't remember that" = forget_fact.
- You speak Tamil: write Tamil in Tamil script (a Tamil voice reads it). "Say" means speak, never type.
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
if GEMINI_KEY:
    from openai import OpenAI, RateLimitError as GeminiBusy
    gemini = OpenAI(api_key=GEMINI_KEY, max_retries=0, timeout=20,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
else:
    MODELS = [m for m in MODELS if not m[0].startswith("gemini")]
    GeminiBusy = RateLimitError
active = 0  # index of the model that worked last time

# Words that claim an action was done (if no tool ran, the model is pretending)
CLAIMS_ACTION = re.compile(r"\b(here's|here is|playing|opened|opening|turned|closed|locked|started|sent|saved|"
                           r"paused|skipped|muted|set (it|the|a|your)|done)\b", re.I)
TAMIL_LETTERS = re.compile(r"[஀-௿]")
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
    if profile.get("name"):
        lines.append(f"The user likes to be called {profile['name']} (use it only now and then).")
    if profile.get("real_name"):
        lines.append(f"The user's real name is {profile['real_name']}.")
    if profile.get("city"):
        lines.append(f"The user lives in {profile['city']}.")
    if profile.get("facts"):
        lines.append("Things you remember about the user: " + "; ".join(profile["facts"]))
    if profile.get("shortcuts"):
        saved = ", ".join(f"{k} = {v}" for k, v in profile["shortcuts"].items())
        lines.append("The user's saved website shortcuts: " + saved)
    lines.append("All routines (run_routine): " + ", ".join(routines()))
    if upcoming_reminders():
        lines.append("Upcoming reminders: " + "; ".join(upcoming_reminders()))
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

def ask_model(messages):
    # Try the model that worked last, then the others. Returns (reply message, problem).
    # problem is None, "busy" (free limit reached) or "offline".
    global active
    for attempt in range(2):
        # Fastest first, skipping models that are resting (they're tried last, just in case)
        order = sorted(range(len(MODELS)), key=lambda i: (limits.resting(MODELS[i][0]), i))
        wait = None  # shortest time until a busy model is free again
        for i in order:
            name, settings = MODELS[i]
            api = gemini if name.startswith("gemini") else client
            try:
                raw = api.chat.completions.with_raw_response.create(
                    model=name, messages=messages if api is not client else for_groq(messages),
                    tools=TOOLS, **settings)
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
    if actions:
        reply_text += "\n(Already done: " + "; ".join(actions) + ")"
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply_text})
    del history[:-MAX_HISTORY]
    save_history()

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
    nudged = False  # already asked it once to really do what it claimed
    actions = []  # results of the tools, saved in history
    for _ in range(MAX_STEPS):
        msg, problem = ask_model(messages)
        if problem == "busy":
            return "I've hit my free thinking limit for the moment, Sir. Give me a minute.", action
        if problem == "offline":
            return "Sorry, I couldn't reach my brain. Check the internet.", action

        # No tools needed: this is the final answer
        if not msg.tool_calls:
            reply = re.sub(r"<think>.*?</think>", "", msg.content or "", flags=re.S)
            reply = re.sub(r"\(Already done:.*?\)", "", reply, flags=re.S).strip()  # private note, never say it
            reply = re.sub(r"^\s*\[[a-z ]+\]\s*", "", reply, flags=re.I)  # drop tags like "[speech]"
            if reply.lower() in ("[silent]", "silent", "") and not actions:
                return "", action  # nothing to say
            if not actions and not nudged and CLAIMS_ACTION.search(reply):
                # It SAID it did something ("here's Rathinamo") without using a tool: make it really do it
                print("  (Said it did something without doing it, asking again)")
                nudged = True
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": "You didn't call any tool, so nothing happened. "
                                 "If I asked for an action, call the right tool now. If not, just repeat your answer."})
                continue
            if looks_broken(reply):
                print("(Brain gave a broken reply, not saying it)")
                reply = "Done, Sir." if actions else "Sorry, I got muddled there. Say that again?"
            reply = reply or "Sorry, I didn't catch that."
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
        if quick and None not in quick and not tamil_mode() and not TAMIL_LETTERS.search(text):
            reply = quick[-1]
            remember(text, reply, actions)
            return reply, action
    return "Sorry, that took too many steps.", action
