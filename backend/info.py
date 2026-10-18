# Info: live facts for the HUD's side panel and for the brain:
# battery/CPU/RAM, Wi-Fi name and signal, and a real internet speed test (Cloudflare, free).
import os
import re
import time
import threading
import subprocess
import http.client
import psutil

# ---------- PC ----------
def system():
    battery = psutil.sensors_battery()
    return {
        "battery": round(battery.percent) if battery else None,
        "charging": bool(battery and battery.power_plugged),
        "cpu": round(psutil.cpu_percent(interval=None)),
        "ram": round(psutil.virtual_memory().percent),
    }

# ---------- Wi-Fi (asks Windows; saved for 10 seconds so it isn't asked too often) ----------
wifi_cache = {"time": 0, "data": None}

def wifi():
    if time.time() - wifi_cache["time"] < 10:
        return wifi_cache["data"]
    data = None
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True,
                             timeout=5, creationflags=subprocess.CREATE_NO_WINDOW).stdout
        name = re.search(r"^\s+SSID\s+:\s(.+)$", out, re.M)
        signal = re.search(r"^\s+Signal\s+:\s(\d+)%", out, re.M)
        if name:
            data = {"name": name.group(1).strip(), "signal": int(signal.group(1)) if signal else None}
    except Exception as e:
        print("Wi-Fi check failed:", e)
    wifi_cache.update(time=time.time(), data=data)
    return data

# ---------- Internet speed test ----------
HOST = "speed.cloudflare.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}
speed = {"running": False, "result": None, "error": None}  # last result, shown in the HUD

class Link:
    # One connection to the speed test server that reconnects if the internet drops a request
    def __init__(self):
        self.conn = None

    def timed(self, method, path, body=None):
        # Time one request; returns (seconds, bytes received). Tries twice.
        for attempt in range(2):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPSConnection(HOST, timeout=20)
                start = time.time()
                self.conn.request(method, path, body=body, headers=HEADERS)
                received = len(self.conn.getresponse().read())
                return time.time() - start, received
            except (OSError, http.client.HTTPException):
                self.close()
                if attempt == 1:
                    raise

    def close(self):
        if self.conn:
            self.conn.close()
        self.conn = None

def speed_test():
    # Ping, download and upload, like speedtest.net. Takes about 10 seconds and ~15 MB of data.
    speed["running"] = True
    link = Link()
    try:
        link.timed("GET", "/__down?bytes=0")  # open the connection first
        ping = min(link.timed("GET", "/__down?bytes=0")[0] for _ in range(5)) * 1000
        # Small download to guess the speed, then a bigger one that takes about 4 seconds
        took, got = link.timed("GET", "/__down?bytes=1000000")
        size = int(min(max(got / took * 4, 2_000_000), 50_000_000))
        took, got = link.timed("GET", f"/__down?bytes={size}")
        down = got * 8 / took / 1e6
        body = os.urandom(1_000_000)
        took, _ = link.timed("POST", "/__up", body)
        up = len(body) * 8 / took / 1e6
        speed["result"] = {"ping": round(ping), "down": round(down, 1), "up": round(up, 1),
                           "time": time.strftime("%I:%M %p")}
        speed["error"] = None
        return speed["result"]
    except Exception as e:
        speed["error"] = "Test failed, the connection dropped. Try again."
        raise RuntimeError(f"speed test failed, the internet connection dropped ({e})")
    finally:
        link.close()
        speed["running"] = False

def start_speed_test():
    # Runs in the background (for the HUD button)
    if not speed["running"]:
        threading.Thread(target=lambda: safe(speed_test), daemon=True).start()

def safe(job):
    try:
        job()
    except Exception as e:
        print("Speed test failed:", e)

def internet_speed():
    # Tool for the brain: "how fast is my internet?"
    r = speed_test()
    net = wifi()
    where = f" on Wi-Fi '{net['name']}' ({net['signal']}% signal)" if net else ""
    return f"Internet{where}: download {r['down']} Mbps, upload {r['up']} Mbps, ping {r['ping']} ms."

def snapshot():
    return {"system": system(), "wifi": wifi(), "speed": speed}
