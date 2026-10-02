#!/usr/bin/env python3
"""Render an animated explainer in animation/*.html to a 1080x1920 MP4.

Why frame-by-frame instead of a screen recording: the scene is written so
that every property is a pure function of `?t=`, which means a frame can be
grabbed in any order, in parallel, and reproduced exactly. A recording of a
CSS animation would drift with CPU load and could never be re-rendered
identically after an edit.

Headless Chrome costs about 1.7s per launch, so the frames are grabbed by a
small pool of concurrent Chrome processes. 20.5s at 25fps is 513 frames,
roughly two minutes of wall clock on this machine.

Voiceover is one clip per scene, each laid onto the timeline at its scene's
start with ffmpeg `adelay`. If a clip runs longer than its scene it is
re-synthesised faster rather than allowed to bleed into the next beat. The
English scene uses the local neural voice (`say-neural.py`, Kokoro); the
Hebrew one still uses macOS `say`, which is the only engine here that speaks
Hebrew at all.

All the English episodes share village.html and one five-beat skeleton; what
makes them different lessons is episodes/<id>.js plus the narration in SCENES.
`bull-vs-bear` is the rejected Hebrew v1, kept only so its render stays
reproducible.

    ./render.py --scene bull-bear               # full build
    ./render.py --scene volatility --fps 12     # quick look
    ./render.py --scene compound --still 7.2    # one frame, for checking a pose
    ./render.py --scene correction --voice-only # re-dub without redoing frames
    ./render.py --all                           # every English episode in turn
"""
import argparse
import json
import shutil
import subprocess
import sys
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH, HEIGHT = 1080, 1920
# 10 concurrent Chromes drove this machine to a load average of 191 and cut
# throughput roughly tenfold. 5 is where it stops fighting itself.
WORKERS = 5

# Local neural TTS. macOS `say` only has the compact voices here, and Ofir
# rejected the first cut over exactly that. See the script's own docstring.
NEURAL = Path.home() / ".local/bin/say-neural.py"

# One entry per explainer. `narration` is (start second, line); each line must
# finish inside its own scene, and `scene_ends` gives the deadline for each.
# `engine` is "neural" (Kokoro, a voice name like af_heart, paced by `speed`)
# or "say" (macOS, a voice name like Samantha, paced by `rate` in wpm).
# Every English episode shares one scene file and one five-beat skeleton. What
# differs is the data in episodes/<id>.js and the narration below. `narration`
# is (start second, line); `scene_ends` is the deadline for each line.
BEATS = [3.20, 6.60, 12.30, 18.00, 20.5]

