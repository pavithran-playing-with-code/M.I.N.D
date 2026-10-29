# Self test: checks that every part of M.I.N.D works, without opening apps, playing music
# or changing your settings (all actions are faked, saving is turned off).
# Run from the backend folder:   venv\Scripts\python.exe self_test.py
# Add "--brain" to also run the 20 brain tests. They use ~40 requests of today's free brain limit,
# so run them only after changing the prompt or tools (running them often made Groq rest all day).
import os
import re
import sys
import json
import numpy as np
import time
import asyncio
import tempfile
import functools
import subprocess
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
results = []

def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))

def section(title):
    print(f"\n=== {title} ===")

# ---------- Load everything, with saving switched off ----------
section("1. Code health")
import memory
memory.save_profile = lambda: None
import state, limits, info, alerts, hud, taskbar
import tools, pc, brain, telegram_bot, server
for module in (tools, telegram_bot, server):
    module.save_profile = lambda: None
tools.save_reminders = lambda: None
brain.HISTORY_FILE = os.path.join(tempfile.gettempdir(), "mind_self_test_history.json")
brain.history.clear()
check("all modules load", True)

tool_names = [t["function"]["name"] for t in tools.TOOLS]
check("every tool in TOOLS has a function", all(n in tools.FUNCTIONS for n in tool_names),
      str([n for n in tool_names if n not in tools.FUNCTIONS]))
check("every function is listed in TOOLS", all(n in tool_names for n in tools.FUNCTIONS),
      str([n for n in tools.FUNCTIONS if n not in tool_names]))
check("no tool is listed twice", len(tool_names) == len(set(tool_names)))
stray = [f for f in os.listdir(".") if f.endswith(".py") and chr(8) in open(f, encoding="utf-8").read()]
check("no broken regex characters in the code", not stray, str(stray))
# Every PowerShell/netsh call must hide its window (one flashed a black window at every start)
flashing = []
for name in [f for f in os.listdir(".") if f.endswith(".py") and f != "self_test.py"]:
    code = open(name, encoding="utf-8").read()
    for call in re.finditer(r"subprocess\.(run|Popen)\(\[\"(powershell|netsh|cmd)\"", code):
        whole = code[call.start():call.start() + 600].split("\n\n")[0]  # the call and its arguments
        if "CREATE_NO_WINDOW" not in whole:
            flashing.append(f"{name}:{code[:call.start()].count(chr(10)) + 1}")
check("no command windows flash (CREATE_NO_WINDOW)", not flashing, str(flashing))
bad = []
for t in tools.TOOLS:
    f = t["function"]
    props = f["parameters"]["properties"]
    if any(r not in props for r in f["parameters"]["required"]):
        bad.append(f["name"])
    import inspect
    params = inspect.signature(tools.FUNCTIONS[f["name"]]).parameters
    if any(p not in params for p in props) and not any(v.kind == v.VAR_KEYWORD for v in params.values()):
        bad.append(f["name"] + " (settings don't match the function)")
check("tool settings match their functions", not bad, str(bad))
check("quick replies only for real tools", all(k in tools.FUNCTIONS for k in tools.QUICK))
steps_ok = all(s["tool"] in tools.FUNCTIONS for steps in tools.DEFAULT_ROUTINES.values() for s in steps)
check("built-in routines use real tools", steps_ok)
request_size = len(json.dumps(tools.TOOLS)) + len(brain.system_prompt("hi")["content"])
# (most requests now send only some tools, so this is the worst case: all tools)
check("brain request stays small (< 20,000 characters)", request_size < 20000, f"{request_size} characters")
build = subprocess.run("npm run build", shell=True, cwd=os.path.dirname(HERE), capture_output=True, text=True)
check("HUD builds", build.returncode == 0, build.stderr[-200:])
lint = subprocess.run("npm run lint", shell=True, cwd=os.path.dirname(HERE), capture_output=True, text=True)
check("HUD code is clean (lint)", lint.returncode == 0, lint.stdout[-300:])

# ---------- Logic (no internet) ----------
section("2. Logic")
src = open("main.py", encoding="utf-8").read()
detector = {"re": re}
exec(src[src.index("CALLED = re.compile"):src.index("def command_from")], detector)
CALLED = detector["CALLED"]
ns = {}
exec(src[src.index("SLEEP_WORDS = "):src.index("def command_from")].split("# ---------- \"Mind\" must be said")[0], ns)
wants_sleep = ns["wants_sleep"]
for text, expect in [("Mind, play a song", "play a song"), ("Hey mind.", ""), ("remind me later", None),
                     ("mindset", None), ("Okay MIND, close the tab", "close the tab"), ("மைண்ட் பாட்டு போடு", "பாட்டு போடு"),
                     ("Hey mine, what's the weather", "what's the weather"), ("ஹே மைண்டு வானிலை", "வானிலை")]:
    m = CALLED.search(text)
    got = None if not m else text[m.end():].strip(" .,!?")
    check(f"'mind' detector: {text!r}", got == expect, f"got {got!r}")
GREETING = detector["GREETING"]
for text, expect in [("Hey man, play music", "play music"), ("ஹாய் மை பாட்டு போடு", "பாட்டு போடு"),
                     ("பதுவான் வக்குமிந்த அக்காண்ட்ட", None), ("open the door", None)]:
    m = GREETING.match(text)
    got = None if not m else text[m.end():].strip(" .,!?")
    check(f"'hey mind' heard, greeting check: {text!r}", got == expect, f"got {got!r}")
for text, expect in [("stop", True), ("Stop stop, don't speak to me for a while", True), ("நிறுத்து", True),
                     ("stop the music", False), ("stop the timer", False)]:
    check(f"sleep command: {text!r}", wants_sleep(text) == expect)
