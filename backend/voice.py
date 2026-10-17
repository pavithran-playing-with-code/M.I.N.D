# Voice: talks with the Windows voice, and goes quiet if you say "stop" or the wake word.
import unicodedata
import comtypes.client
from ears import open_mic, phrase_listener, hear, wake_word

SPEAK_ASYNC = 1  # start talking and return right away, so we can listen at the same time
PURGE = 2        # cancel whatever is being said
STOP_WORDS = ["stop", "quiet"]

windows_voice = comtypes.client.CreateObject("SAPI.SpVoice")

def speak(text):
    # Says the text out loud. Returns True if you interrupted it.
    text = unicodedata.normalize("NFKC", text)  # turn odd symbols (special spaces, dashes) into normal ones
    print("M.I.N.D:", text)
    if not text:
        return False
    words = STOP_WORDS + [wake_word()]
    rec = phrase_listener(words)
    stream = open_mic()
    windows_voice.Speak(text, SPEAK_ASYNC)
    try:
        while not windows_voice.WaitUntilDone(0):
            heard = hear(rec, stream)
            if any(w in heard for w in words):
                windows_voice.Speak("", SPEAK_ASYNC | PURGE)
                print("(Interrupted)")
                return True
        return False
    finally:
        stream.stop_stream()
        stream.close()
