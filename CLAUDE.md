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
    ears.py              <- wake word (Vosk) + speech to text (Groq Whisper, local faster-whisper backup)
    voice.py             <- speaks with edge-tts (SAPI backup); "stop", wake word or orb click interrupts
    brain.py             <- Groq LLM, personality prompt, history, tool-calling loop
    tools.py             <- every action M.I.N.D can do + TOOLS list the brain reads
    state.py             <- shared status/mic level/chat log/typed commands/orb clicks for the HUD
    server.py            <- FastAPI on 127.0.0.1:8000 (background thread): /api/state, /api/command, /api/orb; serves ../dist
    requirements.txt
    .env.example         <- copy to .env
    .env                 <- GROQ_API_KEY=... (SECRET, git-ignored)
    profile.json         <- auto-created, personal (git-ignored)
    notes.txt, reminders.json  <- auto-created, personal (git-ignored)
    venv/                <- Python virtual environment (git-ignored)
  src/                   <- React HUD: App.jsx (polls /api/state every 200ms), components/Orb.jsx, ChatLog.jsx, CommandBar.jsx, App.css
  dist/                  <- built HUD (npm run build), served by the backend; git-ignored
```

## 5. Tech stack (all free)
| Part | Tool |
|---|---|
| Wake word | `vosk` small en-us model (offline) |
| Speech to text | **Groq Whisper** `whisper-large-v3`, then `-turbo` (free, ~0.4s, accurate). Offline backup: `faster-whisper` base.en, loaded only if the cloud fails. Own recorder in `ears.record()` (pyaudio, 0.1s steps, threshold = max(2x room noise, 60), 0.6s pause ends speech, <0.3s of loud sound is ignored as a click). Ghost "Thank you"-type segments are dropped using `no_speech_prob`/`avg_logprob` |
| HUD | React + Vite, FastAPI + uvicorn backend server |
| Brain (LLM) | **Groq free API** via `groq` package, with **tool calling** |
| Text to speech | **`edge-tts`** (free, internet), default voice `en-GB-RyanNeural`, set by `voice` in `profile.json` (the brain can change it via `update_profile`). Text is split into sentences, made in a background thread, and played with Windows MCI (`winmm`, no install), so the first sentence starts after ~0.8s. Clips are cached in `%TEMP%\mind_voice` (cached ones start in ~0.05s; deleted after 30 days). Edge pads ~1s of silence at the end, so playback stops at the last WordBoundary + 0.25s. Offline backup: Windows SAPI via `comtypes` |
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

The HUD opens by itself at http://localhost:8000 (served from `dist/`). After changing anything in `src/`, rebuild from the project root: `npm run build`.

Install packages (inside the venv): `pip install -r requirements.txt`

Live-editing the HUD: keep `python main.py` running, and run `npm run dev` from the project root (http://localhost:5173/, proxies `/api` to port 8000).

## 7. Current status (done)
- [x] **Jarvis HUD**: dark grid page with a ring orb (cyan waiting/listening, amber thinking, pulsing speaking, grey offline); the core grows with mic level; chat log shows you / M.I.N.D / tool results; type commands; click the orb to wake it or to stop it talking. Works on narrow screens too
- [x] Code split into small files (see section 4)
- [x] Wake word "hey mind" (set by `wake_word` in `profile.json`), then a conversation until silence twice, "that's all", or "shut down"
- [x] Hearing via Groq Whisper (tested: 0.35-0.75s vs 1.6s for local base, and spells "Pavithran" right). A natural-sentence hint with real name, city, corrections and shortcuts is sent as the prompt. (The dotted "M.I.N.D" in the old hint made Whisper write things like "A.M.D", so the hint says "Mind".)
- [x] Speaks "Mind" instead of spelling M.I.N.D; glued sentences ("done.Next") get a space
- [x] Prompt forbids inventing facts about the user and acting on nonsense; prints timing (heard in / thought in)
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
- `localhost:5173` (npm run dev) shows OFFLINE unless `python main.py` is running; normal use is `localhost:8000`.

## 9. Roadmap (do in this order)
Done: HUD, Edge voice (see status).
1. **More tools (next):** type text into apps, media play/pause/next, close apps, system info (battery, time on PC).
2. **Faster feel:** stream the brain's reply and start making the first sentence's audio before the reply is finished.
3. **Optional:** offline backup brain with Ollama using a small model (1B to 3B), package as a desktop app (Electron/Tauri).

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