check("hint copy filter catches a repeated hint", __import__("ears").copied_hint("Pavithran talking to Mind"))
import ears, voice
check("hint copy filter lets real commands through", not ears.copied_hint("play a Tamil song on YouTube"))
check("'the past two songs' (said over music) = pause", ears.fix_text("mind the past two songs") == "mind pause the songs")
check("'past' in normal speech stays", ears.fix_text("what did I do in the past hour") == "what did I do in the past hour")
import speaker, numpy as np
real_print, real_embed, real_active = speaker.voiceprint, speaker.embed, speaker.active
speaker.voiceprint, speaker.active = np.array([1.0, 0.0]), lambda: True
speaker.embed = lambda sound: np.array([0.67, (1 - 0.67 ** 2) ** 0.5])  # your voice over a song scored 0.67
check("voice lock: 0.67 over music counts as you", speaker.check(b"0" * 64000, music=True)[0])
check("voice lock: 0.67 without music doesn't", not speaker.check(b"0" * 64000)[0])
speaker.voiceprint, speaker.embed, speaker.active = real_print, real_embed, real_active
import audio
audio.unduck()
check("music ducking: nothing turned down -> unduck does nothing", not audio.ducked and audio.duck_timer is None)
check("pause says Paused (no brain call)", tools.QUICK["media_control"]({"action": "play_pause"}, "Paused the music.") == "Paused.")
import typebox
check("type box: closed = M.I.N.D keeps listening", not typebox.typing() and not typebox.is_open())
import brain
check("two asks heard with 'a' instead of 'and'", brain.SEVERAL.search("stop the current playing song a play pesalame song"))
check("one ask stays one ask", not brain.SEVERAL.search("stop the current playing song"))
def box_side(reactor_on_right):
    p = floating.Painter(1.0, mirrored=reactor_on_right)
    saved = dict(floating.spot), dict(floating.current), floating.is_shown
    floating.current["painter"], floating.is_shown = p, lambda: True
    floating.spot.update(x=(1200 if reactor_on_right else 20), y=500)
    try:
        x = floating.type_box_spot()[0]
        reactor_x = floating.spot["x"] + (p.w - p.r if reactor_on_right else 0)
        return x < reactor_x if reactor_on_right else x > reactor_x
    finally:
        floating.spot.update(saved[0]); floating.current.clear(); floating.current.update(saved[1])
        floating.is_shown = saved[2]
import floating
check("text box: reactor on the right -> box on its left", box_side(True))
check("text box: reactor on the left -> box on its right", box_side(False))
import notices, watcher
check("notification: WhatsApp app message", notices.describe("WhatsApp", [["Jenny", "are you free tonight?"]])
      == "Sir, WhatsApp: Jenny says are you free tonight?")
check("notification: website in Chrome named by its site",
      notices.describe("Google Chrome", [["Jenny", "hi", "web.whatsapp.com"]]) == "Sir, Whatsapp: Jenny says hi")
check("notification: a burst = one line", notices.describe("WhatsApp", [["A", "1"], ["B", "2"], ["Jenny", "3"]])
      == "Sir, 3 new notifications from WhatsApp, the latest from Jenny.")
def fake_notes(notes, front=("explorer", "desktop")):
    real = notices.read_all, notices.front_app, watcher.chime
    notices.read_all, notices.front_app, watcher.chime = (lambda: notes), (lambda: front), (lambda: None)
    notices.GROUP_SECONDS, saved_alerts = 0, list(state.alerts)
    state.alerts.clear()
    try:
        notices.check()
        return list(state.alerts)
    finally:
        notices.read_all, notices.front_app, watcher.chime = real
        notices.GROUP_SECONDS = 4
        state.alerts.clear(); state.alerts.extend(saved_alerts)
check("notification is said", len(fake_notes([(9001, "WhatsApp", ["Jenny", "hi"])])) == 1)
check("notification not said when WhatsApp is in front",
      not fake_notes([(9002, "WhatsApp", ["Jenny", "hi"])], front=("whatsapp", "whatsapp")))
check("notification: Claude/ChatGPT sites skipped (prompt watcher says those)",
      not fake_notes([(9003, "Google Chrome", ["Claude", "Claude responded", "claude.ai"])]))
check("notification: Snipping Tool etc. stay quiet", not fake_notes([(9004, "Snipping Tool", ["Screenshot copied"])]))
check("prompt reply: page labels removed", watcher.first_words(
      "Claude responded: Dfresh products v2 Code · HTML Shared a file, Here it is") == "Here it is")
check("Tamil sentences use a Tamil voice", voice.voice_for("வணக்கம்").startswith("ta-"))
check("English sentences don't use a Tamil voice", not voice.voice_for("Hello there").startswith("ta-"))
check("echo check: own sentence = echo", voice.is_echo("the weather in chennai", "The weather in Chennai is warm."))
check("echo check: new words = you", not voice.is_echo("open youtube please", "The weather in Chennai is warm."))
check("broken reply guard", brain.looks_broken("… ... … ... …") and not brain.looks_broken("Done!"))
check("broken reply guard: invisible characters", brain.looks_broken("Those " + chr(0x200b) * 6))
saved_history = list(brain.history)
brain.history[:] = []
check("showing: 'what is biryani' / 'suggest a keyboard' put pictures on the HUD",
      brain.wants_showing("what is biryani") and brain.wants_showing("suggest a good keyboard under 1500"))
check("showing: battery / music requests don't", not brain.wants_showing("how is my battery")
      and not brain.wants_showing("play lofi"))
brain.history[:] = [{"role": "user", "content": "suggest a keyboard under 1500"},
                    {"role": "assistant", "content": "Mechanical or membrane?"}]
check("showing: the answer to Mind's question counts", brain.wants_showing("mechanical and wired"))
brain.history[:] = []
check("teaching: 'help me learn Spanish' turns on tutor mode", brain.wants_teaching("help me learn Spanish")
      and not brain.wants_teaching("play lofi"))
import showcase
check("prompt watcher: a long test isn't 'needs your OK', a plain step is after 75 s",
      watcher.step_time([{"type": "tool_use", "name": "Bash", "input": {"command": "x", "timeout": 300000}}]) > 300
      and watcher.step_time([{"type": "tool_use", "name": "Bash", "input": {"command": "x"}}]) == 75)
import writing
real_write = brain.write
brain.write = lambda rules, ask, **k: 'Sure: {"corrected": "Today I fixed it.", "changes": [{"from": "Today fixed", "to": "Today I fixed", "why": "missing I"}]}'
check("grammar: the brain's fix and reasons are read", writing.corrected("Today fixed it") ==
      ("Today I fixed it.", [{"from": "Today fixed", "to": "Today I fixed", "why": "missing I"}]))
brain.write = real_write
check("'mind if it's my grammar' heard right", ears.fix_text("mind if it's my grammar") == "mind fix my grammar")
state.last_user_text = "mindfix, my sentence, grammar"
check("grammar: the spoken ask isn't the text to fix (reads the box instead)",
      writing.just_the_ask("mindfix, my sentence, grammar") and not writing.just_the_ask("Very good evening sir, the work is going well"))
