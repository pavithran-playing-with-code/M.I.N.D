# Phone control: talk to M.I.N.D from anywhere through your own free Telegram bot.
# Setup: make a bot with @BotFather in Telegram, put its token in backend/.env as
# TELEGRAM_BOT_TOKEN=..., start M.I.N.D, and send the 6-digit code it shows to your bot.
# Only that one phone (chat) can control M.I.N.D; everyone else is ignored.
import io
import os
import json
import time
import random
import threading
import urllib.request
import state
from memory import profile, save_profile

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}/"
pair_code = None  # the secret code shown on the HUD until your phone is connected
OLD_MESSAGE_SECONDS = 120  # messages older than this were sent while M.I.N.D was off

HELP = ("Hey, it's M.I.N.D! Talk to me like on the laptop: text, or a voice note (I answer with one too). "
        "e.g. \"is my laptop charging?\", \"play Rathinamo\", \"send me the PDF I downloaded today\".\n"
        "Send a photo and ask about it. Share a link and I'll open it on the laptop.\n"
        "/screen - a screenshot of the laptop\n/status - battery, memory and internet")

# ---------- Talking to Telegram ----------
def call(method, **params):
    data = json.dumps(params).encode()
    page = urllib.request.Request(API + method, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(page, timeout=40) as resp:
        return json.load(resp)["result"]

def send(chat, text):
    call("sendMessage", chat_id=chat, text=text[:4000])

def upload(method, chat, field, data, filename, kind, caption=""):
    # Photos, voice notes and files must be sent as a file upload ("multipart" form)
    boundary = "mind" + str(random.randint(10**8, 10**9))
    body = io.BytesIO()
    for name, value in (("chat_id", str(chat)), ("caption", caption)):
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
               f"Content-Type: {kind}\r\n\r\n".encode())
    body.write(data)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    page = urllib.request.Request(API + method, data=body.getvalue(),
                                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(page, timeout=120).read()

def send_photo(chat, jpg, caption=""):
    upload("sendPhoto", chat, "photo", jpg, "screen.jpg", "image/jpeg", caption)

def send_voice(chat, sound):
    # M.I.N.D's live voice (24 kHz sound) as a Telegram voice note
    import ears
    upload("sendVoice", chat, "voice", ears.to_ogg(sound, 24000), "mind.ogg", "audio/ogg")

FILE_LIMIT = 49 * 1024 * 1024  # Telegram bots can send files up to 50 MB

def send_file_to_phone(which):
    # Tool: "send me the PDF I downloaded today" (a number or name from find_files)
    import pc
    if not connected():
        return "The phone isn't connected yet (Telegram setup)."
    path, problem = pc.pick_file(which)
    if problem:
        return problem
    if os.path.getsize(path) > FILE_LIMIT:
        return f"{os.path.basename(path)} is too big for Telegram (over 50 MB)."
    with open(path, "rb") as f:
        upload("sendDocument", profile["telegram_owner"], "document", f.read(), os.path.basename(path),
               "application/octet-stream")
    return f"Sent {os.path.basename(path)} to your phone."

def ears_sound(voice_note):
    # The voice note as the live brain hears it (16 kHz sound), or b"" if there isn't one
    if not voice_note:
        return b""
    import ears
    try:
        return ears.from_ogg(voice_note, 16000)
    except Exception as e:
        print("Couldn't read the voice note:", str(e)[:100])
        return b""

def download_voice(file_id):
    path = call("getFile", file_id=file_id)["file_path"]
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=30) as resp:
        return resp.read()

def screenshot():
    from PIL import ImageGrab
    shot = ImageGrab.grab()
    shot.thumbnail((1600, 1600))
    buffer = io.BytesIO()
    shot.convert("RGB").save(buffer, "JPEG", quality=80)
    return buffer.getvalue()

# ---------- For the rest of M.I.N.D ----------
def connected():
    return bool(TOKEN and profile.get("telegram_owner"))

def notify(text):
    # Send a message to your phone (alerts, reminders...), if it's connected
    if connected():
        try:
            send(profile["telegram_owner"], text)
        except Exception as e:
            print("Couldn't message your phone:", e)

def send_to_phone(text):
    # Tool: "Mind, send this to my phone: ..."
    if not connected():
        return "The phone isn't connected yet (Telegram setup)."
    send(profile["telegram_owner"], text)
    return "Sent to your phone."

def send_screenshot():
    # Tool: "Mind, send a screenshot to my phone"
    if not connected():
        return "The phone isn't connected yet (Telegram setup)."
    send_photo(profile["telegram_owner"], screenshot(), "Your screen right now")
    return "Screenshot sent to your phone."

