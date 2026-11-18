# M.I.N.D

Your own J.A.R.V.I.S.-style voice assistant for Windows. Say **"Mind"**, talk normally, and it understands you and acts: opens apps, projects and websites, plays music, reads your screen, sends WhatsApp messages, tells you when Claude/ChatGPT finish your prompts, searches the web, sets reminders, guards your laptop, shows a life dashboard, and remembers things about you. It also has its own phone app (see and control the laptop, talk to Mind, files, notifications).

Made by VVP. **Everything is free.**

## Install (5 steps)
You need: a Windows 10/11 laptop with a mic, and a Google account.

1. Click the green **Code** button above, then **Download ZIP**.
2. Unzip it somewhere you'll keep it (for example `Documents\M.I.N.D`).
3. Open the folder and double-click **`install.bat`**.
   It installs everything it needs by itself (about 10-15 minutes the first time). If Windows asks to allow changes, click **Yes**. If Windows says "Windows protected your PC", click **More info**, then **Run anyway**.
4. M.I.N.D starts and its **setup screen** opens: your name, two free keys (it shows you exactly where to click), and your voice.
5. Pin it: Start menu, type **MIND**, right-click it, **Pin to taskbar**.

Then just say **"Hey Mind"**, or "Mind, what can you do?"

**Phone app (optional):** say **"Mind, set up my phone"** and scan the QR code with your phone's camera. Nothing to install on the phone.

## Use it
- **Talk:** "Mind, play some lofi", "Mind, open WhatsApp", "Mind, remind me to call Mom at 5".
- **Type:** click the glowing reactor on the screen.
- **HUD:** double-click the reactor. Tap the core once for all settings.
- **Taskbar button:** one click = on/off, double-click = HUD.
- **Something wrong?** "Mind, how do I fix you?" or "Mind, restart yourself".

## Found a bug or have an idea?
Open an **Issue** on this page (the Issues tab) and say what happened.

## Privacy
Your memory, keys and settings stay on your laptop. Talk without the word "Mind" is never saved or sent. Speech goes to Google (Gemini) and Groq to be understood; that's how the free brain works. Each person uses their own free keys.

---

### For developers
| Part | Tool |
|---|---|
| Wake word | Vosk (offline), plus a voice lock so only your voice counts (sherpa-onnx) |
| Main brain | Gemini Live: hears and speaks in one go, with tool calling (free API key) |
| Backup brain | Groq Whisper (hearing) + Groq/Gemini text models + Microsoft Edge voices |
| HUD | Floating arc reactor on the desktop, and a React + Vite HUD served by FastAPI |
| Phone | M.I.N.D phone app (`backend/phone.html`), reached through Tailscale Funnel |
| Chrome extension | Optional helper in `extension/`: lets M.I.N.D see AI chats in hidden tabs |

There are no hardcoded sentences. The brain gets a list of **tools** (in `backend/tools.py`) with plain-English descriptions and decides by itself which ones to use.

Add a skill: write a function in `backend/tools.py` that returns a short text result, add it to `TOOLS`, `FUNCTIONS` and a `TOOL_GROUPS` entry, then run `venv\Scripts\python.exe self_test.py` from `backend`.