SCENES = {
    "bull-bear": {
        "html": "village.html", "episode": "bull-bear", "duration": 20.5,
        "engine": "neural", "voice": "af_heart", "speed": 0.98,
        "narration": [
            (0.30,  "Why a bull, and why a bear?"),
            (3.50,  "Every market has two animals living in it."),
            (6.90,  "The bull runs through town and throws its horns up. "
                    "That's a bull market."),
            (12.60, "The bear walks into town and swipes its paw down. "
                    "That's a bear market."),
            (18.25, "The bull, and the bear."),
        ],
        "scene_ends": BEATS,
    },
    "correction": {
        "html": "village.html", "episode": "correction", "duration": 20.5,
        "engine": "neural", "voice": "af_heart", "speed": 0.98,
        "narration": [
            (0.30,  "When is a fall just a dip?"),
            (3.50,  "Two words get used for the same red screen."),
            (6.90,  "A correction is a drop of about ten percent, "
                    "and it usually comes back."),
            (12.60, "Twenty percent or more, and it has a different name. "
                    "That's a bear market."),
            (18.25, "Ten percent, or twenty."),
        ],
        "scene_ends": BEATS,
    },
    "volatility": {
        "html": "village.html", "episode": "volatility", "duration": 20.5,
        "engine": "neural", "voice": "af_heart", "speed": 0.98,
        "narration": [
            (0.30,  "Why does the price jump around so much?"),
            (3.50,  "Up on Monday, down on Tuesday, and nothing changed."),
            (6.90,  "Day to day, the two animals pull the same line "
                    "in opposite directions."),
            (12.60, "Step back far enough and the argument turns into a trend."),
            (18.25, "Close up, noise. Far away, a trend."),
        ],
        "scene_ends": BEATS,
    },
    "compound": {
        "html": "village.html", "episode": "compound", "duration": 20.5,
        "engine": "neural", "voice": "af_heart", "speed": 0.98,
        "narration": [
            (0.30,  "Why does money grow slowly, then all at once?"),
            (3.50,  "Compounding is the quietest idea in investing."),
            (6.90,  "For years almost nothing happens. "
                    "The line barely leaves the ground."),
            (12.60, "Then the gains start earning gains, "
                    "and the curve bends upward."),
            (18.25, "Slow for years. Then fast."),
        ],
        "scene_ends": BEATS,
    },
    # v1: Hebrew, no world, rejected for the slot. Kept so the render it
    # produced stays reproducible, not because it ships.
    "bull-vs-bear": {
        "html": "bull-vs-bear.html", "episode": None, "duration": 15.0,
        "engine": "say",            # Kokoro has no Hebrew voice
        "voice": "Carmit",          # the only he_IL voice macOS ships
        "rate": 182,
        "narration": [
            (0.55,  "\u05e9\u05d5\u05e8 \u05d5\u05d3\u05d5\u05d1. \u05e9\u05ea\u05d9 \u05d4\u05d7\u05d9\u05d5\u05ea \u05e9\u05e9\u05d5\u05dc\u05d8\u05d5\u05ea \u05d1\u05e9\u05e4\u05d4 \u05e9\u05dc \u05e9\u05d5\u05e7 \u05d4\u05d4\u05d5\u05df."),
            (3.85,  "\u05e9\u05d5\u05e7 \u05e9\u05d5\u05e8\u05d9. \u05d4\u05e9\u05d5\u05e8 \u05e0\u05d5\u05e2\u05e5 \u05d0\u05ea \u05d4\u05e7\u05e8\u05e0\u05d9\u05d9\u05dd \u05db\u05dc\u05e4\u05d9 \u05de\u05e2\u05dc\u05d4, \u05d5\u05db\u05db\u05d4 \u05d2\u05dd \u05d4\u05de\u05d7\u05d9\u05e8\u05d9\u05dd \u05e2\u05d5\u05dc\u05d9\u05dd."),
            (8.25,  "\u05e9\u05d5\u05e7 \u05d3\u05d5\u05d1\u05d9. \u05d4\u05d3\u05d5\u05d1 \u05de\u05e0\u05d7\u05d9\u05ea \u05d0\u05ea \u05d4\u05db\u05e3 \u05db\u05dc\u05e4\u05d9 \u05de\u05d8\u05d4, \u05d5\u05d4\u05de\u05d7\u05d9\u05e8\u05d9\u05dd \u05d9\u05d5\u05e8\u05d3\u05d9\u05dd."),
            (12.45, "\u05e7\u05e8\u05e0\u05d9\u05d9\u05dd \u05dc\u05de\u05e2\u05dc\u05d4, \u05db\u05e3 \u05dc\u05de\u05d8\u05d4. \u05db\u05db\u05d4 \u05ea\u05d6\u05db\u05e8\u05d5 \u05d0\u05ea \u05d6\u05d4 \u05ea\u05de\u05d9\u05d3."),
        ],
        "scene_ends": [3.60, 8.00, 12.20, 15.0],
    },
}

# Filled in by main() once --scene is known; the frame grabber and the voice
# synthesiser both read them.
SCENE = None
DURATION = None
CFG = None
DATA_FILE = None     # per-run episode + captions bundle, see write_data()