check("commas alone aren't several asks (Whisper adds them)", not brain.SEVERAL.search("mindfix, my sentence, grammar"))
from concurrent.futures import Future
def finished(text):
    job = Future()
    job.set_result(text)
    return job
check("listening: same words again = noise, stop recording", ears.words_of(finished("Mind, fix my grammar.")) ==
      ears.words_of(finished("mind fix my grammar")))
import speaker as voice_lock_code
loud = (np.sin(np.arange(16000) / 3) * 8000).astype(np.int16).tobytes()
check("voice lock: only the talking part is compared (silence dropped)",
      len(voice_lock_code.voiced(bytes(32000 * 3) + loud + bytes(32000 * 3))) < 32000 * 2)
state.last_user_text = "yes"
check("grammar: 'yes' after a fix replaces (no new check)", not writing.NEW_CHECK.search(state.last_user_text)
      and writing.NEW_CHECK.search("fix my grammar and replace it"))
state.offer = {"replace": True}
check("grammar: asks 'replace it?' only when it can", "replace" in tools.grammar_line("Fixed 2 thing(s)").lower())
state.offer = {"replace": False}
check("grammar: no 'replace it?' for text you said", "replace" not in tools.grammar_line("Fixed 2 thing(s)").lower())
state.offer = None
check("'open what's up' / 'open watch the video' = open WhatsApp", ears.fix_text("mind open, what's up") == "mind open WhatsApp"
      and ears.fix_text("mind open, watch the video") == "mind open WhatsApp")
cmd_ns = {"re": re}
exec(src[src.index("COMMAND_START = re.compile"):src.index("MIND_LIKE = {")], cmd_ns)
check("wake heard but Whisper dropped 'mind': a clear command still counts",
      cmd_ns["COMMAND_START"].match("open WhatsApp") and not cmd_ns["COMMAND_START"].match("I told him to open it"))
# From the hearing test (2026-10-29): how Whisper rewrote "Mind, ..." in the owner's own recordings
check("Whisper's rewrites of 'Mind,' still count ('I'm going to lock my laptop', 'Now I need to take...')",
      cmd_ns["COMMAND_START"].match("I'm going to lock my laptop")
      and cmd_ns["COMMAND_START"].match("Now I need to take a screenshot and send it to my phone"))
exec(src[src.index("MIND_GLUED = re.compile"):src.index("def squash")], cmd_ns)
check("'Mindo', 'Minda', 'Mindy', 'Minder', 'Minding' = Mind (but not 'mindful')",
      all(cmd_ns["MIND_GLUED"].match(w) for w in ["mindo", "minda", "mindy", "minder", "minding"])
      and not cmd_ns["MIND_GLUED"].match("mindful"))
check("hint copy filter keeps real commands with hint words ('Mind pause the song' was thrown away)",
      not any(ears.copied_hint(t) for t in ["Mind pause the song", "Mind play Rathinamo song", "mind open the HUD"]))
check("hint copy filter catches the word list or 2 example commands copied",
      ears.copied_hint("Chennai, HUD, WhatsApp") and ears.copied_hint("Mind, open Chrome. Mind, check my battery."))
check(f"Whisper hint is short (<= {ears.HINT_LENGTH} chars; it only reads ~224 tokens)",
      len(ears.make_hint()) <= ears.HINT_LENGTH, f"{len(ears.make_hint())} chars")
check("grammar: replaces your text only if you said replace", not writing.REPLACE_WORDS.search("fix my grammar")
      and writing.REPLACE_WORDS.search("fix my grammar and replace it"))
check("hologram: 'ask question' isn't a topic (asks first)", showcase.show_on_hud("ask question").startswith("Not shown"))
check("animation: HTML taken out of the brain's answer",
      showcase.html_from("Here you go:\n```html\n<!DOCTYPE html><html><body><canvas></canvas></body></html>\n```")
      .startswith("<!DOCTYPE html>") and showcase.html_from("Sorry, I can't.") == "")
chat_ns = {"re": re}
exec(src[src.index("CHAT = re.compile"):src.index("def think_or_cancel")], chat_ns)  # not "import main": it starts M.I.N.D
check("chit-chat gets 'Hmm', not 'Let me check'", chat_ns["CHAT"].search("do you like thor or hulk")
      and not chat_ns["CHAT"].search("open youtube"))
from fastapi.testclient import TestClient
web = TestClient(server.app)
check("animations: only real file names are served", web.get("/api/creation/..%2Fmain.py").status_code == 404
      and web.get("/api/creation/nope.html").status_code == 404)
real_hud_open = tools.hud.open_hud
tools.hud.open_hud = lambda: None
hidden_before = list(memory.profile.get("hud_hidden", []))
tools.open_hud("chat", False)
hid = "chat" in state.hidden_parts()
tools.open_hud("all", True)
check("HUD panels: hide the chat, then show everything", hid and not state.hidden_parts())
memory.profile["hud_hidden"] = hidden_before
tools.hud.open_hud = real_hud_open
brain.history[:] = saved_history
brain.history[:] = saved_history
check("pretend catcher", brain.CLAIMS_ACTION.search("Sure, here's Rathinamo.") and not brain.CLAIMS_ACTION.search("It's 3 PM."))
check("typing guard needs type/write words", brain.ASKED_TO_TYPE.search("write my name") and not brain.ASKED_TO_TYPE.search("say hello"))
# "Close YouTube" must close the tab, never the whole browser window (it closed every Chrome tab once)
real_windows, real_tab, real_post = pc.open_windows, pc.tab_action, pc.win32gui.PostMessage
posted = []
pc.open_windows = lambda: [(1, 99, "chrome", "Rathinamo - YouTube - Google Chrome")]
pc.tab_action = lambda name, action="switch": f"Close: {name}"
pc.win32gui.PostMessage = lambda *a: posted.append(a)
result = pc.close_app("YouTube")
pc.open_windows, pc.tab_action, pc.win32gui.PostMessage = real_windows, real_tab, real_post
check("'close YouTube' closes the tab, not Chrome", result.startswith("Close:") and not posted, result)
check("keyboard key names", pc.key_code("ctrl") == 0x11 and pc.key_code("f5") == 0x74 and pc.key_code("banana") is None)
check("speed labels", info.describe(25, 50)[0] == "Fast" and info.describe(2, 50)[0] == "Slow")
check("one-word wake words are refused", tools.update_profile("wake_word", "mind").startswith("Not changed"))
check("contacts get the country code", tools.save_contact("Test", "98765 43210") and memory.profile["contacts"]["Test"] == "919876543210")
memory.profile["contacts"].pop("Test")
saved = tools.reminders[:]
tools.set_reminder(600, "self test reminder")
check("set and cancel a reminder", "Cancelled" in tools.cancel_reminder("self test"))
tools.reminders[:] = saved
check("save a routine", tools.save_routine("self test mode", [{"tool": "change_volume", "args": {"action": "up"}}]).startswith("Saved"))
check("routines refuse unsafe steps", tools.save_routine("bad", [{"tool": "shut_down"}]).startswith("Can't"))
check("delete a routine", tools.delete_routine("self test mode").startswith("Deleted"))
memory.profile.get("routines", {}).pop("self test mode", None)
check("folder finder: 'mind' = the M.I.N.D project", pc.find_folder("mind")[:1] and pc.find_folder("mind")[0].endswith("M.I.N.D"))
tools.installed or tools.load_apps()
check("app finder: Notepad is installed", tools.find_app("notepad") is not None)
groq_msgs = brain.for_groq([{"role": "assistant", "tool_calls": [{"id": "1", "type": "function", "function": {}, "extra_content": {}}]}])
check("Groq gets plain tool calls", "extra_content" not in groq_msgs[0]["tool_calls"][0])
gem_msgs = brain.for_gemini([{"role": "assistant", "tool_calls": [{"id": "1", "type": "function", "function": {}}]}])
check("Gemini gets a thought signature", "extra_content" in gem_msgs[0]["tool_calls"][0])
limits.note_busy("self-test-model", 600)
check("free-limit meter marks resting brains", limits.resting("self-test-model"))
limits.usage.pop("self-test-model", None)

