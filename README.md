# M.I.N.D

A personal J.A.R.V.I.S.-style voice assistant for Windows. Say the wake word, talk normally, and it understands you and acts: opens apps and websites, checks the weather, sets reminders, takes notes, changes the volume, and remembers things about you.

Built with free tools only.

| Part | Tool |
|---|---|
| Wake word | Vosk (offline) |
| Speech to text | faster-whisper (offline) |
| Brain | Groq free API (GPT-OSS models) with tool calling |
| Voice | Windows built-in voice (SAPI) |
| HUD | React + Vite page served by a FastAPI backend |

## How it understands you
There are no hardcoded sentences. The brain gets a list of **tools** (in `backend/tools.py`) with plain-English descriptions, and decides by itself which ones to use. "Put on some music", "I wanna code" and "it's too loud" all work without special rules.

## Setup (Windows)
```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Put your free Groq key (https://console.groq.com/keys) in `backend/.env`.

Build the HUD once (from the project root): `npm install` then `npm run build`.

## Run
```
cd backend
venv\Scripts\activate
python main.py
```
The HUD opens at http://localhost:8000. Say **"hey mind"** (or click the orb), then talk, or type a command. Say **"stop"** or click the orb to interrupt it while it's speaking.

## Add a new skill
1. Write a function in `backend/tools.py` that returns a short text result.
2. Add it to `TOOLS` (with a clear description) and `FUNCTIONS`.

The brain will start using it on its own.
