# Voice: talks with the Windows voice, and goes quiet if you say "stop",
# say the wake word, or click the orb in the HUD.
import re
import unicodedata
import comtypes.client
from ears import open_mic, close_mic, phrase_listener, hear, wake_word
import state

SPEAK_ASYNC = 1  # start talking and return right away, so we can listen at the same time
PURGE = 2        # cancel whatever is being said
STOP_WORDS = ["stop", "quiet"]

windows_voice = comtypes.client.CreateObject("SAPI.SpVoice")

def speak(text):
    # Says the text out loud. Returns True if you interrupted it.
    text = unicodedata.normalize("NFKC", text)  # turn odd symbols (special spaces, dashes) into normal ones
    text = re.sub(r"([a-z]{2}[.!?])(?=[A-Z])", r"\1 ", text)  # "done.Anything" -> "done. Anything"
    print("M.I.N.D:", text)
    if not text:
        return False
    state.add_message("mind", text)
    state.set_status("speaking")
    said = re.sub(r"M\.I\.N\.D\.?", "Mind", text)  # say "Mind", not "M I N D"
    words = STOP_WORDS + [wake_word()]
    rec = phrase_listener(words)
    stream = open_mic()
    state.take_click()  # forget old clicks
    windows_voice.Speak(said, SPEAK_ASYNC)
    try:
        while not windows_voice.WaitUntilDone(0):
            heard = hear(rec, stream)
            if state.take_click() or any(w in heard for w in words):
                windows_voice.Speak("", SPEAK_ASYNC | PURGE)
                print("(Interrupted)")
                return True
        return False
    finally:
        state.set_level(0)
        close_mic(stream)