class RenderError(RuntimeError):
    pass


def require(path, what):
    if not Path(path).exists():
        raise RenderError(f"{what} not found at {path}")


# --- frames -----------------------------------------------------------------

def grab(args):
    """One frame. Chrome exits on its own once the virtual clock is spent.

    Deliberately no --user-data-dir: passing one makes this Chrome build hang
    indefinitely instead of screenshotting (verified 1.10.2026). Headless
    Chrome already makes its own throwaway profile, so parallel instances do
    not collide. --virtual-time-budget is what makes it exit promptly, and is
    the same flag generate.py and reel.py use for the cards.
    """
    t, dest = args
    url = f"{SCENE.as_uri()}?t={t:.4f}"
    if DATA_FILE:
        url += f"&d={DATA_FILE.name}"
    cmd = [
        CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--virtual-time-budget=4000",
        f"--window-size={WIDTH},{HEIGHT}",
        f"--screenshot={dest}",
        url,
    ]
    # Under load this machine has stalled a single Chrome past two minutes, and
    # on the first pass that killed a render twenty minutes in. One slow frame
    # is not a reason to throw away the whole episode, so it gets three goes
    # with a breather between them.
    for attempt in range(3):
        try:
            subprocess.run(cmd, capture_output=True, timeout=240)
        except subprocess.TimeoutExpired:
            print(f"  ! frame t={t:.2f} timed out, retry {attempt + 1}/3",
                  file=sys.stderr, flush=True)
            Path(dest).unlink(missing_ok=True)
            time.sleep(4)
            continue
        if Path(dest).exists():
            return dest
        time.sleep(2)
    raise RenderError(f"no frame written for t={t:.3f} after 3 attempts")


def render_frames(frames_dir, fps, reuse=False):
    total = int(round(DURATION * fps))
    jobs = [(i / fps, str(frames_dir / f"f{i:05d}.png")) for i in range(total)]
    if reuse:
        jobs = [j for j in jobs if not Path(j[1]).exists()]
        if not jobs:
            print(f"  frames {total}/{total} (all cached)")
            return total
        print(f"  reusing {total - len(jobs)} cached frames")
    done = total - len(jobs)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for _ in pool.map(grab, jobs):
            done += 1
            if done % 25 == 0 or done == total:
                print(f"  frames {done}/{total}", flush=True)
    return total


# --- voice ------------------------------------------------------------------

