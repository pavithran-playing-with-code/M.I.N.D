# Mini-apps on the HUD: typing practice (a passage, you type it, M.I.N.D gets your speed and accuracy)
# and little games. Progress is in profile.json ("typing", "games").
import time
import random
import state
from memory import profile, save_profile

# ---------- Typing practice ----------
PASSAGES = {
    "easy": ["The sun is warm and the sky is blue. A small bird sings on the tree near my window.",
             "I like to read books at night. My cat sleeps next to me and the room is quiet.",
             "We went to the beach and built a big sand castle. Then the waves came and took it away."],
    "medium": ["Learning to type fast is like learning music: slow and correct practice builds speed that lasts.",
               "Chennai wakes up early. Tea stalls open, buses fill up, and the smell of filter coffee is everywhere.",
               "A good programmer reads the error message first, then the code, and only then starts to change things."],
    "hard": ["Jarvis, analyse the telemetry: thrust at 87%, altitude 12,400 ft, and fuel reserves dropping by 3.5% a minute!",
             "\"Quick,\" she whispered, \"the zebra jumped over 2 lazy dogs at 9:45 PM; nobody noticed (except me).\"",
             "Debugging tip #1: if `x == null` throws, check the API response {status: 404} before blaming React."],
}

TIMED_WORDS = 400  # a timed test needs more text than anyone can type in the time

def typing_practice(level="medium", topic="", seconds=0):
    # Tool: typing practice on the HUD. seconds=0: one passage. seconds=30/60/120: a timed test with endless
    # lines and a countdown. Their own topic = text written about it.
    import showcase
    level = level if level in PASSAGES else "medium"
    seconds = int(float(seconds or 0))
    seconds = min((30, 60, 120), key=lambda s: abs(s - seconds)) if seconds > 0 else 0
    text = ""
    if topic:
        import brain
        length = "a long typing-test text of about 250 words" if seconds else "ONE typing-practice passage of 25-40 words"
        text = brain.write(f"Write {length} about the topic, plain text only, no title, no quotes around it. "
                           + {"easy": "Simple words.", "hard": "Use numbers and punctuation too."}.get(level, ""),
                           topic, seconds=15, writers=brain.QUICK_WRITERS)
        text = " ".join((text or "").split())[:2500 if seconds else 300]
    if len(text) < 40:
        text = random.choice(PASSAGES[level])
    if seconds:
        pool = PASSAGES[level][:]
        while len(text.split()) < TIMED_WORDS:  # (keep adding the level's passages in a new order)
            random.shuffle(pool)
            text += " " + " ".join(pool)
    mode = f"{seconds}s" if seconds else "passage"
    title = f"Typing test · {seconds} seconds · {level}" if seconds else f"Typing practice · {level}"
    showcase.put_on_hud({"kind": "typing", "title": title, "text": text.strip(), "level": level, "seconds": seconds,
                         "best": best_typing(mode), "cards": [], "info": {}}, minutes=30)
    best = best_typing(mode)
    start = (f"A {seconds}-second test is on the HUD; the countdown starts with their first key." if seconds
             else f"{'An' if level == 'easy' else 'A'} {level} passage is on the HUD; they just start typing (the timer starts with the first key).")
    return start + (f" Their best here: {best} words per minute." if best else " First time: no record yet.")

def best_typing(mode):
    return max((r["wpm"] for r in profile.get("typing", []) if r.get("mode", "passage") == mode), default=0)

def typing_result(wpm, accuracy, seconds, mode="passage"):
    # From the HUD when a passage or a timed test is finished: kept, and M.I.N.D says how it went
    history = profile.setdefault("typing", [])
    best = best_typing(mode)
    history.append({"wpm": wpm, "accuracy": accuracy, "seconds": seconds, "mode": mode, "at": time.strftime("%Y-%m-%d %H:%M")})
    del history[:-30]
    save_profile()
    note = " That's a new best!" if best and wpm > best else (f" Your best is {best}." if best else "")
    state.alerts.append(f"Typing done: {wpm} words per minute with {accuracy}% accuracy.{note}")

# ---------- Little games on the HUD (src/components/Games.jsx) ----------
GAMES = {"snake": "Snake", "2048": "2048", "tictactoe": "Tic-tac-toe"}

