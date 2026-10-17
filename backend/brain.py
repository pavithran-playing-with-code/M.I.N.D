# Brain: understands what you say (Groq LLM) and decides which tools to use.
import os
import json
import datetime
from groq import Groq
from memory import profile
from tools import TOOLS, run_tool, upcoming_reminders
import state

# max_retries=0: if a model is busy, switch to the next one right away instead of waiting
client = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0)

PERSONALITY = """You are M.I.N.D, a personal AI assistant inspired by J.A.R.V.I.S. from Iron Man.
You live on the user's Windows laptop and everything you say is spoken out loud, so:
- Keep replies short: one or two sentences. No lists, no markdown, no emojis.
- Be warm, calm and a little witty, like a loyal friend with a dry British sense of humour.
- When the user wants something done, use your tools. Pick the best tool yourself, even for vague
  requests (e.g. "put on some music" could open Spotify, or YouTube Music if Spotify isn't installed).
- You can use several tools for one request, one after another.
- If a tool fails, try another way, or say briefly what went wrong. Never pretend you did something.
- Your hearing makes mistakes. If a word is a bit off but the meaning is clear, go with it.
  If the sentence doesn't make sense, ask them to say it again, and don't use tools on a guess.
- Only say things about the user that are written below. Never invent their likes or facts.
- Don't end replies with filler like "anything else?". Just answer."""

# Models that work on this Groq account, tried in order (with their settings).
# Tested with tools: these two work well. (qwen repeated tool calls, so it's left out.)
MODELS = [
    ("openai/gpt-oss-120b", {"reasoning_effort": "low"}),
    ("openai/gpt-oss-20b", {"reasoning_effort": "low"}),
]
active = 0  # index of the model that worked last time

history = []      # past turns, so follow-up questions make sense
MAX_HISTORY = 20  # 10 things you said + 10 replies
MAX_STEPS = 5     # most tool rounds for one request

def system_prompt():
    now = datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    lines = [PERSONALITY, f"\nRight now it is {now}."]
    if profile.get("name"):
        lines.append(f"Call the user {profile['name']}.")
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
    return {"role": "system", "content": "\n".join(lines)}

def ask_model(messages):
    # Try the model that worked last, then the others. Returns the reply message or None.
    global active
    order = [active] + [i for i in range(len(MODELS)) if i != active]
    for i in order:
        name, settings = MODELS[i]
        try:
            resp = client.chat.completions.create(
                model=name, messages=messages, tools=TOOLS, **settings)
            active = i
            return resp.choices[0].message
        except Exception as e:
            print(f"Model {name} failed: {e}")
    return None

def remember(user_text, reply_text):
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply_text})
    del history[:-MAX_HISTORY]

def think(text):
    # Returns (reply to speak, action). action is None, "end" or "shutdown".
    messages = [system_prompt()] + history + [{"role": "user", "content": text}]
    action = None
    for _ in range(MAX_STEPS):
        msg = ask_model(messages)
        if msg is None:
            return "Sorry, I couldn't reach my brain. Check the internet.", None

        # No tools needed: this is the final answer
        if not msg.tool_calls:
            reply = (msg.content or "").strip() or "Sorry, I didn't catch that."
            remember(text, reply)
            return reply, action

        # The brain wants to use tools: run each one and give it the results
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in msg.tool_calls]})
        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            print(f"  [tool] {name} {args}")
            result = run_tool(name, args)
            print(f"  [result] {result}")
            if name == "end_conversation":
                action = "end"
            elif name == "shut_down":
                action = "shutdown"
            else:
                state.add_message("tool", result[:150])  # show what was done in the HUD
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "Sorry, that took too many steps.", action
