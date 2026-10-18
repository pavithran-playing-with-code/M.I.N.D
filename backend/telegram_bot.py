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

HELP = ("Hey, it's M.I.N.D! Just talk to me like on the laptop, by text or voice note, "
        "e.g. \"is my laptop charging?\", \"play Rathinamo\", \"lock my PC\".\n"
        "/screen - a screenshot of the laptop\n/status - battery, memory and internet")

# ---------- Talking to Telegram ----------
def call(method, **params):
    data = json.dumps(params).encode()
    page = urllib.request.Request(API + method, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(page, timeout=40) as resp:
        return json.load(resp)["result"]

def send(chat, text):
    call("sendMessage", chat_id=chat, text=text[:4000])

def send_photo(chat, jpg, caption=""):
    # Photos must be sent as a file upload ("multipart" form)
    boundary = "mind" + str(random.randint(10**8, 10**9))
    body = io.BytesIO()
    for name, value in (("chat_id", str(chat)), ("caption", caption)):
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"screen.jpg\"\r\n"
               "Content-Type: image/jpeg\r\n\r\n".encode())
    body.write(jpg)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    page = urllib.request.Request(API + "sendPhoto", data=body.getvalue(),
                                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(page, timeout=60).read()

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

    if message.get("voice"):
        import ears
        text = ears.transcribe_ogg(download_voice(message["voice"]["file_id"]))
        if not text:
            send(chat, "Couldn't make out that voice note, try again?")
            return
    if not text:
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

    # Anything else: think about it just like on the laptop (actions happen on the laptop)
    import brain
    state.add_message("you", "📱 " + text)
    reply, action = brain.think(text)
    reply = reply or "Done."
    state.add_message("mind", "📱 " + reply)
    send(chat, reply)
    if action == "shutdown":
        import hud, taskbar
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

def start():
    global pair_code
    if not TOKEN:
        print("Phone control is off (no TELEGRAM_BOT_TOKEN in .env)")
        return
    if not profile.get("telegram_owner"):
        pair_code = str(random.randint(100000, 999999))
        print(f"Phone control: send {pair_code} to your Telegram bot to connect")
        state.add_message("mind", f"📱 To connect your phone, send this code to your Telegram bot: {pair_code}")
    threading.Thread(target=loop, daemon=True).start()
