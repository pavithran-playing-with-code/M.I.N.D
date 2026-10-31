# Which apps are making sound right now (the Windows volume mixer, read with comtypes)
# Used to know when a quietly opened song has really started playing.
import ctypes
from ctypes import POINTER, c_float, c_int, c_void_p, c_wchar_p, HRESULT
from ctypes.wintypes import DWORD
import comtypes
import psutil
import live_window
from comtypes import GUID, IUnknown, COMMETHOD, CLSCTX_ALL

class IAudioMeterInformation(IUnknown):
    _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
    _methods_ = [COMMETHOD([], HRESULT, "GetPeakValue", (["out"], POINTER(c_float), "peak"))]

class ISimpleAudioVolume(IUnknown):
    _iid_ = GUID("{87CE5498-68D6-44E5-9215-6DA47EF883D8}")
    _methods_ = [COMMETHOD([], HRESULT, "SetMasterVolume", (["in"], c_float), (["in"], c_void_p)),
                 COMMETHOD([], HRESULT, "GetMasterVolume", (["out"], POINTER(c_float)))]

class IAudioSessionControl(IUnknown):
    _iid_ = GUID("{F4B1A599-7266-4319-A8C1-E70ACB11E8CD}")
    _methods_ = [COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(c_int)))]

class IAudioSessionControl2(IAudioSessionControl):
    _iid_ = GUID("{bfb7ff88-7239-4fc9-8fa2-07c950be9c6d}")
    # (methods we don't use still need a place, so the order matches Windows)
    _methods_ = [COMMETHOD([], HRESULT, name) for name in (
        "GetDisplayName", "SetDisplayName", "GetIconPath", "SetIconPath", "GetGroupingParam",
        "SetGroupingParam", "RegisterAudioSessionNotification", "UnregisterAudioSessionNotification")] + [
        COMMETHOD([], HRESULT, "GetSessionIdentifier", (["out"], POINTER(c_wchar_p))),
        COMMETHOD([], HRESULT, "GetSessionInstanceIdentifier", (["out"], POINTER(c_wchar_p))),
        COMMETHOD([], HRESULT, "GetProcessId", (["out"], POINTER(DWORD)))]

class IAudioSessionEnumerator(IUnknown):
    _iid_ = GUID("{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}")
    _methods_ = [COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_int))),
                 COMMETHOD([], HRESULT, "GetSession", (["in"], c_int), (["out"], POINTER(POINTER(IAudioSessionControl))))]

class IAudioSessionManager2(IUnknown):
    _iid_ = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
    _methods_ = [COMMETHOD([], HRESULT, "GetAudioSessionControl"), COMMETHOD([], HRESULT, "GetSimpleAudioVolume"),
                 COMMETHOD([], HRESULT, "GetSessionEnumerator", (["out"], POINTER(POINTER(IAudioSessionEnumerator))))]

class IMMDevice(IUnknown):
    _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
    _methods_ = [COMMETHOD([], HRESULT, "Activate", (["in"], POINTER(GUID), "iid"), (["in"], DWORD, "ctx"),
                           (["in"], c_void_p, "params"), (["out"], POINTER(POINTER(IUnknown)), "obj"))]

class IMMDeviceEnumerator(IUnknown):
    _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    _methods_ = [COMMETHOD([], HRESULT, "EnumAudioEndpoints", (["in"], DWORD), (["in"], DWORD), (["out"], POINTER(c_void_p))),
                 COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint", (["in"], DWORD, "flow"), (["in"], DWORD, "role"),
                           (["out"], POINTER(POINTER(IMMDevice)), "dev"))]

SPEAKERS = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")

def sessions():
    # Every app's sound session on the speakers: (session, its id, app name, making sound now?)
    comtypes.CoInitialize()
    devices = comtypes.CoCreateInstance(SPEAKERS, IMMDeviceEnumerator, CLSCTX_ALL)
    speaker = devices.GetDefaultAudioEndpoint(0, 1)  # 0 = output, 1 = multimedia
    manager = speaker.Activate(ctypes.byref(IAudioSessionManager2._iid_), CLSCTX_ALL, None).QueryInterface(IAudioSessionManager2)
    found = manager.GetSessionEnumerator()
    for i in range(found.GetCount()):
        session = found.GetSession(i)
        try:
            control = session.QueryInterface(IAudioSessionControl2)
            pid = control.GetProcessId()
            name = psutil.Process(pid).name().lower() if pid else ""
            if name == "chrome.exe" and live_window.FOLDER in " ".join(psutil.Process(pid).cmdline()):
                name = "mind-live"  # M.I.N.D Live's own voice (its hidden Chrome), not music
            key = control.GetSessionInstanceIdentifier()  # one app can have several sessions
        except Exception:
            continue
        sounding = session.GetState() == 1 and session.QueryInterface(IAudioMeterInformation).GetPeakValue() >= 0.005
        yield session, key, name, sounding

def playing_apps():
    # Names of apps that are making sound right now, e.g. {"chrome.exe"}
    return {name for _, _, name, sounding in sessions() if sounding and name}

def chrome_playing():
    try:
        return "chrome.exe" in playing_apps()
    except Exception:
        return False

NOT_MUSIC = ("python", "mind-live", "audiodg")  # M.I.N.D's own voices, and Windows' sound engine (system sounds)

def is_music(name):
    return bool(name) and not name.startswith(NOT_MUSIC)

def music_playing():
    # Is any other app (YouTube in Chrome, Spotify...) making sound?
    try:
        return any(is_music(name) for name in playing_apps())
    except Exception:
        return False

# ---------- Turning the music down while you talk to M.I.N.D ----------
DUCK_TO = 0.25        # other apps play at 25 % of their volume while you talk
DUCK_MAX_SECONDS = 60  # safety: never stays turned down longer than this
ducked = {}           # session id -> its volume before
duck_timer = None

def duck():
    # Turns down every app that's making sound (not M.I.N.D itself), so Whisper hears you
    global duck_timer
    import settings
    if not settings.on("duck_music"):
        return
    try:
        for session, key, name, sounding in sessions():
            if sounding and key not in ducked and is_music(name):
                volume = session.QueryInterface(ISimpleAudioVolume)
                ducked[key] = volume.GetMasterVolume()
                volume.SetMasterVolume(ducked[key] * DUCK_TO, None)
    except Exception as e:
        print("Couldn't turn the music down:", e)
    if ducked and not duck_timer:
        import threading
        duck_timer = threading.Timer(DUCK_MAX_SECONDS, unduck)
        duck_timer.daemon = True
        duck_timer.start()

def unduck():
    # Puts the music back to how loud it was (Windows remembers app volumes, so this must always run)
    global duck_timer
    if duck_timer:
        duck_timer.cancel()
        duck_timer = None
    if not ducked:
        return
    try:
        for session, key, name, sounding in sessions():
            if key in ducked:
                session.QueryInterface(ISimpleAudioVolume).SetMasterVolume(ducked[key], None)
    except Exception as e:
        print("Couldn't turn the music back up:", e)
    ducked.clear()
