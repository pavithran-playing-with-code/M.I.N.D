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
    pc.py                <- PC control used by tools: type_text (SendInput unicode), press_keys, close_app (WM_CLOSE, never M.I.N.D's own parents or "Program Manager"), system_info (psutil), lock_pc, look_at_screen (Pillow screenshot -> Groq qwen vision)
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

**Models:** `brain.py` MODELS = `openai/gpt-oss-120b`, `openai/gpt-oss-20b` (both `reasoning_effort="low"`), then `qwen/qwen3.8-27b`. `max_retries=0` so a busy model fails over instantly. **Free limits: 8000 tokens/minute and 1000 requests/day per model**; one request is ~1.8K tokens (tool list ~8K chars), and a tool action needs 2 requests. On `RateLimitError` from every model, `ask_model` waits the shortest `retry-after` (if <=15s) and retries once, then says "I've hit my free thinking limit". `think()` skips repeated identical tool calls (qwen used to repeat them) and strips `<think>` tags. `qwen/qwen3.8-27b` is the only model here that accepts images (used by `look_at_screen`). Llama models returned 404 for this account. List available models (from `backend`):
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
- [x] **Music**: `play_youtube` scrapes the top `videoId` from the YouTube results page (no key, ~0.8s) and opens `watch?v=` so it autoplays; falls back to the search page. `media_control` presses media keys (play/pause, next, previous, stop). Tools in `ENDS_CONVERSATION` (play_youtube) end the conversation so the music isn't heard as speech
- [x] **PC control** (`pc.py`): type into the app in front, keyboard shortcuts, close apps, battery/CPU/RAM/disk/top memory apps, lock PC, look at the screen. Ask ChatGPT/Claude via `chatgpt.com/?q=` / `claude.ai/new?q=`. Timers use `set_reminder`
- [x] History stores tool results as "(Already done: ...)" so fillers like "oh" don't repeat actions; prompt says "stop/wait/not now/bye" = `end_conversation` (it once closed Notepad on "Stop"); `looks_broken()` drops glitchy replies (long runs of "…"); silence or noise in a conversation is ignored quietly (no "Sorry, I didn't catch that"), 2 in a row ends it
- [x] **Quick replies** (`tools.QUICK` + `quick_reply`): when every tool in a round is a simple action that worked (volume, media, play_youtube, reminders, notes, profile, keys, lock, open_url, type_text, end/shutdown), `think()` speaks a short fixed line ("Turning it up, Sir.") instead of a second brain call. Halves tokens; fixed lines hit the voice cache so they play instantly. Not used in Tamil mode. `system_info` only scans per-app memory when `include_apps` is true (was 2.4s)
- [x] **Tamil mode**: `profile["language"]` = "tamil"/"english" (`memory.tamil_mode()`), switched by voice via `update_profile(language)`. Whisper gets no language (auto: Tamil, English or a mix) plus a Tamil hint; offline backup uses multilingual `base`. Voice is `ta-IN-ValluvarNeural` (or `ta-IN-PallaviNeural`). The brain replies in spoken Tamil and calls the user சார். `main.PHRASES` has Tamil "Yes?", greeting and reminder. The HUD font falls back to Nirmala UI for Tamil letters. Wake word and "stop" stay English (Vosk is English only)
- [x] **Wake words**: `ears.wake_words()` = profile `wake_word` (must be 2+ Vosk-known words, else "hey mind") + "hey mind" + "hi mind". One-word wake words are refused in code and in `update_profile` (the brain once set it to "mind" when told "don't speak to me", and then "remind"/self-talk kept waking it)
- [x] **Sleep command** (`main.wants_sleep`, no brain): if every word is a stop word (stop, sleep, quiet, bye, enough, later, நிறுத்து, போதும்...) or a filler, M.I.N.D says "Going quiet" and waits for the wake word. "Stop the music" etc. still go to the brain
- [x] `cancel_reminder` tool (by words/time, or everything)
- [x] Jarvis-like personality prompt (short, warm, witty); knows current time/date
- [x] **Barge-in** (talk over M.I.N.D): `voice.speak()` reads the mic in 0.1s steps while playing. The echo level is learned during the first sentence (startup greeting) and slowly afterwards. Sound above max(1.5x speech threshold, 1.6x echo) for 0.3s pauses playback, records you (`ears.finish_recording`) and transcribes. If the text is mostly words from the current sentence (`is_echo`), it resumes and raises the echo level; otherwise it stops and puts the text in `state.heard`, which `main.next_input()` handles first. Tested: greeting then long answer with no false trigger (echo ~400, threshold ~640 at the owner's volume)
- [x] Interrupt: say "stop", "quiet" or the wake word while it talks
- [x] Empty brain reply -> "Sorry, I didn't catch that."
- [x] Errors handled: speech timeouts, bad internet, tool failures, unicode printing

## 8. Known issues
- Interrupt listens through the laptop mic while the speaker plays, so a reply containing "stop" could rarely cut itself off.
- Barge-in needs you to be clearly louder than the speaker echo; at high volume you may need to speak up (or use "stop"/orb click). Headphones make it perfect. If the volume is raised a lot mid-session, the first barge-in check may pause for ~1s, then it re-learns.
- Tamil mode: Tamil replies are a bit formal at times; the wake word and "stop" must still be said in English.
- Groq free tier: 8000 tokens/minute per model, so about 6 actions a minute across 3 models; faster use waits a few seconds. Shortening tool descriptions or history would stretch it.
- `type_text` types into whichever window is in front; a command typed in the HUD would type into the HUD's browser tab unless an app was just opened.
- The laptop often has <1 GB RAM free (Chrome is the biggest user).
- `open_app` short names like "VS Code" may not match "Visual Studio Code" directly (the brain retries with the suggested name).
- Only 8GB RAM: avoid heavy local models; close Chrome/Docker when testing.
- `localhost:5173` (npm run dev) shows OFFLINE unless `python main.py` is running; normal use is `localhost:8000`.

## 9. Roadmap (do in this order)
Done: HUD, Edge voice, music, PC control, quick replies, Tamil mode (see status).
1. **Fewer tokens:** shorter tool descriptions or sending only the tools likely needed, to fit more requests under the 8000 tokens/minute free limit.
2. **Faster feel:** stream the brain's reply and start making the first sentence's audio before the reply is finished; Tamil quick replies.
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
