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
- [x] Wake word "hey mind" (set by `wake_word` in `profile.json`); see the "Mind must be said" item below
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
- [x] **Speak Tamil any time (no mode needed)**: Whisper auto-detects the language (retries with en/ta if it guesses another one); Tamil speech comes back in Tamil script. If the user's text has Tamil letters, the prompt asks for a Tamil reply and quick replies are skipped. `voice.voice_for()` picks the voice **per sentence**: Tamil letters -> ta-IN voice, else the English voice. "Say something in Tamil" in English is answered in Tamil script
- [x] Safety: `type_text` only runs if the user's words include type/write/enter/fill/paste/jot/எழுது/டைப் (it once typed a reply into a random window); "(Already done: ...)" notes are stripped from replies; prompt says "don't remember that" = `forget_fact`
- [x] Note: an old M.I.N.D still running keeps its own copy of the profile and writes it back on save (it reset the wake word to "mind"); always close the old one before starting the new one
- [x] **Friend personality** (owner asked for "like an actual person or friend"): casual, warm, funny, contractions, name only now and then, no "Certainly/Understood"; casual Chennai Tamil; quick replies and `main.PHRASES` are casual with a few random variants ("Yeah?", "Got it.", "Here's X, enjoy!")
- [x] Voice timing: HUD text appears when the voice starts; the first sentence is cut at its first comma ("Yeah," / "Oh nice," get cached and start instantly); all pieces are made in parallel on one shared asyncio loop (`edge_loop`) with a 6s limit, then fall back to the Windows voice; everyday lines are pre-made at startup (`voice.warm_up`). Measured: Edge itself takes 0.5-2s per request depending on the network (the main remaining delay)
- [x] **HUD info panel** (`src/components/InfoPanel.jsx`, left column; medium screens put the cards in a row above the orb): Weather (browser geolocation -> BigDataCloud reverse geocode for the place name -> Open-Meteo forecast + air quality, refresh 10 min, retry 30s on failure; falls back to profile city marked "approx."), Internet (Wi-Fi name/signal from `netsh`, automatic Cloudflare speed test), Laptop (battery/CPU/RAM bars, amber when high). Backend `info.py` + `/api/info`, `/api/speedtest`, `/api/location` (the browser's location is also used by `get_weather` when no city is given). New `internet_speed` tool. `get_weather` now gives feels-like, humidity, wind, rain chance
- [x] **Main voice: Groq Orpheus `orpheus-austin`** (owner's choice on 2026-10-18 after hearing Edge/Orpheus/Piper; Piper was rejected and uninstalled). `profile.json`: `"voice": "orpheus-austin"`, `"edge_voice": "en-US-AndrewNeural"`. Free limit is **100 requests/day** (+1200 tokens/min), so: first sentence alone, the rest in one request (max 2 per reply); clips cached in `%TEMP%\mind_voice` (cached lines use no requests); `warm_up` is skipped for Orpheus; on `RateLimitError` it pauses Orpheus for `retry-after` and uses the Edge voice. Orpheus returns a streaming wav with a bogus length, so it's re-saved with a correct header and the speech end is found from the samples. ~0.9s for one sentence, ~3s for a long reply. Tamil sentences always use Edge `ta-IN-ValluvarNeural`. Samples in `backend/voices/samples/`
- [x] Internet card is automatic: `info.auto_speed_test()` runs 20s after start and every `speed_test_minutes` (default 60; ~10 MB each), labels the result like weather (`describe()`: Very fast / Fast / Good / Okay / Slow + a hint), and shows live usage from `psutil.net_io_counters` ("Using right now")
- [x] **Proactive alerts** (`alerts.py`, checked every 60s; rain every 15 min). Tested with fake battery/internet/memory and a fake rain forecast
- [x] **Morning briefing** (`daily_briefing` tool: weather, today's reminders, laptop, internet, 3 headlines; up to 4 spoken sentences) and **news** (`get_news`, Google News RSS for India, optional topic, titles cut to 120 chars)
- [x] **Chat memory across restarts**: `brain.history` saved to `backend/history.json` (last 20 messages, git-ignored)
- [x] Robustness: `tools.fetch()` retries web requests once (the owner's connection often drops requests); `run_tool` ignores arguments a tool doesn't have; the HUD location's place name is saved as `profile["city"]` if no city is set
- [x] **Starts with Windows** (turned ON on 2026-10-18 with the owner's OK): `backend/autostart.py on|off` puts/removes `M.I.N.D.lnk` (venv python + main.py, minimized) in the Startup folder (`shell:startup`). `backend/start_mind.bat` = double-click launcher (pauses only on error), `backend/stop_mind.bat` = stops whatever listens on port 8000. **Taskbar button** (owner keeps the Desktop empty and uses the taskbar): `python autostart.py button` puts `M.I.N.D.lnk` in the Start menu (target `cmd.exe /c toggle_mind.bat`, so it can be pinned; orb icon `backend/icons/mind.ico`, git-ignored). `toggle_mind.bat` (CRLF line endings, needed for goto) starts M.I.N.D if port 8000 is free, otherwise stops it and says "Mind is off" via SAPI. Windows doesn't allow programs to pin to the taskbar, so the owner pins it: Start -> type MIND -> right-click -> Pin to taskbar. `main.py` exits early if port 8000 already answers (opens the HUD instead) and waits up to 60s for internet at boot
- [x] **Hearing fixes (2026-10-18 afternoon)**: (1) the old sentence hint ("I'm Pavithran. I live in X.") was being repeated by Whisper on music/noise, creating fake commands ("I live in Kishore" -> saved city, fake facts/shortcuts). Hint is now "Pavithran talking to Mind." + a word list (never "I live in..."), and `copied_hint()` drops transcripts that are >=70% hint words (3+ words). (2) **English and Tamil at the same time**: `transcribe_cloud` runs `language="en"` and `language="ta"` in parallel and keeps the higher duration-weighted `avg_logprob` (tested: Tamil, English, and mixed like "Volume கொஞ்சம் குறை" all right); below `MIN_CONFIDENCE` -0.8 = noise -> "". (3) Audio is sent as **Opus/ogg via PyAV** (~10x smaller: 193 KB -> 16 KB; 5.6s -> 0.9s on the owner's ~1 Mbps upload). Whisper client timeout 8s
- [x] **Not meant for me**: `stay_silent` tool (prompt: talking to others, lyrics, TV, half sentences); `think()` returns "" and main stays quiet (counts as a miss; 2 misses end the conversation). Bracket tags like "[speech]" are stripped from replies. Prompt: don't change saved details from passing remarks
- [x] **Browser tabs**: `close_tab(name)` brings each browser window to the front, walks its tabs with ctrl+tab reading the window title, closes matching ones with ctrl+w, never the HUD ("M.I.N.D" title), stops after a full loop. `press_keys` refuses ctrl+w/alt+f4 while the HUD is in front (it once closed the HUD on "close the YouTube tab")
- [x] **Folders/projects**: `open_folder(name, open_with=vscode|explorer)`; `pc.folders` is indexed in the background (Desktop, Documents, Downloads, source, projects; depth 6; skips node_modules/venv...); ranking: exact name ("mind" = "M.I.N.D") > has .git/package.json/main.py/CLAUDE.md > shorter path; opens with `%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe`
- [x] **Taskbar icon shows on/off** (`taskbar.py`): swaps the pinned shortcut's icon (`icons/mind_on.ico` glowing cyan / `mind_off.ico` grey) and calls `SHChangeNotify(SHCNE_ASSOCCHANGED)`; tested, the pinned icon really changes. `main.py` sets on at start and off via `atexit`; `toggle_mind.bat`/`stop_mind.bat` set off after killing
- [x] **Faster thinking**: tool descriptions and the personality prompt were rewritten short (request 2,747 -> ~1,600 tokens, so ~5 requests/min per model instead of 2); `MAX_HISTORY` 12; rate-limit wait capped at 8s. `text()`/`number()` omit empty descriptions
- [x] **Cancel a slow thought**: `main.think_or_cancel()` runs `think()` in a thread while listening for "stop"/wake word and orb taps; cancelling sets `brain.cancelled` so no tool runs afterwards, then says "Okay, never mind"
- [x] **Offline mode (double-tap the orb)**: `state.muted` via `/api/mute`; mic off, reminders/alerts wait, conversation ends; HUD shows a powered-down red orb and "Offline" (amber dot); single tap still wakes/stops/cancels (Orb.jsx waits 300 ms to tell taps apart)
- [x] **One M.I.N.D only, even on a double-click** (the owner double-clicked the taskbar button and got two): `main.py` grabs a Windows named mutex `MIND_voice_assistant` and writes `backend/mind.pid` (git-ignored) as its very first step; a second copy exits (opens the HUD only if port 8000 answers). `toggle_mind.bat` decides from `mind.pid` (process alive = on), ignores clicks within 15 s of starting, and stops with `taskkill /T /F`. Tested: double-click -> one M.I.N.D; one click -> off. Note: the venv `python.exe` is a launcher, so one M.I.N.D shows as 2 python processes
- [x] **HUD power button** (top bar, asks to confirm) -> `/api/power_off` (icon grey, pid removed, `os._exit`). `open_url` description tells the brain its HUD is http://localhost:8000 (so "open your HUD" works after closing the tab)
- [x] **"Mind" must be said (owner's rule, 2026-10-18)**: the open conversation mode is gone. `ears.wait_for_wake()` listens for "hey mind"/"hi mind"/"mind" (Vosk), keeps the last 2 s and records until you pause, so "Mind, play a song" works in one breath. `main.command_from()` transcribes and requires `CALLED` (`(hey|hi|ok...)? mind` or மைண்ட்) in the text, else it's ignored without any brain call ("remind me" doesn't count). Only "hey mind" -> "Yeah?" -> one command. Typed HUD commands and talk-over (barge-in) text don't need "mind". `respond()` handles one turn; `stay_silent` is now rarely needed. Mic is more sensitive (threshold max(1.5x noise p90, 45), `MIN_CONFIDENCE` -1.0). While speaking, stop words that appear in its own sentence are ignored (it said "hey mind" in its greeting)
- [x] **Runs with no window**: started with `venv\Scripts\pythonw.exe` (toggle, start_mind.bat, autostart); output goes to `backend/mind.log` (git-ignored). With no console window, a taskbar click runs the toggle again instead of just showing the window (the owner's click opened the console instead of turning it off). Tested on -> off -> on
- [x] **HUD is its own app window** (`hud.py`): Chrome `--app=http://localhost:8000` (no tabs/address bar), found by exact window title "M.I.N.D" + class `Chrome_WidgetWin*` (a normal tab is "M.I.N.D - Google Chrome", VS Code never matches). `open_hud()` reuses an open window (each start used to add a new tab: 5 piled up); `close_hud()` sends WM_CLOSE and runs on every "off" path (`taskbar.py off` from the toggle/stop scripts, `atexit`, HUD power button). A page can't close its own tab in Chrome (`window.close()` was blocked), which is why this is done from Python. `open_hud` tool for "open your HUD". Tested: on -> 1 window, off -> 0, on -> 1
- [x] **No location popup ever** (the owner kept getting "localhost wants to know your location"): the HUD only uses browser geolocation if `navigator.permissions` already says "granted" (silent); otherwise it uses `info.location` from Windows (`info.windows_location()`: PowerShell `System.Device.Location.GeoCoordinateWatcher`, no popup, ~8 s, refreshed every 30 min by `info.auto_location()`; on this laptop it's ~50 km accurate (IP-based), named via BigDataCloud: city for rough fixes, locality for precise ones; shown as "(approx.)" when > 5 km). A more precise browser fix (POST /api/location with `accuracy`) wins. `/api/info` includes `location`
- [x] **Routines** (`tools.py`): `DEFAULT_ROUTINES` work mode (open M.I.N.D project, lofi, volume 30), good night (stop media, volume 20, lock), movie time (volume 70, YouTube); the user's own in `profile["routines"]` (None = deleted, also hides a built-in). Tools `run_routine` (runs steps directly with `run_tool`, no brain calls), `save_routine(name, steps=[{tool, args}])` ("when I say X, do A and B"; refuses run/save/delete_routine, shut_down, end_conversation), `delete_routine`. All routine names are listed in the system prompt. `stay_silent` was removed: with the "mind" rule everything reaching the brain is meant for it (it once went silent on "study mode")
- [x] **Free limits card** (HUD, `limits.py`): brain/hearing/voice calls use `with_raw_response` and record `x-ratelimit-remaining-requests`/`-limit-requests`; long `retry-after` (>60 s, i.e. the daily token limit) shows "Resting till HH:MM". Note: Groq doesn't send the daily *token* allowance in headers, so requests-left can look fine while a model rests
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
