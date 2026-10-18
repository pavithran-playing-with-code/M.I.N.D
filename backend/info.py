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
last_traffic = {"time": time.time(), "down": psutil.net_io_counters().bytes_recv,
                "up": psutil.net_io_counters().bytes_sent}

def traffic():
    # How much internet the laptop is using right now (Mbps), since the last check
    now, counters = time.time(), psutil.net_io_counters()
    seconds = max(now - last_traffic["time"], 0.5)
    used = {"down": round((counters.bytes_recv - last_traffic["down"]) * 8 / seconds / 1e6, 2),
            "up": round((counters.bytes_sent - last_traffic["up"]) * 8 / seconds / 1e6, 2)}
    last_traffic.update(time=now, down=counters.bytes_recv, up=counters.bytes_sent)
    return used

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
        label, hint = describe(down, ping)
        speed["result"] = {"ping": round(ping), "down": round(down, 1), "up": round(up, 1),
                           "label": label, "hint": hint, "time": time.strftime("%I:%M %p")}
        speed["error"] = None
        return speed["result"]
    except Exception as e:
        speed["error"] = "Test failed, the connection dropped. Try again."
        raise RuntimeError(f"speed test failed, the internet connection dropped ({e})")
    finally:
        link.close()
        speed["running"] = False

def describe(down, ping):
    # Speed in words, like "Partly cloudy" for weather
    if down >= 50:
        label, hint = "Very fast", "Great for 4K and big downloads"
    elif down >= 20:
        label, hint = "Fast", "Smooth HD video and calls"
    elif down >= 8:
        label, hint = "Good", "Fine for HD video and calls"
    elif down >= 3:
        label, hint = "Okay", "Fine for browsing and music"
    else:
        label, hint = "Slow", "Pages and videos may lag"
    if ping > 150:
        hint += ", but laggy for calls and games"
    return label, hint

# A real test uses about 10 MB, so it runs at startup and then every hour
# (change "speed_test_minutes" in profile.json)
def auto_speed_test(minutes):
    def loop():
        time.sleep(20)  # let M.I.N.D finish starting first
        while True:
            safe(speed_test)
            time.sleep(minutes * 60)
    threading.Thread(target=loop, daemon=True).start()

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
    return (f"Internet{where}: {r['label']} ({r['hint']}). Download {r['down']} Mbps, "
            f"upload {r['up']} Mbps, ping {r['ping']} ms.")

# ---------- Where you are (from Windows, so the HUD never has to ask) ----------
WINDOWS_LOCATION = """
Add-Type -AssemblyName System.Device
$w = New-Object System.Device.Location.GeoCoordinateWatcher
[void]$w.TryStart($false, [TimeSpan]::FromSeconds(10))
for ($i = 0; $i -lt 40 -and ($w.Status -ne 'Ready' -or $w.Position.Location.IsUnknown); $i++) { Start-Sleep -Milliseconds 250 }
$l = $w.Position.Location
if (-not $l.IsUnknown) { '{0},{1},{2}' -f $l.Latitude, $l.Longitude, $l.HorizontalAccuracy }
"""

def place_name(lat, lon, accuracy):
    # Turn coordinates into a name (free, no key). Rough locations get the city, not a suburb.
    import json, urllib.request
    url = ("https://api.bigdatacloud.net/data/reverse-geocode-client"
           f"?latitude={lat}&longitude={lon}&localityLanguage=en")
    page = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    found = json.load(urllib.request.urlopen(page, timeout=10))
    if accuracy > 5000:
        return found.get("city") or found.get("principalSubdivision") or ""
    return found.get("locality") or found.get("city") or ""

def windows_location():
    # Asks Windows' location service (no popup). Updates state.location unless the HUD
    # already sent a more precise one from the browser.
    import state
    out = subprocess.run(["powershell", "-NoProfile", "-Command", WINDOWS_LOCATION], capture_output=True,
                         text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
    if not out:
        return
    lat, lon, accuracy = (float(x) for x in out.split(","))
    current = state.location
    if current and current.get("accuracy", 99999) < accuracy:
        return  # the browser's location is better
    state.location = {"lat": lat, "lon": lon, "accuracy": accuracy, "name": place_name(lat, lon, accuracy)}

def auto_location(minutes=30):
    def loop():
        while True:
            safe(windows_location)
            time.sleep(minutes * 60)
    threading.Thread(target=loop, daemon=True).start()

def snapshot():
    import state
    import limits
    return {"system": system(), "wifi": wifi(), "speed": speed, "using": traffic(), "location": state.location,
            "limits": limits.snapshot()}