def duration_of(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def say_clip(text, dest, rate):
    """macOS `say`. Only the compact voices are installed on this machine, so
    this is the fallback, not the first choice. `rate` is words per minute."""
    subprocess.run(["say", "-v", CFG["voice"], "-r", str(rate),
                    "-o", str(dest), text],
                   check=True, capture_output=True)
    return duration_of(dest)


def neural_clip(text, dest, speed):
    """Kokoro via ~/.local/bin/say-neural.py: a local neural voice, no account
    and no network. `speed` is a multiplier, 1.0 being its natural pace."""
    # Kokoro has aborted under memory pressure when renders are running on the
    # same machine. It is a resource problem, not a bad line, so give it room
    # and try again rather than losing the whole dub.
    for attempt in range(3):
        res = subprocess.run([str(NEURAL), "--voice", CFG["voice"],
                              "--speed", f"{speed:.3f}", text, str(dest)],
                             capture_output=True, text=True)
        if res.returncode == 0 and Path(dest).exists():
            return duration_of(dest)
        print(f"  ! neural voice failed (rc={res.returncode}), "
              f"retry {attempt + 1}/3", file=sys.stderr, flush=True)
        Path(dest).unlink(missing_ok=True)
        time.sleep(8)
    raise RenderError(f"neural voice could not synthesise: {text[:50]}")


def render_voice(work):
    """One clip per scene, re-synthesised faster if it overruns its scene.

    Both engines are driven the same way: synthesise, measure, and if the clip
    would bleed past its scene, speed it up and try again. Only the units
    differ, words per minute for `say` against a multiplier for Kokoro.
    """
    neural = CFG.get("engine") == "neural"
    if neural and not NEURAL.exists():
        print(f"  ! {NEURAL} missing, falling back to macOS say", file=sys.stderr)
        neural = False
    ext = "wav" if neural else "aiff"
    unit = "x" if neural else " wpm"

    clips = []
    for idx, (start, line) in enumerate(CFG["narration"]):
        # leave a beat before the mood changes under the next line
        budget = CFG["scene_ends"][idx] - start - 0.15
        dest = work / f"vo{idx}.{ext}"
        rate = CFG["speed"] if neural else CFG["rate"]
        synth = neural_clip if neural else say_clip

        dur = synth(line, dest, rate)
        tries = 0
        while dur > budget and tries < 4:
            over = dur / budget
            rate = rate * min(1.3, over) * 1.02 if neural \
                else int(rate * min(1.35, over) + 4)
            dur = synth(line, dest, rate)
            tries += 1

        shown = f"{rate:.2f}{unit}" if neural else f"{rate}{unit}"
        if dur > budget:
            print(f"  ! scene {idx + 1} voice is {dur:.2f}s for a {budget:.2f}s "
                  f"slot even at {shown}; shorten the line", file=sys.stderr)
        else:
            print(f"  voice {idx + 1}: {dur:.2f}s / {budget:.2f}s at {shown}")
        clips.append((start, dest))
    return clips


def chunk_line(line, max_words=4):
    """Split a narration line into caption-sized groups.

    85 to 88 percent of reels are watched muted, so the captions are not an
    accessibility afterthought, they are how most viewers get the lesson.
    Groups break on punctuation first, because a caption that splits a clause
    reads worse than one that is a word too long.
    """
    out, cur = [], []
    for word in line.split():
        cur.append(word)
        if word.endswith((".", ",", "!", "?", ":", ";")) or len(cur) >= max_words:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def write_data(clips, episode_js):
    """One file per run holding both the episode and the caption timings.

    These used to be two files in the source directory, shared by every run.
    That is fine until two renders overlap, at which point one quietly
    rewrites the other's data and the finished film is a chimera: this is
    exactly how a `compound` render ended up carrying `correction`'s title and
    `bull-bear`'s captions.
    """
    cards = []
    for (start, path), (_, line) in zip(clips, CFG["narration"]):
        dur = duration_of(path)
        groups = chunk_line(line)
        total = sum(len(g) for g in groups) or 1
        at = start
        for g in groups:
            span = dur * len(g) / total
            cards.append({"t0": round(at, 3), "t1": round(at + span, 3), "text": g})
            at += span

    body = ["// generated by render.py, one per run, safe to delete"]
    body.append(episode_js.read_text() if episode_js else "window.EPISODE = undefined;")
    body.append("window.CAPTIONS = " + json.dumps(cards, ensure_ascii=False) + ";")
    DATA_FILE.write_text("\n".join(body) + "\n")
    print(f"  captions: {len(cards)} cards -> {DATA_FILE.name}")


def music_bed(work):
    """A quiet ambient bed, synthesised rather than downloaded.

    The loop needs continuous audio across the seam, and a licensed track would
    mean deciding whose track and under what terms. Five detuned sine partials
    cost nothing and raise no question. Every frequency completes a whole
    number of cycles in DURATION, so the bed loops with no click: 110Hz is
    2255 cycles in 20.5s, 110.2927 is 2261, and so on.

    It is generated three times long and the middle slice taken, because the
    filters need to settle; cutting from steady state is what gets the seam
    discontinuity down from 28% of peak to under 2%.
    """
    dest = work / "bed.wav"
    span = DURATION
    expr = (f"0.085*sin(2*PI*{2255/span:.6f}*t)"
            f"+0.060*sin(2*PI*{2261/span:.6f}*t)"
            f"+0.040*sin(2*PI*{3380/span:.6f}*t)*(0.62+0.38*sin(2*PI*{2/span:.6f}*t))"
            f"+0.022*sin(2*PI*{4510/span:.6f}*t)"
            f"+0.014*sin(2*PI*{6760/span:.6f}*t)*(0.5+0.5*sin(2*PI*{3/span:.6f}*t))")
    res = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"aevalsrc='{expr}':s=48000:d={span * 3:.3f}",
         "-af", f"lowpass=f=900,highpass=f=45,"
                f"atrim=start={span:.3f}:end={span * 2:.3f},asetpts=PTS-STARTPTS",
         "-c:a", "pcm_s16le", str(dest)],
        capture_output=True, text=True)
    if res.returncode != 0:
        print("  ! music bed failed, going out dry", file=sys.stderr)
        return None
    return dest


