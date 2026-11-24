# Downloads the models M.I.N.D needs before its first start (the installer runs this): the wake word model
# (Vosk, ~40 MB) and the voice fingerprint model (~25 MB). Run again any time: finished downloads are kept.
import sys

def main():
    from vosk import Model, SetLogLevel
    SetLogLevel(-1)
    Model(lang="en-us")
    print("Wake word model ready.")
    import speaker
    speaker.get_extractor()
    print("Voice model ready.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Download failed:", e)
        sys.exit(1)
