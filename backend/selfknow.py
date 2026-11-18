# Mind knows itself: "who made you?", "how do I restart you?", "how do I reinstall you?".
# The answers come from about_mind.md (plain-English manual, one "## " part per topic) plus live facts
# (how long it's been running, version, brain, voice lock...). Also "Mind, restart yourself".
import os
import re
import subprocess
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANUAL = os.path.join(BASE_DIR, "about_mind.md")
STARTED = time.time()
RESTART_WORDS = re.compile(r"\b(restart|reboot|re-start|start (yourself )?again|turn (yourself )?off and on)\b", re.I)

# Words people use for a topic -> words that are in that topic's heading
ALSO = {
    "founder": "made", "creator": "made", "built": "made", "build": "made", "owner": "made", "father": "made",
    "who": "made", "invented": "made", "history": "story", "born": "story", "birthday": "story", "age": "story",
    "old": "story", "name": "made", "stand": "made",
    "start": "on", "open": "on", "launch": "on", "boot": "on", "wake": "on",
    "stop": "off", "close": "off", "shut": "off", "kill": "off", "quit": "off", "exit": "off",
    "reboot": "restart", "reload": "restart",
    "broken": "fix", "problem": "fix", "error": "fix", "bug": "fix", "crash": "fix", "repair": "fix", "debug": "fix",
    "issue": "fix", "wrong": "fix", "listen": "fix", "answer": "fix", "understand": "fix", "work properly": "fix", "slow": "fix", "hear": "fix", "log": "fix", "logs": "fix", "test": "fix",
    "update": "upgrade", "improve": "upgrade", "newer": "upgrade", "pull": "upgrade", "latest": "upgrade",
    "remove": "delete", "uninstall": "delete", "erase": "delete", "rid": "delete", "wipe": "delete",
    "setup": "install", "new": "install", "laptop": "install", "clone": "install", "fresh": "install",
    "again": "reinstall", "clean": "reinstall",
    "backup": "backup", "save": "backup", "files": "backup", "memory": "backup", "secret": "backup", "keys": "backup",
    "settings": "settings", "setting": "settings", "change": "settings", "customize": "settings", "control": "settings",
    "privacy": "privacy", "safe": "privacy", "data": "privacy", "secure": "privacy", "security": "privacy", "spy": "privacy",
    "cost": "costs", "free": "costs", "price": "costs", "limit": "costs", "pay": "costs", "money": "costs",
    "work": "work", "brain": "work", "think": "work", "how": "work", "made of": "work", "tech": "work",
    "hud": "parts", "reactor": "parts", "phone": "parts", "jarvis": "parts", "extension": "parts", "taskbar": "parts",
    "features": "features", "abilities": "features", "can": "features",
}
LITTLE = set("a an the i you your me my to of in on is are do does how what could would will it and or for with mind "
             "please bro tell about".split())

def parts():
    # [(heading, body)] from the manual (read fresh each time, so edits count without a restart)
    try:
        text = open(MANUAL, encoding="utf-8").read()
    except OSError:
        return []
    found = []
    for chunk in re.split(r"^## ", text, flags=re.M)[1:]:
        heading, _, body = chunk.partition("\n")
        found.append((heading.strip(), body.strip()))
    return found

def words(text):
    return [w for w in re.findall(r"[a-z]+", (text or "").lower()) if w not in LITTLE]

def best_parts(question, how_many=2):
    asked = words(question)
    wanted = set(asked) | {topic for w in asked for k, topic in ALSO.items() if w == k or (len(k) >= 4 and w.startswith(k))}
    if re.search(r"\bre-?install", question or "", re.I):
        wanted.add("reinstall")
    scored = []
    for heading, body in parts():
        head = set(words(heading))
        score = 5 * len(wanted & head) + 0.3 * len(wanted & set(words(body)))
        scored.append((score, heading, body))
    scored.sort(key=lambda x: -x[0])
    good = [p for p in scored if p[0] >= 1][:how_many]
    return good or scored[:2]  # (nothing matched: "who made me" + "how I work" are the safest)