def play_game(game="snake"):
    # Tool: "Mind, let's play snake / 2048 / tic tac toe"
    import showcase
    said = str(game or "snake").lower().replace("-", "").replace(" ", "")
    game = next((g for g in GAMES if g in said), "tictactoe" if "tic" in said or "noughts" in said else "snake")
    record = profile.get("games", {}).get(game, {})
    showcase.put_on_hud({"kind": "game", "game": game, "title": GAMES[game], "best": record.get("best", 0),
                         "record": {k: record.get(k, 0) for k in ("won", "lost", "draw")}, "cards": [], "info": {}}, minutes=60)
    how = "they click a square; M.I.N.D plays the circles" if game == "tictactoe" else "arrow keys or WASD; Space starts again"
    best = f" Their best: {record['best']}." if record.get("best") else ""
    return f"{GAMES[game]} is on the HUD ({how}).{best} Say it in a few words."

def game_result(game, score, won, draw=False):
    # From the HUD at the end of a game: the record is kept; a new best is said out loud
    if game not in GAMES:
        return
    record = profile.setdefault("games", {}).setdefault(game, {})
    record["played"] = record.get("played", 0) + 1
    if game == "tictactoe":
        key = "draw" if draw else "won" if won else "lost"
        record[key] = record.get(key, 0) + 1
    else:
        old = record.get("best", 0)
        if score > old:
            record["best"] = score
            if old:
                state.alerts.append(f"New best in {GAMES[game]}: {score} (was {old})!")
    save_profile()


# ---------- "Mind, what can you do?" (owner: "I don't even know what features I have") ----------
# Every ability with things to SAY (no keywords needed: any natural way works). Shown on the HUD; tapping an
# example sends it as a command. Keep this list in step with the tools.
ABILITIES = [
    ("🎵", "Music & videos", ["play Rathinamo", "play some lofi", "pause the song", "play the song", "replay the song",
                              "next song", "skip ahead 30 seconds", "go back 10 seconds", "play it faster",
                              "turn on subtitles", "full screen", "which song is this?",
                              "volume to 30", "find the video where a guy builds a pool in the jungle"]),
    ("💻", "The laptop itself", ["make the screen brighter", "brightness to 40", "turn off the screen",
                                "take a screenshot", "dark mode", "put the laptop to sleep", "shut down the laptop",
                                "restart the laptop", "turn on bluetooth (opens the right settings page)",
                                "make a new folder called work", "close this", "minimize this", "reopen the tab I closed"]),
    ("📊", "Life dashboard", ["show my week", "my dashboard", "my stats", "how was my month?", "show my progress"]),
    ("🛡", "Guard", ["guard my laptop (anyone who touches it: photo + lock + phone alert)", "protect mode",
                    "security mode", "keep an eye on my laptop", "I'm stepping out, watch my laptop",
                    "(turn it off in the phone app's Laptop tab, or unlock with your PIN)"]),
    ("📧", "Gmail", ["open my mail (or Ctrl + M on the HUD)", "any important mails?", "read the second one", "any mail from Penny this week?",
                    "open that mail", "what did the bank mail say?", "anything in spam?",
                    "reply to the second one saying I'll join", "send it", "delete that mail", "mark it as read"]),
    ("⌨️", "Project terminals", ["run npm run dev in gameroom", "stop gameroom's backend (like Ctrl+C)",
                                 "what's running in gameroom?", "docker compose up in blogsite", "npm install in myshop"]),
    ("🖥️", "Your laptop", ["how's my battery?", "how much charge do my earbuds have?", "what's using my RAM?", "show my laptop map",
                          "lock my laptop", "open WhatsApp", "close Chrome", "maximize VS Code"]),
    ("🪟", "Window layouts", ["put VS Code on the left and Claude on the right", "WhatsApp in the top right corner",
                             "put these side by side", "save this as my coding setup", "coding setup", "undo that", "swap them"]),
    ("📂", "Projects & files", ["open the myshop project", "open yesterday's tabs", "work mode",
                               "find the pdf I downloaded today", "send that file to my phone"]),
    ("🌐", "Browser & screen", ["open YouTube in my tiger account", "close the YouTube tab", "switch to the Claude tab",
                               "scroll down a bit", "click the second video", "what's on my screen?", "read this page"]),
    ("🤖", "Claude helper", ["is my Claude prompt done?", "do what Claude said", "send Claude Code's questions to my Claude chat",
                             "paste a screenshot into Claude", "continue in that chat"]),
    ("✍️", "Writing", ["fix my grammar", "type hello in this box", "copy the last answer", "paste it in WhatsApp"]),
    ("💬", "WhatsApp", ["open Penny's chat", "message Penny I'm on the way", "video call Penny"]),
    ("⏰", "Reminders & memory", ["remind me in 10 minutes to drink water", "cancel the water reminder",
                                  "remember I like dark mode", "what did I ask you yesterday?",
                                  "how was my day?", "how long did I code yesterday?"]),
    ("📝", "Notes", ["note: call the bank about my card", "jot down: pay rent on the 1st",
                    "add buy milk to my list", "what's on my notes?", "tick off the bank one", "pin the rent note",
                    "remind me about the milk note at 6", "clear my done notes"]),
    ("☁️", "Weather & news", ["what's the weather?", "will it rain tomorrow?", "any news today?",
                              "gold rate in Chennai today", "who won the last India match?"]),
    ("🖼️", "HUD & pictures", ["show me Iron Man suits", "suggest a keyboard under 2000", "open the HUD",
                              "Jarvis mode", "add a clock for Tokyo", "open settings"]),
    ("🎮", "Fun", ["let's play snake", "play 2048", "tic tac toe", "typing test for 60 seconds", "tell me a story"]),
    ("🎧", "Hear & see", ["what song is this? (then hum or sing)", "look at this error", "what's on my screen?"]),
    ("🔄", "Updates & feedback", ["any updates?", "update yourself", "send feedback: the reactor is too big",
                                  "report a bug: it didn't hear me"]),
    ("📱", "Phone", ["set up my phone (QR code)", "send this to my phone", "send a screenshot to my phone",
                     "(phone app: windows live, files, clipboard, talk to Mind)", "(phone app, Windows tab: open apps/sites/new tab, close windows and tabs)"]),
    ("🧠", "About me", ["who made you?", "how do I restart you?", "restart yourself", "how do I fix you?",
                       "how do I upgrade you?", "how do I reinstall you?", "how do I delete you completely?",
                       "what files should I back up?", "is my data safe?"]),
    ("🔕", "Quiet", ["Mind, stop", "go offline", "I'm on a call", "don't disturb me for 30 minutes",
                    "learn my voice", "only listen to me"]),
]

