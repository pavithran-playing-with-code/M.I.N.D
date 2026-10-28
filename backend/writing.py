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

def fix_grammar(text="", replace=False):
    hwnd = pc.target_window()
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
    replaced = ""
    wants_replace = replace in (True, "true", "yes") and REPLACE_WORDS.search(state.last_user_text or "")
    if wants_replace and changes and source in ("selection", "box") and hwnd:
        if win32gui.GetForegroundWindow() != hwnd:
            # (only when needed: its Alt key press puts Chrome's focus on its menu, away from the box)
            pc.bring_to_front(hwnd)
            time.sleep(0.3)
        if source == "box":
            pc.tap_keys(CTRL, KEY_A)  # the whole box (a selection is replaced as it is)
            time.sleep(0.1)
        pc.tap_keys(CTRL, KEY_V)
        replaced = " Replaced their text with it (not sent)."
    if not changes:
        return "Checked it: it's already correct. (Copied.)"
    notes = "; ".join(f"'{c.get('from')}' -> '{c.get('to')}' ({c.get('why')})" for c in changes)
    return (f"Fixed {len(changes)} thing(s); the corrected text is copied and on the HUD.{replaced} "
            f"Corrected: {fixed[:500]} Changes: {notes}")