# Telegram security (fake phone)
sent = []
telegram_bot.TOKEN = telegram_bot.TOKEN or "fake"
real_send, real_owner = telegram_bot.send, memory.profile.get("telegram_owner")
telegram_bot.send = lambda chat, text: sent.append((chat, text))
memory.profile["telegram_owner"] = 111
telegram_bot.handle({"chat": {"id": 999}, "date": int(time.time()), "text": "lock my pc"})
check("Telegram ignores strangers", not sent)
telegram_bot.handle({"chat": {"id": 111}, "date": int(time.time()) - 3600, "text": "lock my pc"})
check("Telegram doesn't do old messages", sent and "was off" in sent[-1][1])
memory.profile.pop("telegram_owner")
telegram_bot.pair_code = "123456"
sent.clear()
telegram_bot.handle({"chat": {"id": 222}, "date": int(time.time()), "text": "000000"})
check("Telegram: wrong code doesn't connect", "telegram_owner" not in memory.profile)
telegram_bot.handle({"chat": {"id": 222}, "date": int(time.time()), "text": "123456"})
check("Telegram: right code connects", memory.profile.get("telegram_owner") == 222)
telegram_bot.send = real_send
if real_owner:
    memory.profile["telegram_owner"] = real_owner
else:
    memory.profile.pop("telegram_owner", None)

# Alerts (fake battery)
import types
alerts.quiet_hours = lambda: False
state.alerts.clear()
alerts.said.clear()
real_battery = alerts.psutil.sensors_battery
alerts.psutil.sensors_battery = lambda: types.SimpleNamespace(percent=15, power_plugged=False)
real_notify = telegram_bot.notify
telegram_bot.notify = lambda text: None
alerts.check_battery()
check("low battery alert", any("15 percent" in a for a in state.alerts))

# Human touches: a break after 2 hours of use (spoken, not sent to the phone)
state.alerts.clear()
real_idle, real_quiet = alerts.idle_seconds, alerts.quiet_hours
alerts.idle_seconds, alerts.quiet_hours = (lambda: 5), (lambda: False)
alerts.said.pop("break", None)
alerts.use.update(since=time.time() - 2 * 3600 - 5, last=time.time())
alerts.check_human()
check("break reminder after 2 hours", any("2 hours" in a for a in state.alerts), str(list(state.alerts)))
alerts.idle_seconds, alerts.quiet_hours = real_idle, real_quiet

# Prompt watcher: a fake Claude Code session (in a temp folder) that runs, then finishes
import watcher, tempfile, json as json_
real_sessions, real_web = watcher.SESSIONS, watcher.web_chats
watcher.SESSIONS = os.path.join(tempfile.gettempdir(), "mind_selftest_sessions")
os.makedirs(os.path.join(watcher.SESSIONS, "proj"), exist_ok=True)
fake = os.path.join(watcher.SESSIONS, "proj", "s.jsonl")
watcher.web_chats = lambda with_reply=False: []
def entry(**e):
    with open(fake, "a", encoding="utf-8") as f:
        f.write(json_.dumps(e) + "\n")
open(fake, "w").close()
entry(type="ai-title", aiTitle="Fix login")
entry(type="last-prompt", lastPrompt="fix the login page")
entry(type="user", cwd=r"C:\code\dfresh\backend", timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 60)),
      message={"content": [{"type": "text", "text": "fix the login page"}]})
entry(type="assistant", cwd=r"C:\code\dfresh\backend", message={"stop_reason": "tool_use", "content": [{"type": "tool_use"}]})
watcher.seen.clear(); watcher.cache.clear()
watcher.check(first=True)
running = watcher.claude_code_sessions()
check("prompt watcher: running session seen", running and running[0]["status"] == "running"
      and running[0]["project"] == "dfresh", str(running[:1]))
status = watcher.prompt_status("dfresh")
check("prompt status says STILL RUNNING first", status.startswith("STILL RUNNING"), status)
check("running prompt gets a short 'Okay Sir.'", tools.quick_reply("prompt_status", {}, status) == "Okay Sir.")
time.sleep(0.05)
entry(type="assistant", cwd=r"C:\code\dfresh\backend",
      message={"stop_reason": "end_turn", "content": [{"type": "text", "text": "**Fixed** the login page, it works now."}]})
state.alerts.clear()
watcher.chime = lambda: None
watcher.looking_at = lambda job: True  # even while you look at it: you asked about it
watcher.check()
check("prompt watcher: says when it's done (asked, even in front)", any("Claude Code in dfresh is done" in a and "Fixed the login" in a for a in state.alerts),
      str(list(state.alerts)))