# "How do I use you?": the basics, shown once by itself after the first-run setup (main.py) and on request.
# Keep it true when the clicks/taps change (also in about_mind.md).
# The "Mind Guide" panel (src/components/Guide.jsx): HOW to control Mind, as gesture -> what happens.
# Keep it TRUE when clicks/taps change (also README / about_mind.md). Short words only: people scan, not read.
CONTROLS = [
    ("🗣", "Your voice", [("Say “Mind, …”", "Ask anything, in your own words"),
                          ("“Mind, stop”", "Quiet right away"),
                          ("“Mind, help”", "Opens this guide")]),
    ("🔵", "Floating reactor", [("Click", "Type to Mind"),
                                ("Double-click", "Show / hide the HUD"),
                                ("Double-click anywhere else", "Close the text it's showing"),
                                ("Hover", "Volume · brightness · mic"),
                                ("Drag", "Move it anywhere"),
                                ("Scroll on it", "Bigger / smaller"),
                                ("Click while it talks", "Stop it")]),
    ("🎯", "HUD core", [("1 tap", "Settings"),
                        ("2 taps", "Mic off / on"),
                        ("3 taps", "Jarvis mode"),
                        ("Hold 2 s", "Turn Mind off")]),
    ("📌", "Taskbar button", [("1 click", "Turn Mind on / off"),
                              ("Double-click", "Show / hide the HUD"),
                              ("Pin it", "Start → type MIND → right-click → Pin")]),
    ("🧩", "HUD cards", [("Drag", "Move"),
                         ("Drag an edge", "Resize"),
                         ("Double-click title", "Shrink to an icon"),
                         ("Drop at the bottom", "Hide it")]),
    ("⌨️", "Keys on the HUD", [("F1", "This guide"),
                               ("Ctrl + ,", "Settings"),
                               ("Ctrl + M", "Mail"),
                               ("Esc", "Close a panel")]),
]
# The first page of the guide, for someone who has never used Mind: five steps, one plain line each.
# "try" = a button that does it right away. Keep it this short: no step may need a second read.
START = [
    ("🗣", "Talk to me", "Say “Mind,” and then what you want, in your own words.", "what's the weather?"),
    ("⌨️", "Or type", "Click the glowing circle on your screen and type instead.", ""),
    ("🤫", "Make me quiet", "Say “Mind, stop”, or click the circle while I'm talking.", ""),
    ("🖥", "See the big screen", "Double-click the circle: this screen opens or hides.", ""),
    ("❓", "Stuck?", "Say “Mind, help” or press F1 and this guide comes back. Esc hides it.", ""),
]
START_TRY = ["play a song", "remind me in 10 minutes to drink water", "open notepad", "how's my battery?", "what can you do?"]

