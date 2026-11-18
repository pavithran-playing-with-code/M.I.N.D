# The laptop map ("Mind, show my laptop map"): what's using the RAM (the table you work on), the CPU (the
# heat) and the storage (the cupboard), live, for the HUD to draw. M.I.N.D's own parts are marked.
import os
import shutil
import threading
import time
import psutil

from memory import BASE_DIR

# Process names -> the name people know
NAMES = {"code": "VS Code", "chrome": "Chrome", "msedge": "Edge", "msedgewebview2": "Edge WebView (apps inside)",
         "memory compression": "Squeezed memory (Windows)", "svchost": "Windows services", "msmpeng": "Defender (antivirus)",
         "memcompression": "Squeezed memory (Windows)", "claude": "Claude app", "node": "Node.js", "mysql": "MySQL", "mysqld": "MySQL", "whatsapp.root": "WhatsApp", "explorer": "File Explorer",
         "searchhost": "Windows search", "onedrive": "OneDrive", "onedrive.sync.service": "OneDrive", "dwm": "Screen drawing (Windows)",
         "audiodg": "Sound (Windows)", "system": "Windows itself", "registry": "Windows itself", "docker desktop": "Docker"}

def friendly(p):
    # (name shown, is it M.I.N.D?)
    name = (p.info["name"] or "").lower().removesuffix(".exe")
    if name in ("python", "pythonw"):
        cmd = " ".join(p.info.get("cmdline") or [])
        if "main.py" in cmd:
            return "M.I.N.D brain", True
        if "offline_hearing" in cmd:
            return "M.I.N.D offline ears", True
    if name == "chrome" and "live_chrome" in " ".join(p.info.get("cmdline") or []):
        return "M.I.N.D voice (its Chrome)", True
    if name == "electron":
        return "M.I.N.D Jarvis mode", True
    return NAMES.get(name, name.title() or "Other"), False

# CPU is measured over time: a background sampler keeps the last reading for every process
cpu = {"apps": [], "at": 0.0, "running": False}

def sample_cpu():
    # Runs only while someone looks at the map (stops after a minute without asks)
    cores = psutil.cpu_count() or 1
    seen = {}
    while time.time() - cpu["at"] < 60:
        totals = {}
        for p in psutil.process_iter(["name", "cmdline"]):
            try:
                use = p.cpu_percent(None) / cores  # (% of the whole laptop)
            except psutil.Error:
                continue
            if p.pid in seen and p.pid != 0:  # (0 = "System Idle Process": the unused part, not an app)
                name, mind = friendly(p)
                totals.setdefault(name, [0.0, mind])[0] += use
            seen[p.pid] = True
        cpu["apps"] = sorted(({"name": n, "pct": round(v[0], 1), "mind": v[1]} for n, v in totals.items()
                              if v[0] >= 0.3), key=lambda a: -a["pct"])[:8]
        time.sleep(2)
    cpu["running"] = False

def ram():
    mem = psutil.virtual_memory()
    apps = {}
    for p in psutil.process_iter(["name", "cmdline", "memory_info"]):
        try:
            used = p.info["memory_info"].rss if p.info["memory_info"] else 0
        except psutil.Error:
            continue
        name, mind = friendly(p)
        apps.setdefault(name, [0, mind])[0] += used
    mb = 1024 * 1024
    listed = sorted(({"name": n, "mb": round(v[0] / mb), "mind": v[1]} for n, v in apps.items()), key=lambda a: -a["mb"])
    big = [a for a in listed if a["mb"] >= 120 or a["mind"]][:14]
    rest = (mem.total - mem.available) / mb - sum(a["mb"] for a in big)
    if rest > 50:
        big.append({"name": "Everything else", "mb": round(rest), "mind": False})
    return {"total": round(mem.total / mb), "free": round(mem.available / mb), "apps": big}

# Storage: a few big folders are measured in the background (it takes a while), once an hour
folders = {"parts": [], "at": 0.0, "busy": False}

def folder_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total

def measure_folders():
    home = os.path.expanduser("~")
    places = [("M.I.N.D", os.path.dirname(BASE_DIR), True)]
    places += [(n, os.path.join(home, n), False) for n in ("Downloads", "Desktop", "Documents", "Pictures", "Videos")]
    places += [("App data", os.path.join(home, "AppData"), False)]
    parts = []
    for name, path, mind in places:
        if os.path.isdir(path):
            parts.append({"name": name, "gb": round(folder_size(path) / 1024 ** 3, 1), "mind": mind})
    # (M.I.N.D lives inside Desktop: show Desktop without it, so nothing is counted twice)
    mind_gb = next((p["gb"] for p in parts if p["mind"]), 0)
    for p in parts:
        if p["name"] == "Desktop" and os.path.dirname(BASE_DIR).lower().startswith(os.path.join(home, "Desktop").lower()):
            p["gb"] = round(max(p["gb"] - mind_gb, 0), 1)
    folders.update(parts=parts, at=time.time(), busy=False)

def disk():
    total, used, free = shutil.disk_usage(os.path.splitdrive(BASE_DIR)[0] + "\\")
    if not folders["busy"] and time.time() - folders["at"] > 3600:
        folders["busy"] = True
        threading.Thread(target=measure_folders, daemon=True).start()
    gb = 1024 ** 3
    parts = [p for p in folders["parts"] if p["gb"] >= 0.1]
    known = sum(p["gb"] for p in parts)
    return {"total": round(total / gb, 1), "used": round(used / gb, 1), "free": round(free / gb, 1),
            "parts": parts + [{"name": "Windows, apps and the rest", "gb": round(max(used / gb - known, 0), 1), "mind": False}],
            "measuring": not folders["parts"]}

def snapshot():
    cpu["at"] = time.time()
    if not cpu["running"]:
        cpu["running"] = True
        threading.Thread(target=sample_cpu, daemon=True).start()
    return {"ram": ram(), "cpu": cpu["apps"], "cpu_total": round(psutil.cpu_percent(None)), "disk": disk()}

def show_laptop_map():
    # Tool: the map on the HUD, and a few words about it to say
    import showcase
    now = snapshot()
    showcase.put_on_hud({"kind": "sysmap", "title": "Laptop map"}, minutes=10)
    r = now["ram"]
    top = ", ".join(f"{a['name']} {a['mb']} MB" for a in r["apps"][:3])
    mind = sum(a["mb"] for a in r["apps"] if a["mind"])
    return (f"The laptop map is on the HUD (live). RAM: {r['total'] - r['free']} of {r['total']} MB used, "
            f"biggest: {top}; M.I.N.D uses {mind} MB. Storage: {now['disk']['free']} GB free of {now['disk']['total']} GB.")
