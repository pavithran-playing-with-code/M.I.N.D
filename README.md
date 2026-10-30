# M.I.N.D

A personal J.A.R.V.I.S.-style voice assistant for Windows. Say "Mind", talk normally, and it understands you and acts: opens apps, projects and websites, plays music, reads your screen, sends WhatsApp messages, tells you when Claude/ChatGPT finish your prompts, searches the web, sets reminders, and remembers things about you. It also works from your phone through Telegram.

Built with free tools only.

| Part | Tool |
|---|---|
| Wake word | Vosk (offline), plus a voice lock so only your voice counts (sherpa-onnx) |
| Main brain | Gemini Live: hears and speaks in one go, with tool calling (free API key) |
| Backup brain | Groq Whisper (hearing) + Groq/Gemini text models + Microsoft Edge voices |
| HUD | Floating arc reactor on the desktop, and a React + Vite HUD served by FastAPI |
| Phone | Your own Telegram bot (optional) |
| Chrome extension | Optional helper in `extension/`: lets M.I.N.D see AI chats in hidden tabs |

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
Put your free keys in `backend/.env`: `GEMINI_API_KEY` (https://aistudio.google.com/apikey) and `GROQ_API_KEY` (https://console.groq.com/keys). `TELEGRAM_BOT_TOKEN` is optional (phone control).

Build the HUD once (from the project root): `npm install` then `npm run build`.

Optional: load the Chrome extension once per Chrome profile (`chrome://extensions` -> Developer mode -> Load unpacked -> the `extension` folder).

## Run
Double-click `backend/start_mind.bat`, or:
```
cd backend
venv\Scripts\activate
python main.py
```
- Taskbar on/off button: `python autostart.py button`, then Start -> type MIND -> right-click -> Pin to taskbar.
- Start with Windows: `python autostart.py on` (`off` to undo).

The floating reactor appears and it says "Mind online." Say **"Mind, ..."** (or click the reactor and type). Double-click the reactor to open the HUD. Say **"stop"** or click the reactor to interrupt it.

## Add a new skill
1. Write a function in `backend/tools.py` that returns a short text result.
2. Add it to `TOOLS` (with a clear description), `FUNCTIONS`, and a `TOOL_GROUPS` entry.
3. Run `venv\Scripts\python.exe self_test.py` from `backend`.

The brain will start using it on its own.