def mix_voice(clips, work):
    """Lay each clip at its start second on one silent 15s bed."""
    mixed = work / "voice.m4a"
    inputs, filters, labels = [], [], []
    for i, (start, path) in enumerate(clips):
        inputs += ["-i", str(path)]
        filters.append(f"[{i}:a]aresample=48000,adelay={int(start * 1000)}|"
                       f"{int(start * 1000)}[a{i}]")
        labels.append(f"[a{i}]")

    # the bed runs the full length and under everything, so the loop point has
    # no silence in it
    bed = music_bed(work)
    if bed:
        inputs += ["-i", str(bed)]
        filters.append(f"[{len(clips)}:a]aresample=48000,volume=0.16[bed]")
        labels.append("[bed]")

    n = len(labels)
    graph = ";".join(filters) + ";" + "".join(labels) + \
        f"amix=inputs={n}:dropout_transition=0:normalize=0," \
        f"apad,atrim=0:{DURATION},alimiter=limit=0.95[out]"
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
         "-c:a", "aac", "-b:a", "160k", str(mixed)],
        check=True, capture_output=True)
    return mixed


# --- assembly ---------------------------------------------------------------

def encode(frames_dir, fps, voice, dest):
    cmd = ["ffmpeg", "-y", "-framerate", str(fps),
           "-i", str(frames_dir / "f%05d.png")]
    if voice:
        cmd += ["-i", str(voice)]
    # Never output below the input rate: `-r 30` against a 50fps render would
    # silently throw away two frames in five, which is exactly the smoothness
    # the higher render was paid for.
    cmd += ["-c:v", "libx264", "-profile:v", "high", "-crf", "19",
            "-pix_fmt", "yuv420p", "-r", str(max(fps, 30)),
            "-movflags", "+faststart"]
    if voice:
        cmd += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd.append(str(dest))
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RenderError(res.stderr[-2000:])


