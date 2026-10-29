# Writing help: fixes grammar/spelling in what you wrote ("Mind, fix my grammar").
# Takes the text you gave, or the text you selected, or what's in the box you're typing in
# (WhatsApp, Gmail, Teams...). Shows before/after with short "why" notes on the HUD (so you learn),
# copies the fixed text, and only replaces your text if you said so ("replace it").
import re
import json
import time
import win32gui
import state
import pc
import showcase
from memory import profile, save_profile

GRAMMAR_RULES = """You fix English written by the user (an Indian software developer) before they send it.
- Fix grammar, spelling, punctuation, capital letters and missing words (like a missing "I" or "the").
- Keep their meaning, tone and formality (a message to a boss stays polite; a chat to a friend stays casual).
- Keep names, product and project names (just fix their capitals if clearly wrong). Add nothing new.
- Make it sound natural, like a fluent professional, but don't rewrite what's already fine.
- Understand what they MEAN, like a friend would: if they describe the message ("I need to text my sir that
  ..."), write the message itself to that person. Fix typos of short forms (wrh/wfh = work from home) and
  awkward phrases ("reach dfresh" = work on dFresh, "tomorrow is start wfh" = from tomorrow I'll work from home).
  Write it out in full words, never leave unclear short forms.
Reply with ONLY this JSON:
{"corrected": "the fixed text", "changes": [{"from": "their words", "to": "fixed words", "why": "reason, max 8 words"}]}
At most 6 changes, most important first. Already correct: corrected = their text, changes = []."""

REPLACE_WORDS = re.compile(r"\b(replace|change it|update it|put it|fix it there|in the box|correct it there|swap)\b", re.I)
CTRL, KEY_A, KEY_C, KEY_V = 0x11, 0x41, 0x43, 0x56

def selected_text(hwnd):
    # Whatever is selected in that window (Ctrl+C), without losing what was on the clipboard
    before = pc.clipboard_text()
    pc.set_clipboard("")
    pc.tap_keys(CTRL, KEY_C)
    for _ in range(8):
        time.sleep(0.05)
        got = pc.clipboard_text()
        if got:
            break
    pc.set_clipboard(before)
    return got.strip()

def box_text():
    # The text in the box that has the keyboard focus (where you're typing), via the screen-reader API
    uia = pc.automation()
    element = uia.GetFocusedElement()
    if not element:
        return ""
    from comtypes.gen.UIAutomationClient import IUIAutomationValuePattern, IUIAutomationTextPattern
    try:
        return element.GetCurrentPattern(10002).QueryInterface(IUIAutomationValuePattern).CurrentValue.strip()
    except Exception:
        pass
    try:
        return element.GetCurrentPattern(10014).QueryInterface(IUIAutomationTextPattern).DocumentRange.GetText(-1).strip()
    except Exception:
        return ""

def name_hint():
    # Their projects, so "dshield" is written the way they write it (dShield, like dAssure, dEpr, dForms)
    names = pc.project_names(30)
    styled = [n for n in names if re.fullmatch(r"d[A-Z]\w+", n)]
    if not names:
        return ""
    if styled:  # their short "d" products in the same style: dshield -> dShield, dfresh -> dFresh
        names = ["d" + n[1].upper() + n[2:] if re.fullmatch(r"d[a-z]{3,8}", n) else n for n in names]
    return " Their work project/product names (write them exactly like this): " + ", ".join(names) + "."

def corrected(text):
    import brain
    answer = brain.write(GRAMMAR_RULES + name_hint(), text, seconds=12, writers=brain.QUICK_WRITERS)
    found = re.search(r"\{.*\}", answer or "", re.S)
    if not found:
        return None
    try:
        fixed = json.loads(found.group(0), strict=False)
    except ValueError:
        return None
    if not isinstance(fixed.get("corrected"), str) or not fixed["corrected"].strip():
        return None
    changes = [c for c in fixed.get("changes") or [] if isinstance(c, dict) and c.get("from") != c.get("to")]
    return fixed["corrected"].strip(), changes[:6]

def remember_mistakes(changes):
    # Keeps the last 40 "why"s, so "what mistakes do I make most?" can be answered
    notes = profile.setdefault("grammar_notes", [])
    notes.extend(str(c.get("why", ""))[:60] for c in changes if c.get("why"))
    profile["grammar_notes"] = notes[-40:]
    save_profile()

ABOUT_FIXING = re.compile(r"\b(grammar|sentence|spelling|fix|correct|check|mind|mindfix|message|this|it|my)\b", re.I)