PHONE_GUIDE = [
    ("🔗", "Set it up", [("Say", "“Mind, set up my phone”"), ("Then", "Scan the QR with your phone")]),
    ("🪟", "Windows tab", [("Tap a window", "See it live, tap = click"), ("Hold, then drag", "Select text"),
                          ("Pinch", "Zoom in")]),
    ("💬", "Mind tab", [("Type or hold 🎤", "Talk to Mind"), ("📧", "Your mail"), ("🔔", "Every notification")]),
    ("💻", "Laptop tab", [("Files", "Send / get any file"), ("🛡 Guard", "Photo + lock if someone touches it"),
                         ("Quick", "Screen off · lock")]),
    ("🖱", "Remote tab", [("Touchpad", "Move the mouse"), ("⏯ 🔊", "Music and volume"), ("⌨", "Type on the laptop")]),
]
GUIDE_WORDS = ("guide", "how to use", "use you", "getting started", "start", "basics", "tutorial", "help me use",
               "help", "controls", "gesture", "shortcut", "click", "tap")

def open_guide(tab="start", find=""):
    # Opens the Mind Guide on the HUD (tab: start / controls / say / phone; find = filter for "say")
    import hud
    import state
    import time
    state.guide.update(n=state.guide["n"] + 1, tab=tab, find=find, at=time.time())
    hud.open_hud()

def hide_guide():
    import state
    import time
    state.guide.update(n=state.guide["n"] + 1, tab="close", find="", at=time.time())

def show_guide():
    open_guide("start")

def guide_data():
    rows = lambda items: [{"icon": i, "name": n, "rows": [{"do": d, "get": g} for d, g in r]} for i, n, r in items]
    return {"start": [{"icon": i, "name": n, "line": l, "try": t} for i, n, l, t in START], "start_try": START_TRY,
            "controls": rows(CONTROLS), "phone": rows(PHONE_GUIDE),
            "say": [{"icon": i, "name": n, "say": s} for i, n, s in ABILITIES]}

def what_can_you_do(topic=""):
    # Tool: the Mind Guide on the HUD. topic "guide"/"how to use" = the Controls tab, a topic = Say-it filtered to it
    want = (topic or "").lower().strip()
    if want in ("close", "hide"):
        hide_guide()
        return "The guide is hidden. ('Mind, help' or F1 brings it back.)"
    if any(w in want for w in ("control", "gesture", "shortcut", "click", "tap", "key")):
        open_guide("controls")
        return ("The Mind Guide is open on the HUD at 'Controls' (every click, tap and key). Say in ONE short "
                "sentence that it's there.")
    if any(w in want for w in GUIDE_WORDS):
        open_guide("start")
        return ("The Mind Guide is open on the HUD at 'Start here' (five simple steps, with buttons to try). Say in "
                "ONE short sentence that it's there.")
    if "phone" in want:
        open_guide("phone")
        return "The Mind Guide is open on the HUD at 'Phone'. Say in ONE short sentence that it's there."
    names = [n for _, n, s in ABILITIES if want and (want in n.lower() or any(want in x.lower() for x in s))]
    open_guide("say", want if names else "")
    return ("The Mind Guide is open on the HUD at 'Say it': everything Mind can do, tap any example to try it. "
            "Say in ONE short sentence: it's on the HUD, they can just talk normally, no exact words needed.")
