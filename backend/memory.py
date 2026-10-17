# Memory: everything M.I.N.D knows about you lives in profile.json, not in code.
# Keys: name, real_name, city, wake_word, facts, corrections, shortcuts
import os
import json
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # the backend folder
PROFILE_FILE = os.path.join(BASE_DIR, "profile.json")
load_dotenv(os.path.join(BASE_DIR, ".env"))  # loads GROQ_API_KEY for ears and brain

def load_profile():
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_profile():
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

profile = load_profile()

def tamil_mode():
    # True when the user asked M.I.N.D to talk in Tamil ("language" in profile.json)
    return profile.get("language", "english") == "tamil"
