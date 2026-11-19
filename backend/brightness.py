# The laptop screen's brightness (the same setting as Windows' brightness slider), through WMI.
# Only built-in laptop screens can do this; an external monitor answers None.
def wmi():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.GetObject("winmgmts://./root/WMI")

def get():
    # 0-100, or None when this screen can't change brightness
    try:
        for screen in wmi().InstancesOf("WmiMonitorBrightness"):
            return int(screen.CurrentBrightness)
    except Exception:
        return None
    return None

def set(percent):
    try:
        for screen in wmi().InstancesOf("WmiMonitorBrightnessMethods"):
            # (named values: calling WmiSetBrightness(1, x) directly gave "Invalid parameter" and nothing changed)
            values = screen.Methods_("WmiSetBrightness").InParameters.SpawnInstance_()
            values.Properties_.Item("Timeout").Value = 1
            values.Properties_.Item("Brightness").Value = max(0, min(100, int(percent)))
            screen.ExecMethod_("WmiSetBrightness", values)
            return True
    except Exception:
        return False
    return False
