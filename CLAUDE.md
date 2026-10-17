# M.I.N.D: Project Guide for Claude

Read this file first. It holds the full context of the project so work can continue in any session, account, or tool (Claude.ai, Claude Code in VS Code).

Repo: https://github.com/pavithran-playing-with-code/M.I.N.D (branch `main`)

## 1. What this project is
M.I.N.D is a personal Jarvis-style voice AI assistant (inspired by Tony Stark's J.A.R.V.I.S.), built by the owner who goes by **VVP** (real name Pavithran). It listens to speech, thinks with an LLM, answers by voice, and acts on the computer. Goal: feel like a real, open-minded assistant that understands natural speech, not a list of hardcoded commands.

## 2. About the owner (important)
- **New to Python.** Explain simply, avoid jargon, one step at a time.
- When sharing code in chat (Claude.ai), give the **full file**, never partial snippets. In Claude Code, edit the files directly and say what changed.
- Prefers **short, direct answers** and a friendly tone, like a friend.
- Wants everything **free**. No paid services.
- Should be called **VVP**.

## 3. Environment
- OS: Windows 11, terminal is PowerShell (VS Code) or cmd
- Laptop: ASUS VivoBook, Intel i5-1035G1 (4 cores), **8GB RAM** (often low free RAM), no dedicated GPU
- Python 3.10.1 (other versions also installed; the venv uses 3.10.1)
- Node.js 22 installed
- Project root: `...\J.A.R.V.I.S\M.I.N.D\`

## 4. Folder structure
```
M.I.N.D/                 <- project root (this CLAUDE.md lives here)
  CLAUDE.md, README.md
  backend/               <- Python brain
    main.py              <- start here: startup + wake word / conversation loop
    memory.py            <- loads/saves profile.json
    ears.py              <- wake word (Vosk) + speech to text (faster-whisper)
    voice.py             <- speaks with Windows SAPI; "stop" or wake word interrupts
    brain.py             <- Groq LLM, personality prompt, history, tool-calling loop
    tools.py             <- every action M.I.N.D can do + TOOLS list the brain reads
    requirements.txt
    .env.example         <- copy to .env
    .env                 <- GROQ_API_KEY=... (SECRET, git-ignored)
    profile.json         <- auto-created, personal (git-ignored)
    notes.txt, reminders.json  <- auto-created, personal (git-ignored)
    venv/                <- Python virtual environment (git-ignored)
  src/, public/, ...     <- React + Vite frontend (default template, not connected yet)
```

## 5. Tech stack (all free)
| Part | Tool |
|---|---|
| Wake word | `vosk` small en-us model (offline) |
| Speech to text | `faster-whisper` base, CPU, int8 (offline); mic capture via `SpeechRecognition` + `pyaudio` |
| Brain (LLM) | **Groq free API** via `groq` package, with **tool calling** |
| Text to speech | Windows SAPI via `comtypes` (async, so it can be interrupted) |
| Config | `python-dotenv` (.env file) |
| UI (later) | React + Vite |

**How understanding works:** no regex commands. `brain.think()` sends the user's words plus `TOOLS` (descriptions in `tools.py`) to the LLM. The LLM picks tools, `run_tool()` runs them, results go back, and the LLM writes the spoken reply (up to 5 rounds). Time/date, name, city, remembered facts, shortcuts and reminders are put in the system prompt each turn.

**Models:** `brain.py` MODELS = `openai/gpt-oss-120b` then `openai/gpt-oss-20b` (both with `reasoning_effort="low"`), `max_retries=0` so a busy model fails over instantly. `qwen/qwen3.8-27b` was tested and left out because it repeated tool calls. Llama models returned 404 for this account. List available models (from `backend`):
```
python -c "from dotenv import load_dotenv; load_dotenv('.env'); from groq import Groq; [print(m.id) for m in Groq().models.list().data]"
```

## 6. How to run
Backend (from the `backend` folder):
```
venv\Scripts\activate
python main.py
```
If PowerShell blocks activate: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Install packages (inside the venv): `pip install -r requirements.txt`

Frontend (from the project root, separate terminal): `npm run dev` (http://localhost:5173/)

## 7. Current status (done)
- [x] Vite + React frontend created (default template, not yet connected)
- [x] Code split into small files (see section 4)
- [x] Wake word "hey mind" (set by `wake_word` in `profile.json`), then a conversation until silence twice, "that's all", or "shut down"
- [x] Offline hearing; name, city, corrections and shortcut names are fed to Whisper as a hint
- [x] **Tool calling**: natural speech understood, no hardcoded phrases. Tools: `open_url` (sites, Google/YouTube searches), `open_app` (any Start menu app via `Get-StartApps`, fuzzy match, suggests similar apps), `get_weather` (Open-Meteo, now + today + tomorrow), `change_volume` (up/down/mute/set), `set_reminder` (saved to `reminders.json`, survives restarts), `save_note`/`read_notes`, `update_profile`, `remember_fact`/`forget_fact` (long-term memory), `add_correction`, `add_shortcut`, `end_conversation`, `shut_down`
- [x] Jarvis-like personality prompt (short, warm, witty); knows current time/date
- [x] Interrupt: say "stop", "quiet" or the wake word while it talks
- [x] Empty brain reply -> "Sorry, I didn't catch that."
- [x] Errors handled: speech timeouts, bad internet, tool failures, unicode printing

## 8. Known issues
- Interrupt listens through the laptop mic while the speaker plays, so a reply containing "stop" could rarely cut itself off.
- Groq free tier has per-minute token limits; many fast requests can fall back to the 20b model or fail.
- "Open chatgpt and type ..." isn't possible yet (no typing tool).
- `open_app` short names like "VS Code" may not match "Visual Studio Code" directly (the brain retries with the suggested name).
- Only 8GB RAM: avoid heavy local models; close Chrome/Docker when testing.

## 9. Roadmap (do in this order)
1. **Connect UI (next):** FastAPI + uvicorn server inside the backend on port 8000 (new `backend/server.py`). The React page polls `/api/state` and becomes a Jarvis-style HUD: dark, glowing orb that reacts to waiting/listening/thinking/speaking, chat log, typed commands, click the orb to wake. Vite proxies `/api` to the backend.
2. **Better voice:** `edge-tts` for a more natural voice (keep interrupt support).
3. **More tools:** type text into apps, media play/pause/next, close apps, system info (battery, time on PC).
4. **Optional:** offline backup brain with Ollama using a small model (1B to 3B), package as a desktop app (Electron/Tauri).

## 10. Rules for Claude working on this project
- Free tools only. Ask before suggesting anything paid.
- Keep the code beginner-friendly with short comments.
- New abilities = new tools in `tools.py` (function + `TOOLS` entry + `FUNCTIONS` entry). Don't add regex command matching.
- Say exactly which folder and command to run.
- Change one thing at a time and tell the owner what to test.
- Never ask for or print the API key. Keep it only in `backend/.env`. Never commit `.env`, `profile.json`, `notes.txt`, `reminders.json`.
- If the owner pastes an error, explain the cause in one or two lines, then give the fix.
- Verify current library/model names before relying on memory, since they change.
- Read the current files before editing; edit them rather than rewriting from memory.
