# Hearing with no internet, as its own small program. Inside M.I.N.D this library crashed the whole app (it clashes
# with another library's copy of a Windows file), so ears.py starts this only when it's needed: if it ever
# fails, M.I.N.D just carries on.
# Two ways to run it:
#   python offline_hearing.py --serve
#       stays running and loads the model ONCE (ears.py keeps it while the internet is down, then closes it).
#       Each line in = {"sound": raw 16 kHz file, "model": "base.en", "language": "", "hint": "..."}
#       each line out = {"text": "..."} or {"error": "..."}
#   python offline_hearing.py <raw 16 kHz sound file> <model> <language or ""> <hint file>   (one go, prints the text)
# (Starting a new copy for every recording loaded the model each time: on a busy laptop several copies at once
# took over 40 s each and nothing was heard.)
import json
import sys
import numpy as np
from faster_whisper import WhisperModel

models = {}

def hear(sound_file, model_name, language, hint):
    if model_name not in models:
        models[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    samples = np.fromfile(sound_file, np.int16).astype(np.float32) / 32768.0
    segments, _ = models[model_name].transcribe(samples, language=language or None, initial_prompt=hint, beam_size=1)
    return " ".join(s.text for s in segments)

if sys.argv[1:] == ["--serve"]:
    out = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)
    for line in sys.stdin.buffer:
        try:
            ask = json.loads(line.decode("utf-8"))
            answer = {"text": hear(ask["sound"], ask["model"], ask.get("language", ""), ask.get("hint", ""))}
        except Exception as e:
            answer = {"error": str(e)[:300]}
        out.write(json.dumps(answer) + "\n")
        out.flush()
else:
    sound_file, model_name, language, hint_file = sys.argv[1:5]
    with open(hint_file, encoding="utf-8") as f:
        hint = f.read()
    sys.stdout.buffer.write(hear(sound_file, model_name, language, hint).encode("utf-8"))
