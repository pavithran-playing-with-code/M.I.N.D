# Speaker: is this the owner's voice? M.I.N.D learns your voice once ("Mind, learn my voice": you
# say a few sentences), then ignores commands in other voices (family, TV, a dog barking) without
# even sending them to the internet. Runs on the laptop (sherpa-onnx + a 25 MB model, ~0.15 s a check).
# "Mind, listen to everyone" turns it off.
import os
import threading
import urllib.request
import numpy as np
from memory import profile, save_profile, BASE_DIR

MODEL_NAME = "wespeaker_en_voxceleb_resnet34.onnx"
MODEL = os.path.join(BASE_DIR, "models", MODEL_NAME)
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/{MODEL_NAME}"
VOICEPRINT = os.path.join(BASE_DIR, "voiceprint.npy")  # your voice as numbers (personal, git-ignored)
MATCH = 0.72         # how alike a voice must be to count as you (tested: you 0.78-0.93, others 0.59-0.70)
LEARN_ABOVE = 0.82   # very sure it's you: learn a little from it (voices change: morning, a cold...)
SENTENCES = [        # what you read out while M.I.N.D learns your voice
    "Mind, open the dai project for me.",
    "Hey Mind, play some lofi music.",
    "What's the weather in Chennai today?",
    "Mind, remind me to call Genyx at five.",
    "Hey Mind, close the YouTube tab and shut down.",
]

lock = threading.Lock()
extractor = None
voiceprint = np.load(VOICEPRINT) if os.path.exists(VOICEPRINT) else None

def get_extractor():
    # Loads the model the first time it's needed (downloads it once if it's missing)
    global extractor
    with lock:
        if extractor is None:
            import sherpa_onnx
            if not os.path.exists(MODEL):
                os.makedirs(os.path.dirname(MODEL), exist_ok=True)
                urllib.request.urlretrieve(MODEL_URL, MODEL)
            extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
                sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=MODEL, num_threads=2))
        return extractor

def embed(sound):
    # Recorded sound (16 kHz, 16-bit) -> a "voice fingerprint" (a list of numbers of length 1)
    samples = np.frombuffer(sound, np.int16).astype(np.float32) / 32768
    model = get_extractor()
    with lock:
        stream = model.create_stream()
        stream.accept_waveform(16000, samples)
        stream.input_finished()
        vector = np.array(model.compute(stream))
    return vector / np.linalg.norm(vector)

def voiced(sound):
    # Only the parts where someone talks (drops silence and steady fan/room noise around your words),
    # so the voiceprint compares voices, not rooms
    samples = np.frombuffer(sound, np.int16)
    frame = 320  # 20 ms
    frames = samples[:len(samples) // frame * frame].reshape(-1, frame).astype(np.float32)
    if len(frames) < 10:
        return sound
    loud = np.sqrt((frames ** 2).mean(axis=1))
    keep = loud > max(np.percentile(loud, 30) * 2, 60)
    keep = np.convolve(keep, np.ones(9), "same") > 0  # keep a little around each loud bit (word edges)
    if keep.sum() < 25:  # under half a second of talking: use everything
        return sound
    return frames[keep].astype(np.int16).tobytes()

def active():
    return voiceprint is not None and profile.get("voice_lock", True)

MUSIC_EASIER = 0.08  # music mixed into your voice lowers the match (you scored 0.67 over a song)

def check(sound, music=False, always=False):
    # (is it you?, how alike 0..1). Always "yes" when no voice is learned or the lock is off.
    # music: something was playing, so a slightly lower match still counts as you.
    # always: compare even with the lock off (the in-talk check is its own setting)
    global voiceprint
    if voiceprint is None or not (always or active()) or len(sound) < 16000 * 2 * 0.5:  # (under 0.5 s: can't tell)
        return True, 1.0
    try:
        speech = voiced(sound)
        vector = embed(speech)
        score = float(np.dot(voiceprint, vector))
        # A long recording (reactor click, talking on): your words may be a few seconds of it,
        # so the best 3-second stretch counts too (whole-recording scores fell to 0.22 for you)
        step = 16000 * 2 * 3
        if len(speech) > step * 2:
            for start in range(0, len(speech) - step + 1, step // 2):
                part = embed(speech[start:start + step])
                if float(np.dot(voiceprint, part)) > score:
                    score, vector = float(np.dot(voiceprint, part)), part
    except Exception as e:
        print("Voice check failed:", e)
        return True, 1.0
    if score >= LEARN_ABOVE:  # surely you: move the voiceprint a tiny bit towards today's voice
        mixed = voiceprint * 0.95 + vector * 0.05
        voiceprint = mixed / np.linalg.norm(mixed)
        np.save(VOICEPRINT, voiceprint)
    return score >= profile.get("voice_match", MATCH) - (MUSIC_EASIER if music else 0), score

def learn(sounds):
    # Makes your voiceprint from a few recordings. Returns how alike they were to each other.
    global voiceprint
    vectors = [embed(s) for s in sounds if s]
    if len(vectors) < 3:
        return None
    mean = np.mean(vectors, axis=0)
    voiceprint = mean / np.linalg.norm(mean)
    np.save(VOICEPRINT, voiceprint)
    profile["voice_lock"] = True
    save_profile()
    return float(np.mean([np.dot(voiceprint, v) for v in vectors]))
