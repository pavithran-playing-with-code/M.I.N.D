# Which apps are making sound right now (the Windows volume mixer, read with comtypes)
# Used to know when a quietly opened song has really started playing.
import ctypes
from ctypes import POINTER, c_float, c_int, c_void_p, c_wchar_p, HRESULT
from ctypes.wintypes import DWORD
import comtypes
import psutil
from comtypes import GUID, IUnknown, COMMETHOD, CLSCTX_ALL

class IAudioMeterInformation(IUnknown):
    _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
    _methods_ = [COMMETHOD([], HRESULT, "GetPeakValue", (["out"], POINTER(c_float), "peak"))]

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

def playing_apps():
    # Names of apps that are making sound right now, e.g. {"chrome.exe"}
    comtypes.CoInitialize()
    devices = comtypes.CoCreateInstance(SPEAKERS, IMMDeviceEnumerator, CLSCTX_ALL)
    speaker = devices.GetDefaultAudioEndpoint(0, 1)  # 0 = output, 1 = multimedia
    manager = speaker.Activate(ctypes.byref(IAudioSessionManager2._iid_), CLSCTX_ALL, None).QueryInterface(IAudioSessionManager2)
    sessions = manager.GetSessionEnumerator()
    names = set()
    for i in range(sessions.GetCount()):
        session = sessions.GetSession(i)
        if session.GetState() != 1:  # 1 = active
            continue
        if session.QueryInterface(IAudioMeterInformation).GetPeakValue() < 0.005:
            continue
        try:
            names.add(psutil.Process(session.QueryInterface(IAudioSessionControl2).GetProcessId()).name().lower())
        except Exception:
            pass
    return names

def chrome_playing():
    try:
        return "chrome.exe" in playing_apps()
    except Exception:
        return False
