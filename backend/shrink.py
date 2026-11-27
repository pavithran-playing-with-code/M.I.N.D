# "Smaller copy" of a video for the phone: far away on weak internet, a 3 GB movie can come as ~1 GB (720p)
# or ~0.5 GB (480p). The ORIGINAL is never touched; the copy goes to Downloads\From M.I.N.D\Smaller copies
# (deleted after 3 days, no junk). Made with the laptop's built-in Intel video chip (Quick Sync) when it can,
# else Windows' own encoder, else plain software. Runs in the background; the phone shows the progress and gets
# a notification when it's ready. Smaller = a little less sharp (that's the trade); sound stays good (AAC 128k).
#
# The video work runs as its OWN program (python shrink.py <video> <height>), never inside M.I.N.D: heavy video
# work in M.I.N.D could make its voice stutter, and a crash in the video library can't take M.I.N.D down.
# It prints "P <percent>" lines, then "OUT <path>" or "ERR <reason>".
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
OUT = os.path.join(HOME, "Downloads", "From M.I.N.D", "Smaller copies")
KEEP = 3 * 24 * 3600
ENCODERS = [("h264_qsv", "nv12"), ("h264_mf", "nv12"), ("libx264", "yuv420p")]
SIZES = {720: 1_600_000, 480: 750_000}  # height -> video bits per second
jobs = {}  # original path -> {"percent", "out", "error", "done", "height", "process"}
lock = threading.Lock()
NO_WINDOW = 0x08000000
PYTHON = os.path.join(HERE, "venv", "Scripts", "python.exe")

def clean():
    try:
        for entry in os.scandir(OUT):
            if time.time() - entry.stat().st_mtime > KEEP:
                os.remove(entry.path)
    except OSError:
        pass

# ---------- M.I.N.D's side: start the helper program and follow it ----------
def guess_sizes(path):
    # About how big each copy will be (for the phone to show before you choose); the helper reads the length
    try:
        said = subprocess.run([PYTHON, os.path.join(HERE, "shrink.py"), "--seconds", path], capture_output=True, text=True,
                              timeout=15, creationflags=NO_WINDOW).stdout.strip()
        return {str(h): int(float(said or 0) * (rate + 128_000) / 8) for h, rate in SIZES.items()}
    except Exception:
        return {}

def start(path, height=720):
    height = height if height in SIZES else 720
    with lock:
        job = jobs.get(path)
        if job and not job["done"] and not job["error"]:
            return job  # (already making it)
        job = jobs[path] = {"percent": 0, "out": "", "error": "", "done": False, "height": height}
    threading.Thread(target=follow, args=(path, job), daemon=True).start()
    return job

def follow(path, job):
    clean()
    helper = job["process"] = subprocess.Popen([PYTHON, os.path.join(HERE, "shrink.py"), path, str(job["height"])],
                                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                               encoding="utf-8", creationflags=NO_WINDOW | 0x00004000)  # (below normal priority)
    for line in helper.stdout:
        kind, _, rest = line.strip().partition(" ")
        if kind == "P":
            job["percent"] = int(rest or 0)
        elif kind == "OUT":
            job.update(out=rest, percent=100, done=True)
            size = os.path.getsize(rest) / 1e6
            print(f"(Smaller copy ready: {os.path.basename(rest)}, {size:.0f} MB)")
            try:
                import phone
                phone.notify(f"{os.path.basename(rest)} is ready ({size:.0f} MB). Open the M.I.N.D app to download it.",
                             "📉 Smaller copy ready", always=True)  # (asked for from the phone)
            except Exception:
                pass
        elif kind == "ERR":
            job.update(error="Couldn't make a smaller copy: " + rest, done=True)
    helper.wait()
    if not job["done"]:
        job.update(error="Couldn't make a smaller copy" + (": stopped" if job.get("stop") else ""), done=True)

def stop(path):
    job = jobs.get(path)
    if job:
        job["stop"] = True
        try:
            job["process"].kill()
        except Exception:
            pass

# ---------- The helper program's side ----------
def make(path, height):
    os.makedirs(OUT, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    final = os.path.join(OUT, f"{stem} ({height}p).mp4")
    temp = final + ".making"
    job = {"height": height, "percent": 0}
    last = ""
    for encoder, pixels in ENCODERS:
        try:
            encode(path, temp, encoder, pixels, job)
            os.replace(temp, final)
            print("OUT", final, flush=True)
            return
        except Exception as error:
            last = str(error)[:120]
            try:
                os.remove(temp)
            except OSError:
                pass
    print("ERR", last, flush=True)

def encode(path, temp, encoder, pixels, job):
    import av
    with av.open(path) as source, av.open(temp, "w", format="mp4") as target:
        video = source.streams.video[0]
        video.thread_type = "AUTO"  # (decode with all cores)
        sound = source.streams.audio[0] if source.streams.audio else None
        width0, height0 = video.codec_context.width, video.codec_context.height
        height = min(job["height"], height0) // 2 * 2
        width = int(width0 * height / height0) // 2 * 2
        rate = video.average_rate or 30
        out_video = target.add_stream(encoder, rate=rate)
        out_video.width, out_video.height, out_video.pix_fmt = width, height, pixels
        out_video.bit_rate = SIZES[job["height"]]
        out_sound = resampler = None
        if sound:
            out_sound = target.add_stream("aac", rate=48000)
            out_sound.bit_rate = 128_000
            out_sound.layout = "stereo"
            resampler = av.AudioResampler(format="fltp", layout="stereo", rate=48000)
        seconds = (source.duration or 1) / 1_000_000
        streams = [video] + ([sound] if sound else [])
        # Two lanes at once: one thread reads + shrinks the pictures, this one encodes and writes the file
        import queue
        lane = queue.Queue(maxsize=16)
        problem = []

        def read():
            try:
                for packet in source.demux(*streams):
                    if job.get("stop"):
                        break
                    for frame in packet.decode():
                        if packet.stream is video:
                            # AREA = sharp and quick for making pictures smaller (the default was the slow step)
                            small = frame.reformat(width=width, height=height, format=pixels, interpolation="AREA")
                            small.pts, small.time_base = frame.pts, frame.time_base  # (the movie's own timing; made-up numbers broke the file)
                            lane.put(("v", small, frame.time))
                        else:
                            lane.put(("a", frame, None))
            except Exception as error:
                problem.append(error)
            lane.put(None)

        threading.Thread(target=read, daemon=True).start()
        while True:
            item = lane.get()
            if item is None:
                break
            kind, frame, at = item
            if kind == "v":
                for out in out_video.encode(frame):
                    target.mux(out)
                if at:
                    now = min(99, int(at / seconds * 100))
                    if now != job["percent"]:
                        job["percent"] = now
                        print("P", now, flush=True)  # (M.I.N.D reads this for the phone's progress bar)
            else:
                for piece in resampler.resample(frame):
                    for out in out_sound.encode(piece):
                        target.mux(out)
        if job.get("stop"):
            raise RuntimeError("stopped")
        if problem:
            raise problem[0]
        for out in out_video.encode():
            target.mux(out)
        if out_sound:
            for out in out_sound.encode():
                target.mux(out)

if __name__ == "__main__":
    if sys.argv[1] == "--seconds":  # (how long the video is, for the size guess)
        import av
        with av.open(sys.argv[2]) as media:
            print((media.duration or 0) / 1_000_000)
    else:
        make(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 720)