# ---------- Messages from your phone ----------
def handle(message):
    chat = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    owner = profile.get("telegram_owner")

    if not owner:
        # Not connected yet: only the secret code from the HUD connects a phone
        if pair_code and text == pair_code:
            profile["telegram_owner"] = chat
            save_profile()
            state.add_message("tool", "Phone connected to M.I.N.D (Telegram)")
            send(chat, "Connected! 🦾 " + HELP)
        else:
            send(chat, "Send me the 6-digit code shown on M.I.N.D's screen to connect.")
        return
    if chat != owner:
        return  # someone else: ignore them completely
    if time.time() - message.get("date", time.time()) > OLD_MESSAGE_SECONDS:
        # Sent while the laptop's M.I.N.D was off: Telegram kept it, but doing it now could surprise you
        # (an old "lock my PC" would lock the laptop the moment M.I.N.D starts)
        send(chat, f"My laptop was off when you sent \"{(text or 'that voice note')[:60]}\". Ask me again?")
        return

    voice_note = b""
    if message.get("voice"):
        voice_note = download_voice(message["voice"]["file_id"])
    if message.get("photo"):
        # A photo ("what's this?"): the reading model looks at it, the brain talks about what it shows
        import live_brain
        picture = download_voice(message["photo"][-1]["file_id"])  # (the biggest size)
        question = (message.get("caption") or "").strip()
        seen = live_brain.read_picture(picture, "a photo they sent from their phone", question or "What is this?")
        text = (f"(They sent a photo{': ' + question if question else ''}. What it shows: {seen}) "
                + (question or "What's this?"))
    if not text and not voice_note:
        return
    if text in ("/start", "/help"):
        send(chat, HELP)
        return
    if text == "/screen":
        send_photo(chat, screenshot(), "Your screen right now")
        return
    if text == "/status":
        import info
        pc, net = info.system(), info.speed.get("result")
        status = (f"Battery {pc['battery']}% ({'charging' if pc['charging'] else 'on battery'}), "
                  f"CPU {pc['cpu']}%, memory {pc['ram']}%.")
        if net:
            status += f"\nInternet: {net['label']}, {net['down']} Mbps (tested {net['time']})."
        send(chat, status)
        return

    # Anything else: the same live brain as on the laptop (actions happen on the laptop). A voice note
    # gets a voice note back in M.I.N.D's voice. The old brain only answers if Live can't.
    import live_brain
    answered = live_brain.phone_turn(text, ears_sound(voice_note)) if profile.get("live", True) else None
    if answered and answered[1]:
        heard, reply, voice = answered
        shown = ("(photo) " + (message.get("caption") or "")) if message.get("photo") else heard
        state.add_message("you", "📱 " + shown)
        state.add_message("mind", "📱 " + reply)
        if voice_note and voice:
            try:
                send_voice(chat, voice)
            except Exception as e:
                print("Couldn't send the voice note:", str(e)[:100])
        send(chat, reply)
        return
    if voice_note:
        import ears
        text = ears.transcribe_ogg(voice_note)
        if not text:
            send(chat, "Couldn't make out that voice note, try again?")
            return
    import brain
    state.add_message("you", "📱 " + text)
    reply, action = brain.think(text)
    reply = reply or "Hmm, I didn't manage that one. Can you say it another way?"
    state.add_message("mind", "📱 " + reply)
    send(chat, reply)
    if action == "shutdown":
        import hud, taskbar
        say_off()
        taskbar.show(False)
        hud.close_hud()
        os._exit(0)

def loop():
    offset = None
    while True:
        try:
            # Waits up to 30 seconds for new messages ("long polling": no server needed)
            for update in call("getUpdates", timeout=30, offset=offset, allowed_updates=["message"]):
                offset = update["update_id"] + 1
                if "message" in update:
                    try:
                        handle(update["message"])
                    except Exception as e:
                        print("Telegram message failed:", e)
        except Exception as e:
            print("Telegram connection problem:", str(e)[:100])
            time.sleep(5)

# ---------- On / off status for the phone ----------
# The bot's profile (tap its name in Telegram) shows "🟢 On · last check 9:42 PM", refreshed every
# 10 minutes. If that time is old, the laptop is off, asleep, or has no internet.
def show_status(text):
    try:
        call("setMyShortDescription", short_description=text[:120])
    except Exception as e:
        print("Couldn't update the bot's status:", str(e)[:80])

def heartbeat():
    while True:
        show_status(f"🟢 M.I.N.D is on · last check {time.strftime('%I:%M %p, %d %b')}")
        time.sleep(600)

def say_off():
    # Called when M.I.N.D is turned off properly (taskbar button, power button, "shut down")
    if TOKEN:
        show_status(f"🔴 M.I.N.D is off since {time.strftime('%I:%M %p, %d %b')}")
        notify("🔴 M.I.N.D is turning off. I can't do anything from your phone until it's on again.")

def start():
    global pair_code
    if not TOKEN:
        print("Phone control is off (no TELEGRAM_BOT_TOKEN in .env)")
        return
    threading.Thread(target=heartbeat, daemon=True).start()
    # In the background: a slow connection used to hold up M.I.N.D's start
    threading.Thread(target=notify, args=("🟢 M.I.N.D is on and ready (your laptop is on).",), daemon=True).start()
    if not profile.get("telegram_owner"):
        pair_code = str(random.randint(100000, 999999))
        print(f"Phone control: send {pair_code} to your Telegram bot to connect")
        state.add_message("mind", f"📱 To connect your phone, send this code to your Telegram bot: {pair_code}")
    threading.Thread(target=loop, daemon=True).start()
