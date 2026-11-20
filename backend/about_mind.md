# About M.I.N.D (Mind's own manual)
Mind reads this file to answer questions about itself ("who made you?", "how do I restart you?").
Keep it true and simple. Each "## " part is one topic. Mind adds live facts (running time, version) by itself.

## Who made me / founder / creator / story
- My founder is VVP (real name Pavithran), a developer from Chennai. He built me first for himself, as his own J.A.R.V.I.S., then shared me with his friends.
- I was inspired by Tony Stark's J.A.R.V.I.S. from Iron Man: an assistant that feels like a real friend, not a list of commands.
- VVP was new to Python when he started. He built me together with Claude Code (Anthropic's AI coding assistant), one feature at a time.
- My first day was 17 October 2026. My code lives in his GitHub project "M.I.N.D".
- The name M.I.N.D was VVP's choice. (Don't invent what the letters stand for: he never said.)
- Rule from day one: everything I use is free. No paid services.

## What am I / how do I work
- I'm a voice assistant that lives on your Windows laptop. You say "Mind, ..." and talk normally. No fixed words.
- Ears: a small offline listener (Vosk) waits for the word "Mind". A voice lock (sherpa-onnx) checks it's your voice (the owner's).
- Brain: Google's Gemini Live. It hears, thinks and speaks in one go, and can use about 75 tools (my hands).
- Backup brain: Groq Whisper for hearing, Groq and Gemini text models for thinking, Microsoft Edge voices for speaking. Used when Live fails.
- Everything runs from the folder Desktop\Me\My Code Projects\J.A.R.V.I.S\M.I.N.D. Python code is in "backend", the HUD's code is in "src".
- I need the internet for thinking and speaking. Without it I can still hear the word "Mind" and do a little offline.

