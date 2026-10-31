# Hearing with no internet, as its own small program. Inside M.I.N.D this library crashed the whole app (it clashes
# with another library's copy of a Windows file), so ears.py starts this only when it's needed: if it ever
# fails, M.I.N.D just carries on, and it uses no memory the rest of the time.
# Usage: python offline_hearing.py <raw 16 kHz sound file> <model> <language or ""> <hint file>
import sys
import numpy as np
from faster_whisper import WhisperModel

sound_file, model_name, language, hint_file = sys.argv[1:5]
with open(hint_file, encoding="utf-8") as f:
    hint = f.read()
samples = np.fromfile(sound_file, np.int16).astype(np.float32) / 32768.0
model = WhisperModel(model_name, device="cpu", compute_type="int8")
segments, _ = model.transcribe(samples, language=language or None, initial_prompt=hint, beam_size=1)
sys.stdout.buffer.write(" ".join(s.text for s in segments).encode("utf-8"))
