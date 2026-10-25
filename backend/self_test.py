# Self test: checks that every part of M.I.N.D works, without opening apps, playing music
# or changing your settings (all actions are faked, saving is turned off).
# Run from the backend folder:   venv\Scripts\python.exe self_test.py
# Add "--brain" to also run the 20 brain tests. They use ~40 requests of today's free brain limit,
# so run them only after changing the prompt or tools (running them often made Groq rest all day).
import os
import re
import sys
import json
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
check("brain request stays small (< 15,500 characters)", request_size < 15500, f"{request_size} characters")
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
check("Tamil sentences use a Tamil voice", voice.voice_for("வணக்கம்").startswith("ta-"))
check("English sentences don't use a Tamil voice", not voice.voice_for("Hello there").startswith("ta-"))
check("echo check: own sentence = echo", voice.is_echo("the weather in chennai", "The weather in Chennai is warm."))
check("echo check: new words = you", not voice.is_echo("open youtube please", "The weather in Chennai is warm."))
check("broken reply guard", brain.looks_broken("… ... … ... …") and not brain.looks_broken("Done!"))
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
          or (isinstance(found, str) and "Several" in found), str(found)[:80])
    check("unknown Chrome account isn't guessed", isinstance(pc.find_chrome_profile("zzqqxxw@nowhere.com"), str))

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
opened = []
real_open, real_remember, real_account = tools.webbrowser.open, tools.remember_song, tools.pc.open_in_browser
tools.webbrowser.open, tools.remember_song = opened.append, lambda q: None
tools.pc.open_in_browser = lambda url, account="": opened.append(url)  # never opens a real window
safe("YouTube lookup finds a video", lambda: tools.play_youtube("Rathinamo Saurav Srisan"),
     lambda r: r.startswith("Playing") and opened and "watch?v=" in opened[0])
tools.webbrowser.open, tools.remember_song, tools.pc.open_in_browser = real_open, real_remember, real_account
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
        ("what's on my screen", {"look_at_screen"}),
        ("open the hub", {"open_hud"}),
        ("நாளைக்கு மழை வருமா", {"get_weather"}),
        ("volume கொஞ்சம் குறை", {"change_volume"}),
        ("what is the capital of japan", set()),
        ("say hello in tamil", set()),
        ("good morning", {"daily_briefing"}),
        ("what song did you play yesterday", {"recall"}),
        ("read my notes", {"recall"}),
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
    check("exactly one HUD window", len(hud.hud_windows()) == 1, f"{len(hud.hud_windows())} windows")
except OSError:
    check("M.I.N.D is running (HUD server answers)", False, "turn it on with the taskbar button, then run again")
log = open("mind.log", encoding="utf-8", errors="replace").read() if os.path.exists("mind.log") else ""
check("no crashes in mind.log", "Traceback" not in log, "see mind.log")
tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=os.path.dirname(HERE)).stdout
secrets = [f for f in tracked.split() if f.endswith((".env", "profile.json", "history.json", "reminders.json", "notes.txt", "mind.log", "conversations.jsonl")) or "/logs/" in f]
check("no secrets or personal files on GitHub", not secrets, str(secrets))

# ---------- Summary ----------
passed = sum(ok for _, ok, _ in results)
print(f"\n{passed} / {len(results)} checks passed")
for name, ok, detail in results:
    if not ok:
        print(f"  FAILED: {name}  {detail}")