check("prompt status tool reports it", "done" in watcher.prompt_status("dfresh"), watcher.prompt_status("dfresh"))
check("chat Stop button is recognised", watcher.STOP_BUTTON.match("Stop response") and not watcher.STOP_BUTTON.match("Stop sharing"))
watcher.SESSIONS, watcher.web_chats = real_sessions, real_web
# Chrome extension: a background ChatGPT tab reports running, then done
import browser
watcher.looking_at = lambda job: False
browser.report({"profile": "selftest", "tabs": [{"id": 7, "title": "Trip plan - ChatGPT", "url": "https://chatgpt.com/c/1"}]})
browser.report({"profile": "selftest", "chat": {"tab": 7, "site": "ChatGPT", "title": "Trip plan", "running": True}})
watcher.seen.clear(); watcher.asked.clear()
watcher.check(first=True)
check("extension chat seen as running", "STILL RUNNING" in watcher.prompt_status("chatgpt"), watcher.prompt_status("chatgpt"))
browser.report({"profile": "selftest", "chat": {"tab": 7, "site": "ChatGPT", "title": "Trip plan", "running": False,
                                                 "reply": "Day one: fly to Goa in the morning and relax at the beach."}})
state.alerts.clear()
watcher.check()
check("extension chat done is announced", any("ChatGPT is done" in a and "Day one" in a for a in state.alerts), str(list(state.alerts)))
browser.report({"profile": "selftest", "chat": {"tab": 7, "site": "Claude", "title": "Keyboard", "running": True}})
watcher.check()
browser.report({"profile": "selftest", "chat": {"tab": 7, "site": "Claude", "title": "Keyboard", "running": False,
                                                 "reply": "Let me confirm a couple of things:", "question": "What's your main usage?"}})
watcher.seen[[k for k in watcher.seen if k.endswith(":7")][0]] = ("running", time.time() - 5)
state.alerts.clear()
watcher.check()
check("chat asking a question is announced as a question",
      any("asking you something: What's your main usage?" in a for a in state.alerts), str(list(state.alerts)))
browser.report({"profile": "selftest", "tabs": []})
check("closed tab's chat is forgotten", not [c for c in browser.chats() if c["profile"] == "selftest"])
check("extension with old code is told to reload", browser.report({"profile": "selftest", "code": "old"}).get("reload"))
browser.last_reload.clear()
check("extension with current code is left alone", not browser.report({"profile": "selftest", "code": browser.code_hash()}))
browser.reload_all()
check("'reload the extension' reaches it on its next report", browser.report({"profile": "selftest", "code": browser.code_hash()}).get("reload"))
browser.profiles.pop("selftest", None)
browser.last_reload.clear()
check("extension status reads Chrome's files", browser.status().startswith("M.I.N.D extension"), browser.status())
state.alerts.clear()

# Long-term memory: a turn saved today can be found again (in a temporary diary file)
import diary, tempfile
real_file = diary.FILE
diary.FILE = os.path.join(tempfile.gettempdir(), "mind_selftest_diary.jsonl")
open(diary.FILE, "w").close()
diary.write("play Rathinamo", ["Playing on YouTube: Rathinamo"], "Here's Rathinamo, enjoy!")
found = diary.recall("Rathinamo", "today")
check("diary remembers today's turns", "Rathinamo" in found and "Today" in found, found[:80])
check("diary keeps days apart", "No conversations" in diary.recall("", "yesterday"))
os.remove(diary.FILE)
diary.FILE = real_file

# Chrome accounts: an email said slightly wrong still finds its profile (one letter missing)
with_email = [p for p in pc.chrome_profiles() if "@" in p[2]]
if with_email:
    folder, name, email = with_email[0]
    user, domain = email.split("@")
    found = pc.find_chrome_profile(user[:-1] + "@" + domain)
    check("Chrome account found from a slightly-off email", isinstance(found, tuple) and found[0] == folder
          or (isinstance(found, str) and "Which Chrome?" in found), str(found)[:80])  # (two profiles may share an email)
    check("unknown Chrome account isn't guessed", isinstance(pc.find_chrome_profile("zzqqxxw@nowhere.com"), str))
# Several possible profiles: a numbered question, "2" picks one (2026-10-29: it said "All set." and opened nothing)
real_profiles, real_choices = pc.chrome_profiles, dict(pc.last_choices)
profile = memory.profile
real_picks = profile.pop("account_choices", None)
pc.chrome_profiles = lambda: [("P1", "Work", "work.team1@x.com"), ("P2", "Work", "work.team2@x.com")]
asked = pc.find_chrome_profile("work team")
check("several Chrome profiles match: asks 'Which Chrome? 1. ... 2. ...'", asked.startswith("Which Chrome? 1."), asked[:60])
check("'2' picks the second profile from that list", pc.find_chrome_profile("2") == ("P2", "Work"),
      str(pc.last_choices))
check("...and the same words open it straight away next time", pc.find_chrome_profile("work team") == ("P2", "Work"))
profile.pop("account_choices", None)
if real_picks is not None:
    profile["account_choices"] = real_picks
pc.chrome_profiles, pc.last_choices = real_profiles, real_choices
check("the numbered question is said as is (never a fake 'All set.')",
      tools.quick_reply("open_url", {}, asked) == asked and tools.quick_reply("open_url", {}, "No Chrome profile like x.") is None)
check("'new tab' / 'https://about:blank' = a blank tab", all(tools.BLANK_TAB.match(u) for u in ["new tab", "https://about:blank"]))
check("'open YouTube instead of Gmail' = two asks", __import__("brain").SEVERAL.search("open youtube instead of gmail"))
real_said, real_at = state.last_user_text, pc.last_choices["at"]
pc.last_choices["at"] = 0
state.last_user_text = "Mind to open a new tab"
check("an account they never said is ignored (the backup brain put 'pavithran' in for a new tab)",
      tools.said_account("pavithran") == "")
state.last_user_text = "play rathinamo in my tigergojimayready account"
check("an account they said (even misheard) is kept", tools.said_account("tigerboogipinky@gmail.com"))
state.last_user_text, pc.last_choices["at"] = real_said, real_at
check("'the last one' is a pick from the list", bool(pc.PICKED.match("the last one")))

# What you're doing: the window in front is noted, and found again by a word
real_activity = list(pc.activity)
pc.activity.clear()
pc.activity.extend([(time.time() - 300, "chrome", "Rathinamo - YouTube - Google Chrome"),
                    (time.time() - 120, "Code", "main.py - M.I.N.D - Visual Studio Code")])
