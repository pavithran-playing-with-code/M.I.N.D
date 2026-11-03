# Memory: everything M.I.N.D knows about you lives in profile.json, not in code.
# Keys: name, real_name, city, wake_word, facts, corrections, voice, language... (and many settings)
import os
import json
import time
import threading
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # the backend folder
PROFILE_FILE = os.path.join(BASE_DIR, "profile.json")
BACKUP_FILE = PROFILE_FILE + ".bak"  # the last good copy (git-ignored)
load_dotenv(os.path.join(BASE_DIR, ".env"))  # loads the API keys (Groq, Gemini)

def load_profile():
    # profile.json, or if it's damaged, the last good copy (a damaged file used to load as empty, and the next
    # save would have wiped every setting)
    for path in (PROFILE_FILE, BACKUP_FILE):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if path == BACKUP_FILE:
                print("(profile.json was damaged: using the last good copy)")
            return loaded
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Couldn't read {os.path.basename(path)}:", str(e)[:80])
    return {}

saving = threading.Lock()

def safe_write(path, text):
    # Saving without ever leaving a half-written file: write a copy, then swap it in. Windows sometimes holds a
    # file for a moment (a reader, antivirus): try again a few times ("Couldn't save the HUD layout" once).
    with saving:
        temp = f"{path}.{threading.get_ident()}.part"
        with open(temp, "w", encoding="utf-8") as f:
            f.write(text)
        for attempt in range(12):  # (up to ~2.5 s)
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                time.sleep(0.03 * (attempt + 1))
        # Still held open by someone: write straight into it (never lose the save, never crash)
        os.remove(temp)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"({os.path.basename(path)} was busy, saved it directly)")

def save_profile():
    text = json.dumps(profile, indent=2)
    safe_write(PROFILE_FILE, text)
    safe_write(BACKUP_FILE, text)  # (a second good copy, in case the first is ever damaged)

profile = load_profile()

def tamil_mode():
    # True when the user asked M.I.N.D to talk in Tamil ("language" in profile.json)
    return profile.get("language", "english") == "tamil"