def redub(dest):
    """Swap the audio track of an already-rendered file, copying the video.

    Auditioning voices is otherwise absurd: the frames take seven minutes and
    none of them depend on the narration.
    """
    require(dest, "the rendered video")
    work = Path(tempfile.mkdtemp(prefix="dub-"))
    try:
        print(f"re-dubbing {dest.name} with {CFG['voice']}")
        # A re-dub only replaces audio. The captions already baked into the
        # picture came from the previous render of the same narration, so there
        # is nothing to rewrite and nothing shared to corrupt.
        clips = render_voice(work)
        voice = mix_voice(clips, work)
        tmp = work / dest.name
        res = subprocess.run(
            ["ffmpeg", "-y", "-i", str(dest), "-i", str(voice),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "160k", "-shortest",
             "-movflags", "+faststart", str(tmp)],
            capture_output=True, text=True)
        if res.returncode != 0:
            raise RenderError(res.stderr[-2000:])
        shutil.move(str(tmp), str(dest))
        print(f"done: {dest}  ({dest.stat().st_size / 1e6:.1f} MB)")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    global SCENE, DURATION, CFG, DATA_FILE

    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", choices=sorted(SCENES), default="bull-bear")
    ap.add_argument("--all", action="store_true",
                    help="render every episode that has an episodes/<id>.js")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--still", type=float, help="render one frame at this second")
    ap.add_argument("--out", help="defaults to out/<scene>.mp4")
    ap.add_argument("--keep-frames", action="store_true",
                    help="cache frames in out/frames and reuse them on the next "
                         "run; use when only the narration or timing changed, "
                         "and delete the folder after editing the scene")
    ap.add_argument("--voice", help="override the scene's voice for this run")
    ap.add_argument("--voice-only", action="store_true",
                    help="re-dub the existing out/<scene>.mp4 in place, copying "
                         "the video track; seconds instead of the seven minutes "
                         "a frame render costs")
    a = ap.parse_args()

    if a.all:
        for name in [k for k, v in sorted(SCENES.items()) if v.get("episode")]:
            print(f"=== {name} ===", flush=True)
            subprocess.run([str(Path(__file__)), "--scene", name,
                            "--fps", str(a.fps)] +
                           (["--keep-frames"] if a.keep_frames else []),
                           check=False)
        return

    CFG = dict(SCENES[a.scene])
    SCENE = ROOT / CFG["html"]
    DURATION = CFG["duration"]
    # One data file per run, named after this process, so two renders can never
    # overwrite each other's episode or captions.
    DATA_FILE = ROOT / f"data-{os.getpid()}.js"
    EPISODE_JS = None
    if CFG.get("episode"):
        EPISODE_JS = ROOT / "episodes" / f"{CFG['episode']}.js"
        require(EPISODE_JS, f"episode data for {CFG['episode']}")
    if a.voice:
        CFG["voice"] = a.voice
    if not a.out:
        a.out = str(OUT / f"{a.scene}.mp4")

    if not shutil.which("ffmpeg"):
        raise RenderError("ffmpeg not on PATH")
    OUT.mkdir(exist_ok=True)

    if a.voice_only:
        redub(Path(a.out))
        return

    require(CHROME, "Google Chrome")
    require(SCENE, "the scene")

    if a.still is not None:
        # a still still needs the episode on disk, but has no voice to time
        # captions against, so it gets the episode and an empty caption list
        DATA_FILE.write_text(
            (EPISODE_JS.read_text() if EPISODE_JS else "window.EPISODE = undefined;")
            + "\nwindow.CAPTIONS = [];\n")
        dest = OUT / f"still-{a.still:g}s.png"
        try:
            grab((a.still, str(dest)))
            print(dest)
        finally:
            DATA_FILE.unlink(missing_ok=True)
        return

    work = Path(tempfile.mkdtemp(prefix="anim-"))
    frames = (OUT / "frames") if a.keep_frames else (work / "frames")
    frames.mkdir(parents=True, exist_ok=True)
    try:
        # Voice first: the burned-in captions are timed from the measured clip
        # durations, and the frames have to be able to read them.
        voice = None
        if a.no_voice:
            DATA_FILE.write_text(
                (EPISODE_JS.read_text() if EPISODE_JS else "window.EPISODE = undefined;")
                + "\nwindow.CAPTIONS = [];\n")
        else:
            print("voiceover")
            clips = render_voice(work)
            write_data(clips, EPISODE_JS)
            voice = mix_voice(clips, work)

        print(f"rendering {DURATION:g}s at {a.fps}fps")
        render_frames(frames, a.fps, reuse=a.keep_frames)

        print("encoding")
        encode(frames, a.fps, voice, Path(a.out))
        size = Path(a.out).stat().st_size / 1e6
        print(f"done: {a.out}  ({size:.1f} MB)")
    finally:
        shutil.rmtree(work, ignore_errors=True)
        DATA_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except RenderError as e:
        print(f"render failed: {e}", file=sys.stderr)
        sys.exit(1)