report = pc.activity_report("youtube")
check("activity: finds the YouTube tab from 5 minutes ago", "Chrome: Rathinamo - YouTube" in report, report[:80])
check("activity: knows what's in front now", pc.in_front().startswith("VS Code: main.py"), pc.in_front())
pc.activity.clear()
pc.activity.extend(real_activity)

# Tool routing: a request gets only its group of tools; unclear ones ("yes do it") get all of them
names = lambda text: {t["function"]["name"] for t in tools.tools_for(text)}
check("routing: 'play Rathinamo' gets music tools only", "play_youtube" in names("play Rathinamo")
      and len(names("play Rathinamo")) < 8, str(sorted(names("play Rathinamo"))))
check("routing: unclear follow-ups get every tool", len(tools.tools_for("yes do it")) == len(tools.TOOLS))
check("routing: every tool is in some group", {t["function"]["name"] for t in tools.TOOLS}
      <= set(tools.ALWAYS) | {n for _, group in tools.TOOL_GROUPS for n in group})

# Noise like "ruff ruff ruff ruff" isn't a request; real ones are
noise_ns = {"re": re}
exec(src[src.index("def meaningless"):src.index("def respond")], noise_ns)
check("noise ignored ('ruff ruff ruff ruff')", noise_ns["meaningless"]("ruff ruff ruff ruff")
      and not noise_ns["meaningless"]("play some lofi") and not noise_ns["meaningless"]("yes yes"))
# Battery full: said when it BECOMES full, not at every start
state.alerts.clear()
full = types.SimpleNamespace(percent=95, power_plugged=True, secsleft=0)  # already past 90 at start
real_battery, real_notify = alerts.psutil.sensors_battery, telegram_bot.notify
alerts.psutil.sensors_battery, telegram_bot.notify = (lambda: full), (lambda text: None)
alerts.said.pop("battery_full", None)
alerts.last_level = None
alerts.check_battery()
quiet_at_start = not state.alerts
full.percent = 85
alerts.check_battery()
full.percent = 90
alerts.check_battery()
check("unplug reminder when it reaches 90 %, not at start", quiet_at_start and any("unplug" in a for a in state.alerts))
alerts.psutil.sensors_battery, telegram_bot.notify = real_battery, real_notify
state.alerts.clear()
# New reminders: low disk, drink water, weak Wi-Fi (with fake readings, nothing sent to the phone)
import info
real_disk, real_idle, real_wifi, real_quiet = alerts.psutil.disk_usage, alerts.idle_seconds, info.wifi, alerts.quiet_hours
alerts.psutil.disk_usage = lambda path: types.SimpleNamespace(free=6 * 2**30)
alerts.idle_seconds, alerts.quiet_hours = (lambda: 10), (lambda: False)
info.wifi = lambda: {"name": "Test", "signal": 20}
for key in ("disk", "water", "wifi_weak"):
    alerts.said.pop(key, None)
state.alerts.clear()
alerts.check_disk()
alerts.water["minutes"] = alerts.WATER_EVERY_MINUTES
alerts.check_water() if 9 <= time.localtime().tm_hour < 23 else state.alerts.append("water (night: skipped)")
alerts.wifi_weak["since"] = time.time() - 301
alerts.check_wifi()
said_now = " | ".join(state.alerts)
check("low disk, water and weak Wi-Fi reminders", "GB left" in said_now and "water" in said_now.lower()
      and "Wi-Fi signal is weak" in said_now, said_now[:90])
alerts.psutil.disk_usage, alerts.idle_seconds, info.wifi, alerts.quiet_hours = real_disk, real_idle, real_wifi, real_quiet
alerts.water["minutes"] = 0
state.alerts.clear()

# WhatsApp calls only when the user said "call"
state.last_user_text = "open my chat with jenny"
check("no call unless 'call' was said", tools.whatsapp_call("Jenny").startswith("Not called"))

# Clicking on screen: risky buttons need the user's own words; routing finds the screen tools
check("risky buttons are spotted", pc.RISKY.search("Sign out") and pc.RISKY.search("Delete chat")
      and not pc.RISKY.search("Skip ad"))
check("routing: 'play the second video' gets the click tools", {"screen_items", "click"} <= names("play the second video"))

# Turn-taking: unfinished sentences make M.I.N.D wait for the rest
check("unfinished sentence detector", ears.unfinished("Open dai and") and ears.unfinished("remind me to,")
      and ears.unfinished("அப்புறம்") and not ears.unfinished("Open the dai project."))
alerts.psutil.sensors_battery = real_battery
telegram_bot.notify = real_notify
state.alerts.clear()

# Floating reactor draws every state (English and Tamil chat, both sides)
import floating
chat = [{"id": 1, "who": "you", "text": "open dai"}, {"id": 2, "who": "mind", "text": "சரி சார், opening dai"}]
sizes = set()
for look in ("waiting", "listening", "thinking", "speaking"):
    for mirrored in (False, True):
        frame, _ = floating.Painter(1.25, mirrored).frame({"status": look, "level": 0.4, "messages": chat})
        sizes.add(frame.size)
check("floating reactor draws every state", len(sizes) == 1 and frame.getbbox() is not None, str(sizes))

# M.I.N.D Live (live_brain.py): the talking brain gets M.I.N.D's tools in Gemini's format
import live_brain
live_tools = [f.name for f in live_brain.declarations()[0].function_declarations]
check("Live brain gets the tools (and end_talk), not the old-ears-only ones",
      "end_talk" in live_tools and "open_url" in live_tools and not set(live_tools) & live_brain.NOT_LIVE,
      f"{len(live_tools)} tools")
check("Live instructions say: never claim what a tool didn't do, never guess weather",
      "tool result says it worked" in live_brain.instructions() and "never guess" in live_brain.instructions())
check("the Live page is a M.I.N.D window (tools never act on it)", "M.I.N.D Live" in pc.MIND_WINDOWS)
# WhatsApp: only open a chat the eyes saw is the right person (it said "Chat's open" for nobody)
check("WhatsApp: right person only ('Shiva Kevalavadi IT' is not 'Siva Chithappa')",
      pc.same_person("siva chithappa", "Siva Chithappa") and not pc.same_person("Shiva Kevalavadi IT", "Siva Chithappa"))