def live_facts():
    # Short true facts about this running copy
    import state
    from memory import profile
    facts = []
    up = int(time.time() - STARTED)
    facts.append(f"Running for {up // 3600} h {up % 3600 // 60} min this time")
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ad|%s", "--date=format:%d %b %Y %H:%M"], cwd=BASE_DIR,
                             capture_output=True, text=True, timeout=4, creationflags=0x08000000).stdout.strip()
        count = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=BASE_DIR, capture_output=True, text=True,
                               timeout=4, creationflags=0x08000000).stdout.strip()
        if out:
            when, what = out.split("|", 1)
            facts.append(f"Version {count} (last upgrade {when}: {what[:90]})")
    except Exception:
        pass
    facts.append("Main brain: Gemini Live" + ("" if profile.get("live", True) else " is switched OFF, using the backup brain"))
    facts.append("Mic: " + ("offline (muted)" if getattr(state, "muted", False) else "listening for 'Mind'"))
    facts.append("Voice lock: " + ("learned" if os.path.exists(os.path.join(BASE_DIR, "voiceprint.npy")) else "not learned yet (say 'Mind, learn my voice')"))
    try:
        import tools
        facts.append(f"{len(tools.TOOLS)} tools")
    except Exception:
        pass
    return "; ".join(facts)

def about_mind(question="", show=False):
    # The tool: answers questions about M.I.N.D itself from its manual
    picked = best_parts(question)
    text = "\n\n".join(f"[{h}]\n{b}" for _, h, b in picked)
    if str(show).lower() in ("true", "1", "yes") or any(re.search(r"^\d+\.", b, re.M) for _, _, b in picked):
        show_on_hud(picked)
        shown = " The steps are also on the HUD (say so in a few words)."
    else:
        shown = ""
    return (f"FACTS ABOUT YOU (M.I.N.D), answer ONLY from these, in simple friendly words, as yourself ('I', 'my "
            f"founder VVP'). For steps: say the 2-3 easiest ones, short.{shown}\nLive: {live_facts()}\n\n{text}")

def show_on_hud(picked):
    import showcase
    groups = []
    for _, heading, body in picked:
        lines = [re.sub(r"^(\d+\.|-)\s*", "", l).strip() for l in body.splitlines() if l.strip()]
        groups.append({"icon": "🧠", "name": heading, "say": lines})
    showcase.put_on_hud({"kind": "abilities", "title": "About me", "groups": groups, "cards": [], "info": {},
                         "read_only": True}, minutes=15)

# ---------- "Mind, restart yourself" ----------
def asked_me_to_restart(said):
    # "Mind, restart" / "restart yourself" / "restart Mind" yes; "Mind, restart VS Code" no
    said = re.sub(r"^\W*((hey|hi|ok|okay|yo)\W+)?mind\b\W*", "", (said or "").strip(), flags=re.I)
    found = RESTART_WORDS.search(said)
    if not found:
        return False
    rest = re.sub(r"\b(please|bro|now|again|quickly|once|right|properly|can you|could you|will you)\b|\W", " ",
                  said[found.end():], flags=re.I).strip()
    return not rest or bool(re.search(r"\b(yourself|you|mind|m\.?i\.?n\.?d|your ?self)\b", said, re.I))

def restart_mind():
    import state
    if not asked_me_to_restart(getattr(state, "last_user_text", "")):
        return "Not restarted: they didn't ask ME (M.I.N.D) to restart. If they meant an app, use fix_app."
    restart_now("asked by voice")
    return "Restarting in a few seconds (back in about 30 seconds). Say ONE short line like 'Restarting, back in a few seconds.'"

def restart_now(why):
    pythonw = os.path.join(BASE_DIR, "venv", "Scripts", "pythonw.exe")
    pid = os.getpid()
    # A tiny separate program waits until this M.I.N.D has fully closed, then starts a new one
    helper = ("import time, subprocess, psutil, os\n"
              f"end = time.time() + 40\n"
              f"while psutil.pid_exists({pid}) and time.time() < end: time.sleep(0.3)\n"
              f"pidfile = os.path.join(r'{BASE_DIR}', 'mind.pid')\n"
              "while os.path.exists(pidfile) and time.time() < end: time.sleep(0.3)\n"
              "time.sleep(1.5)\n"
              f"subprocess.Popen([r'{pythonw}', 'main.py'], cwd=r'{BASE_DIR}', creationflags=0x08000000 | 0x00000008)\n")
    subprocess.Popen([pythonw, "-c", helper], cwd=BASE_DIR, creationflags=0x08000000 | 0x00000008)

    def later():
        time.sleep(6)  # (time to say "restarting")
        import server
        server.power_off()
    threading.Thread(target=later, daemon=True).start()
    print(f"(Restarting myself: {why})")