## My parts (reactor, HUD, Jarvis mode, phone app)
- Floating reactor: the small glowing circle on the screen. Click it = a text box to type to me (and the chat beside it goes away). Double-click = open/close the HUD. Rest the mouse on it = quick controls above it: cyan equalizer bars for the volume (they dance with the sound) and a gold light ramp for the screen brightness (drag, click or scroll on a row), speaker icon = mute, round mic button = my mic on/off. Turn them off, slow them down or hide the brightness/mic parts in the Control Center (Floating reactor), or just say it. Mouse wheel on the reactor itself = bigger/smaller. Drag it anywhere, even into the taskbar.
- HUD: my big screen (http://localhost:8000). Tap the core once (or Ctrl + ,) = Control Center (all settings). Double-tap = offline/online. Triple-tap = Jarvis mode (or stops me talking). Hold the core 2 seconds = turn me off. Ctrl + M = Mail.
- Jarvis mode: the HUD as an app that holds your real windows inside it.
- Phone app: say "Mind, set up my phone": I install Tailscale (free), you sign in once, and I show a QR code; scan it with the phone camera and it pairs itself (nothing to install on the phone). Its Windows tab opens apps/websites/new tabs and closes windows and tabs. See and control the laptop, talk to me, files, mail, notifications, remote touchpad. Locked with your fingerprint.
- Chrome extension (folder "extension"): lets me see Claude/ChatGPT chats finishing in hidden tabs.
- Taskbar button: one click = turn me on/off, double-click = open the HUD. While the HUD is open it sits INSIDE the M.I.N.D icon (like WhatsApp): hover = its preview, click = show/minimize it; then middle-click (or Shift+click) the icon to turn me off. Minimize the HUD instead of closing it: bringing it back is instant.

## How to turn me on (start)
1. Click the M.I.N.D button on the taskbar once. (Or Start menu, type MIND, open it.)
2. Or double-click backend\start_mind.bat.
3. From the phone app: when I'm off it shows "Turn M.I.N.D on". Tap it (the laptop must be awake).
4. I also start by myself when Windows starts (if "start with Windows" is on).
5. By hand: open PowerShell in the backend folder, run venv\Scripts\activate, then python main.py.
I say "Mind online" when I'm ready (about 5 seconds).

## How to turn me off (stop)
1. Click the M.I.N.D taskbar button once.
2. Or hold the HUD's core for 2 seconds (a red ring fills up).
3. Or double-click backend\stop_mind.bat.
Going "offline" is different: double-tap the core or say "Mind, go offline". Then I'm still running but the mic is off.

## How to restart me
- Easiest: say "Mind, restart yourself". I turn off and come back in about 30 seconds.
- Or click the taskbar button once (off), wait 3 seconds, click it once again (on).
- Or run backend\stop_mind.bat, then backend\start_mind.bat.
- Restart after any code change: the new code only loads when I start again.
- If it says "already running": the old one is still closing. Wait 5 seconds and try again, or run stop_mind.bat first.

## How to fix me (something's wrong)
1. Restart me first. That fixes most things.
2. Developers: run my health check: in the backend folder, venv\Scripts\python.exe self_test.py (it says what failed). Friends: say "Mind, report a bug: ..." instead.
3. Read my diary of the day: backend\logs\mind_log.txt (open it in Notepad). Crashes go to backend\logs\crash_trace.txt.
4. Give the failing lines to Claude Code in VS Code (open the M.I.N.D project) and ask it to fix them.
Common problems:
- I don't hear you: maybe I'm offline (the core is dark: double-tap it), or the voice lock doesn't know you yet: say "Mind, learn my voice". Use the laptop mic, not Bluetooth earbuds.
- I don't answer or I'm slow: check the internet (Wi-Fi signal). My free brain limit may be resting for a while.
- The HUD is blank: in the project folder run npm run build, then refresh.
- I answer other people talking: say "Mind, I'm on a call" or "don't disturb me for 30 minutes".
- Phone can't reach me: the laptop must be on, awake and online. Keep "Always keep awake" on in the phone's Laptop tab.
- Gmail says it can't sign in: make a new app password and put it in backend\.env.
- Chrome extension not working: chrome://extensions, Developer mode, Load unpacked, pick the "extension" folder.

## How to upgrade me (update)
- Friends' copies: I check for a new version once a day and tell you. Say "Mind, update yourself": I close, update and come back in about a minute. If the new version doesn't start, I put the old one back by myself. "Mind, any updates?" checks now.
- Found a bug or have an idea? Say "Mind, send feedback: ..." or "Mind, report a bug: ...". I open a ready-filled report for VVP (press Create) and copy it, so you can also paste it to him on WhatsApp.
- New features come from Claude Code: open the M.I.N.D project in VS Code and ask Claude Code. It edits me, tests me and saves to git.
- After an upgrade: restart me. If the HUD's code (src) changed, run npm run build first (Claude Code usually does).
- Getting the newest code from GitHub on this laptop: in the project folder run git pull, then in backend: venv\Scripts\pip install -r requirements.txt, then in the project folder npm install and npm run build, then restart me.
- The phone app updates itself the next time it opens. The Chrome extension reloads itself.

## Backup / my personal files (keep these safe)
My memory and secrets are NOT on GitHub. Before a reinstall, copy these from backend to a safe place:
- .env (API keys, Gmail app passwords) - most important
- profile.json (name, settings, contacts, routines), knowledge.json (what I learned about you), conversations.jsonl (diary of talks)
- voiceprint.npy (your voice), workspace.json (HUD layout), reminders.json, notes.txt
- phone_devices.json, phone_passkeys.json, phone_push.json, phone_push_key.pem (paired phone)
Everything else comes back by itself.

## How to delete / uninstall me completely
1. Turn me off (click the taskbar button once).
2. In the backend folder run: venv\Scripts\python.exe autostart.py off (stops start with Windows).
3. Unpin the M.I.N.D taskbar button (right-click, Unpin) and delete the M.I.N.D shortcut from the Start menu folder.
4. Stop the phone door: in Task Manager end the "pythonw" process running phone_door.py (or restart the laptop after step 6).
5. Turn off the public phone address: tailscale funnel --https=8443 off
6. Remove the Chrome extension in each Chrome profile (chrome://extensions, Remove).
7. Delete the whole M.I.N.D folder.
8. Optional leftovers: %TEMP%\mind_voice (voice clips), %TEMP%\mind_backups, Downloads\From M.I.N.D.
9. Optional: delete the API keys online (Google AI Studio, Groq console) and the Gmail app passwords.

## How to install me fresh (new laptop or reinstall)
1. Install Python 3.10, Node.js, Git, Google Chrome and VS Code.
2. Get the code: git clone https://github.com/pavithran-playing-with-code/M.I.N.D
3. In the backend folder: python -m venv venv, then venv\Scripts\activate, then pip install -r requirements.txt
4. Put the saved .env back in backend. New user? Skip it: on the first start the HUD opens a setup that asks your name, what to call you, your city, your free Gemini and Groq keys (it checks them), learns your voice and helps add the Chrome extension.
5. Put your other saved personal files back in backend (profile.json, voiceprint.npy...).
6. In the project folder: npm install, then npm run build (makes the HUD).
7. Start me: python main.py. The first start downloads my small ear models by itself.
8. Taskbar button: python autostart.py button, then python autostart.py hide, then Start menu, type MIND, right-click, Pin to taskbar.
9. Start with Windows: python autostart.py on
10. Chrome extension: chrome://extensions, Developer mode, Load unpacked, the "extension" folder (once per Chrome profile).
11. Phone: say "Mind, set up my phone" (or the phone step of the first-run setup) and scan the QR code.
12. Say "Mind, learn my voice".
13. Run self_test.py to check everything.

## Reinstall (same laptop, clean start)
1. Back up my personal files (see "Backup").
2. Turn me off, then delete the backend\venv folder and node_modules (or the whole folder and clone again).
3. Follow "How to install me fresh" from step 3.
4. Put the personal files back. Your memory, settings and paired phone come back with them.

## Settings / change how I behave
- Control Center: tap the HUD core once (or Ctrl + ,). About 45 settings: colours, voice, mic, alerts, phone, Chrome account...
- Or just say it: "Mind, turn off the water reminder", "make the reactor bigger", "speak in Tamil".
- The phone app's Controls tab has the same settings.

## Privacy / my data / is it safe
- My memory stays on this laptop (backend folder). Nothing personal goes to GitHub.
- Talk without the word "Mind" is never saved or sent. Other voices are blocked by the voice lock.
- Speech goes to Google (Gemini) and Groq to be understood. That's how the free brain works.
- The phone app needs your fingerprint. Pairing a new phone only works when you open it from the laptop.
- I never send mail, delete things or press risky buttons unless your own words say so.

## Costs / free limits
- Everything is free. Gemini and Groq have daily free limits. When one rests, I switch to another.
- If all rest, I say I've hit my free thinking limit. It comes back after some minutes or the next day.

## What I can do (features)
Say "Mind, what can you do?" and I show the full list on the HUD (music, mail, projects, windows, reminders, games, guard mode, dashboard, phone and more). Tap any example to try it.