check("WhatsApp: tries the first name and its other spelling", pc.name_variants("Shiva Kevalavadi IT")[:2] == ["Shiva", "siva"])
real_look, real_type, real_tap, real_front = pc.look_at_window, pc.type_text, pc.tap, pc.bring_to_front
real_keys, real_window = pc.tap_keys, pc.whatsapp_window
pressed = []
pc.look_at_window = lambda hwnd, q: "NONE"  # WhatsApp shows "No chats, contacts or messages found"
pc.type_text = lambda *a, **k: None
pc.tap_keys = lambda *a: None
pc.tap = lambda key: pressed.append(key)
pc.bring_to_front = lambda hwnd: True
pc.whatsapp_window = lambda: 1
pc.time.sleep, real_sleep = (lambda s: None), pc.time.sleep
result = pc.whatsapp_chat("Shiva Kevalavadi IT")
pc.time.sleep = real_sleep
check("WhatsApp: nothing found -> nothing opened, and it says so (never 'Chat's open')",
      "Nothing was opened" in result and 0x0D not in pressed and tools.quick_reply("whatsapp_chat", {}, result) is None, result[:80])
pc.look_at_window, pc.type_text, pc.tap, pc.bring_to_front = real_look, real_type, real_tap, real_front
pc.tap_keys, pc.whatsapp_window = real_keys, real_window

# ---------- Internet services ----------
section("3. Internet services")
def safe(name, job, test):
    try:
        out = job()
        check(name, test(out), str(out)[:80])
    except Exception as e:
        check(name, False, str(e)[:100])
safe("weather (Open-Meteo)", lambda: tools.get_weather("Chennai"), lambda r: "°C" in r)
safe("news (Google News)", lambda: tools.get_news("ISRO", 2), lambda r: r.startswith("Headlines"))
def hologram(**ask):
    # Pictures on the HUD; the HUD window isn't opened during the test, and what was showing is put back
    import showcase
    before = state.showcase
    import hud
    real_hud, hud.open_hud = hud.open_hud, lambda: None
    try:
        said = showcase.show_on_hud(**ask)
        return said, state.showcase
    finally:
        hud.open_hud, state.showcase = real_hud, before
safe("hologram: pictures + Wikipedia facts", lambda: hologram(topic="biryani"),
     lambda r: r[0].startswith("Showing") and len(r[1]["cards"]) >= 4 and r[1]["info"].get("text"))
safe("hologram: one item ('Parotta') = many pictures of it", lambda: hologram(items=[{"name": "Parotta"}]),
     lambda r: len(r[1]["cards"]) >= 4 and r[1]["title"] == "Parotta")
def shop_test():
    state.last_user_text = "suggest waterproof socks under 1500"
    said, shown = hologram(topic="waterproof socks", items=[{"name": "Dexshell socks"}, {"name": "Decathlon socks"}])
    state.last_user_text = "what is parotta"
    _, food = hologram(topic="parotta", items=[{"name": "Kerala parotta"}, {"name": "Kothu parotta"}])
    return shown, food
safe("hologram: shop buttons only when shopping", shop_test,
     lambda r: all(c.get("shops") for c in r[0]["cards"]) and not any(c.get("shops") for c in r[1]["cards"]))
safe("hologram: product picks get one picture each", lambda: hologram(items=[{"name": "Logitech K120", "note": "wired"},
                                                                            {"name": "Redragon K552"}]),
     lambda r: [c["name"] for c in r[1]["cards"]] == ["Logitech K120", "Redragon K552"] and all(c["url"] for c in r[1]["cards"]))
opened = []
real_open, real_remember, real_account = tools.webbrowser.open, tools.remember_song, tools.pc.open_in_browser
tools.webbrowser.open, tools.remember_song = opened.append, lambda q: None
tools.pc.open_in_browser = lambda url, account="": opened.append(url)  # never opens a real window
real_quietly = tools.pc.open_quietly
tools.pc.open_quietly = lambda url, folder="": opened.append(url) or True
safe("YouTube lookup finds a video", lambda: tools.play_youtube("Rathinamo Saurav Srisan"),
     lambda r: r.startswith("Playing") and opened and "watch?v=" in opened[0])
def different_song():
    # "play a different Tamil melody" played the same top song again
    opened.clear()
    state.last_user_text = "play a tamil melody song"
    tools.play_youtube("Tamil melody song")
    state.last_user_text = "play any different tamil melody song"
    tools.play_youtube("Tamil melody song")
    return opened
safe("'a different song' skips the one just played", different_song,
     lambda r: len(r) == 2 and r[0] != r[1])
tools.webbrowser.open, tools.remember_song, tools.pc.open_in_browser = real_open, real_remember, real_account
tools.pc.open_quietly = real_quietly
import edge_tts, av
def recording(text, voice_id):
    path = os.path.join(tempfile.gettempdir(), "mind_self_test.mp3")
    asyncio.run(edge_tts.Communicate(text, voice_id).save(path))
    resample = av.AudioResampler(format="s16", layout="mono", rate=16000)
    return b"".join(r.to_ndarray().tobytes() for f in av.open(path).decode(audio=0) for r in resample.resample(f))
safe("hearing English", lambda: ears.to_text(recording("Mind, what is the weather today?", "en-IN-PrabhatNeural"), show=False),
     lambda r: "weather" in r.lower())
# (English mode sends English only, so Tamil hearing is checked in Tamil mode)
old_language = memory.profile.get("language")
memory.profile["language"] = "tamil"
safe("hearing Tamil (Tamil mode)", lambda: ears.to_text(recording("நாளைக்கு மழை வருமா?", "ta-IN-ValluvarNeural"), show=False),
     lambda r: "மழை" in r)
if old_language is None:
    memory.profile.pop("language", None)
else:
    memory.profile["language"] = old_language
safe("voice: Tamil (Edge)", lambda: voice.make_audio("வணக்கம், நான் ரெடி."), lambda r: os.path.exists(r[0]))
# Only your voice: learn a test "owner" (in a temporary file), then the same voice passes, another doesn't
import speaker
real_print, real_file = speaker.voiceprint, speaker.VOICEPRINT
speaker.VOICEPRINT = os.path.join(tempfile.gettempdir(), "mind_selftest_voiceprint.npy")
try:
    owner = "en-IN-PrabhatNeural"
    speaker.learn([recording(t, owner) for t in ("Mind, open the dai project for me.", "Hey Mind, play some lofi music.",
                                                  "What's the weather in Chennai today?")])
    same = speaker.check(recording("Mind, remind me to call Genyx at five.", owner))
    other = speaker.check(recording("Mind, remind me to call Genyx at five.", "en-US-AndrewNeural"))
    check("voice lock: owner's voice accepted", same[0], f"match {same[1]:.2f}")
    check("voice lock: another voice ignored", not other[0], f"match {other[1]:.2f}")