def just_the_ask(text):
    # The brain sometimes passes the spoken ask itself ("mindfix, my sentence, grammar") as the text:
    # that's not their writing, so read the box/selection instead
    words = re.findall(r"[\w']+", text.lower())
    said = state.last_user_text.lower()
    return bool(words) and (all(ABOUT_FIXING.fullmatch(w) or w in ("the", "a", "and", "please", "s") for w in words)
                            or (len(words) <= 8 and " ".join(words) in " ".join(re.findall(r"[\w']+", said))
                                and ABOUT_FIXING.search(text)))

NEW_CHECK = re.compile(r"(fix|grammar|grammer|check|correct|spelling|sentence)", re.I)

def fix_grammar(text="", replace=False):
    # "yes" / "replace it" right after a fix: put that fix in, no new check
    new_ask = NEW_CHECK.search(state.last_user_text or "")  # "fix my grammar and replace it" = a new check
    if replace in (True, "true", "yes") and not text.strip() and pending_fix() and not new_ask:
        return replace_now()
    hwnd = pc.target_window()
    if just_the_ask(text):
        text = ""
    source = "given"
    if not text.strip():
        if not hwnd:
            return "No text: select it, click in the box, or say/paste the text."
        if win32gui.GetForegroundWindow() != hwnd:
            pc.bring_to_front(hwnd)  # the box keeps its cursor when its window comes back
            time.sleep(0.4)
        text, source = selected_text(hwnd), "selection"
        if not text:
            text, source = box_text(), "box"
    if not text.strip():
        return "Found no text to check: select it or click inside the box first."
    if len(text) > 4000:
        return "That's too long to check at once; select a part of it."
    result = corrected(text)
    if not result:
        return "Couldn't check it right now (the brain didn't answer properly). Try again?"
    fixed, changes = result
    pc.set_clipboard(fixed)
    showcase.put_on_hud({"kind": "grammar", "title": "Grammar check", "cards": [], "info": {},
                         "original": text, "fixed": fixed, "changes": changes}, minutes=10)
    if changes:
        remember_mistakes(changes)
    can_replace = bool(changes) and source in ("selection", "box") and bool(hwnd)
    last_fix.update(fixed=fixed, hwnd=hwnd, source=source, at=time.time(), replaced=False)
    # The floating reactor shows the fix with Copy / Replace buttons (no need to open the HUD)
    state.offer = {"id": int(time.time() * 1000), "text": fixed, "until": time.time() + OFFER_SECONDS,
                   "replace": can_replace, "done": ""}
    if not changes:
        return "Checked it: it's already correct. (Copied.)"
    if replace in (True, "true", "yes") and REPLACE_WORDS.search(state.last_user_text or "") and can_replace:
        return replace_now()
    notes = "; ".join(f"'{c.get('from')}' -> '{c.get('to')}' ({c.get('why')})" for c in changes)
    return (f"Fixed {len(changes)} thing(s); the corrected text is copied, on the HUD and the floating reactor. "
            f"Corrected: {fixed[:500]} Changes: {notes}")

# ---------- Replacing your text with the fix ----------
OFFER_SECONDS = 60     # the Copy / Replace buttons stay on the floating reactor this long
YES_SECONDS = 3 * 60   # "yes, replace it" still works this long after the fix
last_fix = {}

def pending_fix():
    return bool(last_fix.get("fixed")) and not last_fix.get("replaced") and time.time() - last_fix.get("at", 0) < YES_SECONDS

def replace_now():
    # Puts the fixed text where the original was (never presses send)
    if not pending_fix():
        return "Nothing to replace: ask me to fix something first."
    hwnd, source = last_fix["hwnd"], last_fix["source"]
    if source not in ("selection", "box") or not hwnd or not win32gui.IsWindow(hwnd):
        return "Can't replace that one (it wasn't in a box on screen); the fix is copied, just paste it."
    pc.set_clipboard(last_fix["fixed"])
    if win32gui.GetForegroundWindow() != hwnd:
        # (only when needed: its Alt key press puts Chrome's focus on its menu, away from the box)
        pc.bring_to_front(hwnd)
        time.sleep(0.3)
    if source == "box":
        pc.tap_keys(CTRL, KEY_A)  # the whole box (a selection is replaced as it is)
        time.sleep(0.1)
    pc.tap_keys(CTRL, KEY_V)
    last_fix["replaced"] = True
    if state.offer:
        state.offer = dict(state.offer, done="Replaced ✓", until=time.time() + 4)
    return "Replaced their text with the fix (not sent)."

def copy_now():
    # The Copy button on the floating reactor
    if not state.offer:
        return
    pc.set_clipboard(state.offer["text"])
    state.offer = dict(state.offer, done="Copied ✓", until=time.time() + 4)
