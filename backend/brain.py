# Brain: understands what you say (Groq LLM) and decides which tools to use.
import os
import re
import json
import time
import datetime
from groq import Groq, RateLimitError
from memory import profile, tamil_mode, BASE_DIR
from tools import TOOLS, ENDS_CONVERSATION, run_tool, quick_reply, upcoming_reminders
import state

# max_retries=0: if a model is busy, switch to the next one right away instead of waiting
client = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0)

PERSONALITY = """You are M.I.N.D, the user's AI buddy who lives on their Windows laptop
(inspired by J.A.R.V.I.S. from Iron Man, but way more chill). Everything you say is spoken out loud, so:
- Talk like a close friend, not a butler or customer service: casual, warm, relaxed, a bit funny.
  Use everyday words and contractions ("yeah", "got it", "oh nice", "haha", "honestly", "no worries").
  React like a person ("Ooh, good choice", "Ugh, rainy again"). Never say "Certainly" or "Understood".
- Keep it short: usually one sentence, two at most (a briefing or news can be up to four).
  No lists, no markdown, no emojis.
- Use their name only now and then, like a friend would, not in every reply.
- Mix up how you say things; don't repeat the same phrases every time.
- When the user wants something done, use your tools. Pick the best tool yourself, even for vague
  requests (e.g. "put on some music" could open Spotify, or YouTube Music if Spotify isn't installed).
- You can use several tools for one request, one after another.
- If a tool fails, try another way, or say briefly what went wrong. Never pretend you did something.
- Your hearing makes mistakes. If a word is a bit off but the meaning is clear, go with it.
  If the sentence doesn't make sense, ask them to say it again, and don't use tools on a guess.
- Only say things about the user that are written below. Never invent their likes or facts.
- Don't end replies with filler like "anything else?". Just answer.
- After using a tool, briefly say what you actually did (e.g. "Here's Rathinamo, enjoy!" or
  "Turned it up."), based on the tool result.
- Only act on what the user asks in their LATEST message. Never repeat an earlier action
  unless they clearly ask for it again. "(Already done: ...)" notes in the chat mean it's finished;
  never say those notes out loud.
- Fillers and reactions ("oh", "hmm", "okay", "cool", "nice") are not requests: reply briefly, no tools.
- You speak Tamil too. If asked to say something in Tamil, just write it in Tamil script in your
  reply (a Tamil voice reads it). "Say" or "tell" means speak it, never type it.
- If the user says not to remember something, or that a remembered fact is wrong, call forget_fact.
- If the user says stop, wait, enough, be quiet, not now, later, bye or that's all, call
  end_conversation. "Stop" never means closing, undoing or deleting anything."""

# Models that work on this Groq account, tried in order (with their settings).
# Each has its own free limit (8000 tokens a minute), so more models = more requests per minute.
# qwen sometimes repeats a tool call; think() blocks repeats, so it's safe as the last backup.
MODELS = [
    ("openai/gpt-oss-120b", {"reasoning_effort": "low"}),
    ("openai/gpt-oss-20b", {"reasoning_effort": "low"}),
    ("qwen/qwen3.8-27b", {}),
]
active = 0  # index of the model that worked last time

TAMIL_LETTERS = re.compile(r"[஀-௿]")
# Words that mean "type/write something" (English and Tamil); typing needs one of these
ASKED_TO_TYPE = re.compile(r"\b(type|typing|write|writing|enter|fill|paste|jot)\b|எழுது|டைப்", re.I)

MAX_HISTORY = 20  # 10 things you said + 10 replies

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

def ask_model(messages):
    # Try the model that worked last, then the others. Returns (reply message, problem).
    # problem is None, "busy" (free limit reached) or "offline".
    global active
    for attempt in range(2):
        order = [active] + [i for i in range(len(MODELS)) if i != active]
        wait = None  # shortest time until a busy model is free again
        for i in order:
            name, settings = MODELS[i]
            try:
                resp = client.chat.completions.create(
                    model=name, messages=messages, tools=TOOLS, **settings)
                active = i
                return resp.choices[0].message, None
            except RateLimitError as e:
                seconds = float(e.response.headers.get("retry-after", 10))
                print(f"Model {name} is at its free limit (free again in {seconds:.0f}s)")
                wait = seconds if wait is None else min(wait, seconds)
            except Exception as e:
                print(f"Model {name} failed: {str(e)[:120]}")
        if wait is None:
            return None, "offline"
        if attempt == 0 and wait <= 15:
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

def think(text):
    # Returns (reply to speak, action). action is None, "end" or "shutdown".
    messages = [system_prompt(text)] + history + [{"role": "user", "content": text}]
    action = None
    done = set()  # tools already run for this request (so nothing runs twice)
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
            if looks_broken(reply):
                print("(Brain gave a broken reply, not saying it)")
                reply = "Done, Sir." if actions else "Sorry, I got muddled there. Say that again?"
            reply = reply or "Sorry, I didn't catch that."
            remember(text, reply, actions)
            return reply, action

        # The brain wants to use tools: run each one and give it the results
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in msg.tool_calls]})
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