except Exception as e:
    check("voice lock works", False, str(e)[:100])
finally:
    speaker.voiceprint, speaker.VOICEPRINT = real_print, real_file
safe("voice: main English voice", lambda: voice.make_audio("Self test complete."), lambda r: os.path.exists(r[0]))
safe("Windows location", lambda: (info.windows_location(), state.location)[1], lambda r: r and r.get("lat"))

# ---------- Brain understanding ----------
if "--brain" in sys.argv:
    section("4. Brain understanding (actions are faked)")
    calls = []
    def fake(name, original):
        @functools.wraps(original)
        def run(*args, **kwargs):
            calls.append(name)
            return f"(fake) {name} done"
        return run
    real_functions = dict(tools.FUNCTIONS)
    for name, original in real_functions.items():
        if name not in ("end_conversation", "shut_down"):
            tools.FUNCTIONS[name] = fake(name, original)
    tests = [
        ("play rathinamo", {"play_youtube"}),
        ("turn the volume down a bit", {"change_volume"}),
        ("what's the weather tomorrow", {"get_weather"}),
        ("remind me in 10 minutes to drink water", {"set_reminder"}),
        ("open notepad", {"open_app"}),
        ("close the youtube tab", {"tab_action"}),
        ("open the mind project", {"open_folder"}),
        ("how's my battery", {"system_info"}),
        ("work mode", {"run_routine"}),
        ("send hello to sathana on whatsapp", {"whatsapp_chat"}),
        ("pause the music", {"media_control"}),
        ("lock my pc", {"lock_pc"}),
        ("switch to vs code", {"window_action"}),
        ("close whatsapp", {"close_app", "window_action"}),
        ("what's on my screen", {"look_at_screen", "read_screen"}),
        ("open the hub", {"open_hud"}),
        ("நாளைக்கு மழை வருமா", {"get_weather"}),
        ("volume கொஞ்சம் குறை", {"change_volume"}),
        ("what is the capital of japan", set()),
        ("say hello in tamil", set()),
        ("good morning", {"daily_briefing"}),
        ("what song did you play yesterday", {"recall"}),
        ("read my notes", {"recall"}),
        ("is my claude code prompt done", {"prompt_status"}),
        ("did chatgpt finish answering", {"prompt_status"}),
        ("check if my extension is working", {"mind_extension"}),
        ("open dai and play some lofi", {"open_folder", "play_youtube"}),
        ("check my internet speed", {"system_info"}),
        ("open youtube using my tigerboogipink mail", {"open_url", "play_youtube"}),
        ("what was I doing in the last hour", {"recall"}),
        ("whatsapp is showing a black screen, fix it", {"fix_app"}),
        ("open the pdf I downloaded yesterday", {"find_files", "open_file"}),
        ("I'm mood off today", set()),
        ("scroll down a bit", {"scroll"}),
        ("skip the ad", {"screen_items", "click"}),
        ("copy the last claude response and paste it in notepad", {"copy", "paste"}),
        ("learn my voice", {"voice_lock"}),
        ("video call jenny on whatsapp", {"whatsapp_call"}),
        ("search lofi in the youtube search box", {"type_into"}),
        ("what does this page say about pricing", {"read_screen"}),
    ]
    for text, expect in tests:
        calls.clear()
        start = time.time()
        reply, action = brain.think(text)
        used = brain.MODELS[brain.active][0]
        got = set(calls)
        ok = bool(got & expect) if expect else (not got and bool(reply))
        if text == "say hello in tamil":
            ok = ok and bool(brain.TAMIL_LETTERS.search(reply)) and "type_text" not in got
        if " and " in text:
            ok = expect <= got  # several asks: ALL of them must be done
        if any("஀" <= ch <= "௿" for ch in text):
            ok = ok and bool(brain.TAMIL_LETTERS.search(reply))
        check(f"brain: {text!r}", ok, f"tools {sorted(got) or 'none'}, reply {reply[:50]!r}, {used}, {time.time()-start:.1f}s")
        time.sleep(2)  # be gentle with the free limits
    tools.FUNCTIONS.update(real_functions)

# ---------- The running M.I.N.D ----------
section("5. The running M.I.N.D")
def get(path):
    with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=5) as resp:
        return json.load(resp)
try:
    s = get("/api/state")
    check("M.I.N.D is running (HUD server answers)", "status" in s)
    i = get("/api/info")
    check("HUD info has weather location, Wi-Fi, laptop and limits", all(k in i for k in ("system", "wifi", "location", "limits")))
    pid = open("mind.pid").read().strip() if os.path.exists("mind.pid") else ""
    check("pid file points to a running M.I.N.D", pid and str(pid) in subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout)
    count = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' -and $_.Name -like 'python*' }).Count"],
                           capture_output=True, text=True).stdout.strip()
    check("only one M.I.N.D running", count == "2", f"{count} python processes (2 = one M.I.N.D)")
    # (the HUD only opens when asked now; there must never be two)
    check("at most one HUD window", len(hud.hud_windows()) <= 1, f"{len(hud.hud_windows())} windows")
    import live_window
    if profile.get("live", True):
        check("M.I.N.D Live's hidden window is running (one)", len(live_window.windows()) == 1,
              f"{len(live_window.windows())} windows")
except OSError:
    check("M.I.N.D is running (HUD server answers)", False, "turn it on with the taskbar button, then run again")
log = open("mind.log", encoding="utf-8", errors="replace").read() if os.path.exists("mind.log") else ""
check("no crashes in mind.log", "Traceback" not in log, "see mind.log")
tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=os.path.dirname(HERE)).stdout
secrets = [f for f in tracked.split() if f.endswith((".env", "profile.json", "history.json", "reminders.json", "notes.txt", "mind.log", "conversations.jsonl", "voiceprint.npy")) or "/logs/" in f]
check("no secrets or personal files on GitHub", not secrets, str(secrets))

# ---------- Summary ----------
passed = sum(ok for _, ok, _ in results)
print(f"\n{passed} / {len(results)} checks passed")
for name, ok, detail in results:
    if not ok:
        print(f"  FAILED: {name}  {detail}")
