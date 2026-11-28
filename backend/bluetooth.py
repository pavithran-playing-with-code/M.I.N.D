# Battery of the Bluetooth devices connected to this laptop (earbuds, headphones, a mouse...).
# Windows already knows it for most of them (it's the number in Settings > Bluetooth & devices); this asks
# Windows' device list for that same number. No extra packages, nothing is sent anywhere.
# (The PowerShell way, Get-PnpDeviceProperty, took 95 seconds for the same answer: this takes well under a second.)
import ctypes
import re
from ctypes import wintypes

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)

class GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        parts = text.strip("{}").split("-")
        self.a, self.b, self.c = int(parts[0], 16), int(parts[1], 16), int(parts[2], 16)
        tail = bytes.fromhex(parts[3] + parts[4])
        for i, value in enumerate(tail):
            self.d[i] = value

class PropertyKey(ctypes.Structure):
    _fields_ = [("group", GUID), ("number", wintypes.ULONG)]

class DeviceInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("class_guid", GUID), ("instance", wintypes.DWORD),
                ("reserved", ctypes.c_void_p)]

def key(group, number):
    made = PropertyKey()
    made.group = GUID(group)
    made.number = number
    return made

BATTERY = key("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}", 2)     # percent, one byte
CONNECTED = key("{83DA6326-97A6-4088-9453-A1923F573B29}", 15)  # is it connected right now?
NAME = key("{A45C254E-DF1C-4EFD-8020-67D146A850E0}", 14)       # the name you see in Settings
BUS_NAME = key("{540B947E-8B40-45BC-A8A2-6A0B894CBDA2}", 4)    # the name the device itself gives

setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DeviceInfo)]
setupapi.SetupDiGetDevicePropertyW.argtypes = [ctypes.c_void_p, ctypes.POINTER(DeviceInfo), ctypes.POINTER(PropertyKey),
                                               ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p, wintypes.DWORD,
                                               ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

ALL_CLASSES, PRESENT = 0x4, 0x2
EXTRA = re.compile(r"\s+(Hands-Free( AG)?|Avrcp Transport|Stereo|A2DP.*|Headset|Audio)$", re.I)

def read(devices, device, which, size=512):
    # One detail of one device: (its bytes, how many), or None if the device doesn't have it
    kind, needed = wintypes.ULONG(), wintypes.DWORD()
    buffer = ctypes.create_string_buffer(size)
    if setupapi.SetupDiGetDevicePropertyW(devices, ctypes.byref(device), ctypes.byref(which), ctypes.byref(kind),
                                          buffer, size, ctypes.byref(needed), 0):
        return buffer.raw[:needed.value]
    return None

def words(raw):
    return raw.decode("utf-16-le", "ignore").rstrip("\x00") if raw else ""

def batteries():
    # {device name: percent} for every CONNECTED Bluetooth device that tells Windows its battery
    found = {}
    devices = setupapi.SetupDiGetClassDevsW(None, None, None, ALL_CLASSES | PRESENT)
    if not devices or devices == ctypes.c_void_p(-1).value:
        return found
    try:
        device = DeviceInfo()
        device.size = ctypes.sizeof(DeviceInfo)
        index = 0
        while setupapi.SetupDiEnumDeviceInfo(devices, index, ctypes.byref(device)):
            index += 1
            level = read(devices, device, BATTERY, 8)
            if not level:
                continue
            connected = read(devices, device, CONNECTED, 8)
            if connected is not None and connected[:1] == b"\x00":
                continue  # paired, but not connected now: its number is old
            name = words(read(devices, device, NAME)) or words(read(devices, device, BUS_NAME))
            name = EXTRA.sub("", name).strip()
            if name and 0 <= level[0] <= 100:
                found[name] = min(found.get(name, 100), level[0])  # (earbuds list twice: the lower one counts)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(devices)
    return found

def report():
    # For "how much charge do my earbuds have?"
    try:
        levels = batteries()
    except Exception as e:
        return f"Couldn't read the Bluetooth batteries ({str(e)[:60]})."
    if not levels:
        return ("No connected Bluetooth device is telling the laptop its battery right now (nothing connected, "
                "or that device doesn't report it).")
    return "Bluetooth: " + ", ".join(f"{name} {level}%" for name, level in levels.items()) + "."

if __name__ == "__main__":
    import time
    start = time.time()
    print(batteries(), f"({time.time() - start:.2f} s)")
