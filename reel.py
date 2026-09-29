#!/usr/bin/env python3
"""Turn a Stock Learn Easy post into a vertical Reel.

Why this exists (28.9.2026): the account had 2 followers, 14 posts in a
week, 45 total views and a reach of 1 to 3 per post. At that reach the
quality of a static carousel is irrelevant, because Instagram is not
showing it to anyone who doesn't already follow the account. Reels are
effectively the only surface left that still distributes to non-followers,
so the same copy that goes into the carousel is also rendered as a
1080x1920 video.

How it is built, all locally, no paid services:
  - each scene is an HTML card rendered to PNG by headless Chrome, the
    same renderer the square cards use, so the two formats can never
    drift apart visually
  - the voiceover is macOS `say`, one audio file per scene
  - each scene's on-screen duration is measured from its own audio, so
    the words and the card always end together
  - ffmpeg gives each scene a slow push-in, a short fade, and stitches
    the scenes into one H.264/AAC MP4

Everything degrades safely: if ffmpeg, Chrome or `say` is missing the
build raises and the caller falls back to publishing the carousel.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

import market_data

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

WIDTH, HEIGHT = 1080, 1920
FPS = 30

VOICE = "Samantha"
VOICE_RATE = 178          # words per minute; 180ish reads as brisk, not rushed
VOICE_ENABLED = True

SCENE_MIN_SECONDS = 2.6
SCENE_MAX_SECONDS = 11.0
SCENE_TAIL_SECONDS = 0.65  # beat of silence after the line, before the cut
REEL_MAX_SECONDS = 62.0    # hard ceiling; Instagram allows far more, attention doesn't


class ReelError(RuntimeError):
    pass


# --- scene text --------------------------------------------------------------

def build_scenes(category, copy, news=None, term=None, ticker=None, chart=None):
    """The reel's script: what is on screen and what is said, scene by scene.

    The spoken line is never identical to the on-screen text. Reading the
    slide out loud word for word is the single most common way an
    auto-generated reel announces itself as auto-generated.
    """
    headline = term[0] if category == "term" else news["title"]

    scenes = [{
        "kind": "hook",
        "eyebrow": CATEGORY_META_TAG.get(category, "MARKET"),
        "title": copy["hook"],
        "sub": headline,
        "say": copy["hook"],
    }]

    if chart:
        series = chart["series"]
        direction = "up" if series["change_pct"] >= 0 else "down"
        scenes.append({
            "kind": "chart",
            "chart": chart,
            "say": (
                f"{chart['label']} is {direction} "
                f"{abs(series['change_pct']):.0f} percent over the {series['range_label']}."
            ),
        })

    scenes.append({
        "kind": "concept",
        "eyebrow": copy["concept"].upper(),
        "title": copy["explain"],
        "say": copy["explain"],
        "title_size": 62,
    })

    scenes.append({
        "kind": "takeaway",
        "eyebrow": "THE TAKEAWAY",
        "title": copy["takeaway"],
        "sub": copy["question"],
        "say": copy["takeaway"],
    })

    scenes.append({
        "kind": "cta",
        "eyebrow": "",
        "title": "Stock Learn Easy",
        "sub": "One market story, explained simply, every day.",
        "say": "Follow Stock Learn Easy for one market story explained simply, every day.",
    })

    return scenes


CATEGORY_META_TAG = {
    "ipo": "IPO WATCH",
    "movers": "MARKET MOVERS",
    "macro": "MACRO WATCH",
    "news": "MARKET NEWS",
    "term": "TERM OF THE DAY",
}


# --- rendering ---------------------------------------------------------------

_REEL_CSS = """
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width:1080px; height:1920px;
    font-family:'Inter', sans-serif;
    background: linear-gradient(165deg, #0b1220 0%, #0f2743 55%, #123a5e 100%);
    color:#f5f7fa;
    display:flex; flex-direction:column;
    /* Instagram draws its own UI over a reel: the top bar eats roughly the
       first 160px and the caption, audio row and action buttons cover the
       bottom ~320px. Everything that must stay readable, including the
       disclaimer, lives inside this box. */
    padding:180px 96px 330px 96px;
  }
  .eyebrow {
    display:inline-block; align-self:flex-start;
    background:#22c55e; color:#06210f;
    font-weight:800; font-size:34px; letter-spacing:1px;
    padding:16px 38px; border-radius:999px;
  }
  .main { flex:1; display:flex; flex-direction:column; justify-content:center; }
  .title { font-size:82px; font-weight:800; line-height:1.28; }
  .sub {
    font-size:38px; font-weight:400; line-height:1.5; opacity:0.78;
    margin-top:40px; border-left:5px solid rgba(255,255,255,0.22); padding-left:26px;
  }
  .accent { color:#4dd8ff; }
  .brand { font-size:40px; font-weight:800; }
  .foot { display:flex; justify-content:space-between; align-items:center;
          border-top:2px solid rgba(255,255,255,0.15); padding-top:30px; }
  .disclaimer { font-size:24px; opacity:0.5; margin-top:16px; line-height:1.4; }
  .chart-head { display:flex; align-items:baseline; gap:28px; }
  .chart-symbol { font-size:72px; font-weight:800; }
  .chart-price { font-size:50px; font-weight:600; opacity:0.9; }
  .chart-change { font-size:40px; font-weight:800; padding:10px 26px; border-radius:999px; }
  .chart-change.up { color:#06210f; background:#22c55e; }
  .chart-change.down { color:#2a0a0a; background:#f87171; }
  .chart-label { font-size:34px; font-weight:600; opacity:0.75; margin-top:18px; }
  .chart-wrap { margin-top:44px; }
  .chart-why { font-size:36px; line-height:1.45; opacity:0.88; margin-top:44px; }
"""

DISCLAIMER = "Educational content only. Not financial or investment advice."


def scene_html(scene):
    if scene["kind"] == "chart":
        chart = scene["chart"]
        series = chart["series"]
        rising = series["change_pct"] >= 0
        body = (
            '<div class="chart-head">'
            f'<div class="chart-symbol">{escape(chart["label"])}</div>'
            f'<div class="chart-price">'
            f'{market_data.fmt_price(series["last"], series["currency"])}</div>'
            f'<div class="chart-change {"up" if rising else "down"}">'
            f'{market_data.fmt_pct(series["change_pct"])}</div>'
            '</div>'
            f'<div class="chart-label">{escape(series["range_label"].capitalize())}</div>'
            f'<div class="chart-wrap">{market_data.sparkline_svg(series, width=888, height=430)}</div>'
            f'<div class="chart-why">{escape(chart["why"])}</div>'
        )
        eyebrow = '<div class="eyebrow">THE CHART</div>'
    else:
        title_size = scene.get("title_size", 82)
        sub = f'<div class="sub">{escape(scene["sub"])}</div>' if scene.get("sub") else ""
        body = (
            f'<div class="title" style="font-size:{title_size}px;">{escape(scene["title"])}</div>'
            f'{sub}'
        )
        eyebrow = (
            f'<div class="eyebrow">{escape(scene["eyebrow"])}</div>'
            if scene.get("eyebrow") else ""
        )

    return f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head><meta charset="UTF-8"><style>{_REEL_CSS}</style></head>
<body>
  {eyebrow}
  <div class="main">{body}</div>
  <div>
    <div class="foot">
      <div class="brand">Stock <span class="accent">Learn</span> Easy</div>
      <div class="brand" style="opacity:0.6;font-weight:600;">@stocklearneasy</div>
    </div>
    <div class="disclaimer">{DISCLAIMER}</div>
  </div>
</body>
</html>
"""


def render_frame(html: str, png_path: Path):
    html_path = png_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", f"--screenshot={png_path.resolve()}",
         f"--window-size={WIDTH},{HEIGHT}", f"file://{html_path.resolve()}"],
        check=True, capture_output=True, timeout=45,
    )
    html_path.unlink()
    if not png_path.is_file() or png_path.stat().st_size < 20_000:
        raise ReelError(f"frame render produced nothing usable: {png_path.name}")


# --- audio -------------------------------------------------------------------

def say_to_file(text: str, out_path: Path):
    subprocess.run(
        # WAV + signed 16-bit little-endian: `say` refuses float formats in an
        # AIFF container ("Opening output file failed: fmt?"), and 44.1kHz here
        # saves ffmpeg a resample later.
        ["say", "-v", VOICE, "-r", str(VOICE_RATE), "-o", str(out_path),
         "--data-format=LEI16@44100", text],
        check=True, capture_output=True, timeout=120,
    )
    if not out_path.is_file() or out_path.stat().st_size < 1000:
        raise ReelError("voiceover produced no audio")


def audio_seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    return float(out)


# --- assembly ----------------------------------------------------------------

def build_scene_clip(png: Path, audio: Path | None, seconds: float, out: Path,
                     push_in: bool, fade_in: bool = False, fade_out: bool = False):
    """One scene as a self-contained clip: still frame, slow push, its own audio.

    zoompan works on the scaled-up frame and outputs at final size, which is
    what keeps the push smooth instead of stepping a pixel at a time.
    """
    frames = max(int(seconds * FPS), 1)
    if push_in:
        zexpr = f"'min(1+0.055*on/{frames},1.055)'"
    else:
        zexpr = f"'max(1.055-0.055*on/{frames},1)'"

    # Fades only at the very start and very end of the reel. Fading in on
    # every scene put a full black frame on each cut, which in a 30-second
    # video reads as a glitch rather than as an edit.
    fades = ""
    if fade_in:
        fades += ",fade=t=in:st=0:d=0.4"
    if fade_out:
        fades += f",fade=t=out:st={max(seconds - 0.5, 0):.3f}:d=0.5"

    vf = (
        f"scale={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z={zexpr}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
        f"{fades},format=yuv420p"
    )

    # Every clip carries an audio track, silent or not: concat refuses to
    # join clips whose stream layouts differ, and a reel where one scene
    # has no audio stream is exactly that case.
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png)]
    if audio is not None:
        cmd += ["-i", str(audio)]
        # apad extends the voice with silence so the scene can breathe past
        # the last word; atrim cuts it back to the exact clip length.
        afilter = f"apad,atrim=0:{seconds:.3f},aformat=sample_rates=44100:channel_layouts=stereo"
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        afilter = "aformat=sample_rates=44100:channel_layouts=stereo"

    cmd += [
        "-vf", vf,
        "-af", afilter,
        "-t", f"{seconds:.3f}", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=240)


def concat_clips(clips, out: Path, workdir: Path):
    listing = workdir / "clips.txt"
    listing.write_text(
        "".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)],
        check=True, capture_output=True, timeout=420,
    )


def build_reel(out_dir: Path, category, copy, when_utc,
               news=None, term=None, ticker=None, chart=None):
    """Build out_dir/reel.mp4 plus out_dir/reel.json. Raises ReelError on failure."""
    if shutil.which("ffmpeg") is None:
        raise ReelError("ffmpeg not installed")
    if not Path(CHROME).exists():
        raise ReelError("Chrome not installed")

    scenes = build_scenes(category, copy, news=news, term=term, ticker=ticker, chart=chart)

    with tempfile.TemporaryDirectory(prefix="slei-reel-") as tmp:
        work = Path(tmp)
        clips, total = [], 0.0

        for index, scene in enumerate(scenes):
            png = work / f"scene_{index}.png"
            render_frame(scene_html(scene), png)

            audio = None
            seconds = SCENE_MIN_SECONDS
            if VOICE_ENABLED and scene.get("say"):
                audio = work / f"scene_{index}.wav"
                say_to_file(scene["say"], audio)
                seconds = audio_seconds(audio) + SCENE_TAIL_SECONDS

            seconds = min(max(seconds, SCENE_MIN_SECONDS), SCENE_MAX_SECONDS)
            if total + seconds > REEL_MAX_SECONDS:
                seconds = max(REEL_MAX_SECONDS - total, 0.0)
                if seconds < 1.0:
                    break

            clip = work / f"clip_{index}.mp4"
            build_scene_clip(png, audio, seconds, clip,
                             push_in=(index % 2 == 0),
                             fade_in=(index == 0),
                             fade_out=(index == len(scenes) - 1))
            clips.append(clip)
            total += seconds

        if len(clips) < 2:
            raise ReelError("not enough scenes rendered to make a reel")

        out_path = out_dir / "reel.mp4"
        concat_clips(clips, out_path, work)

    duration = audio_seconds(out_path)
    (out_dir / "reel.json").write_text(
        json.dumps({
            "duration_seconds": round(duration, 2),
            "scenes": [s["kind"] for s in scenes][:len(clips)],
            "voice": VOICE if VOICE_ENABLED else None,
            "size_bytes": out_path.stat().st_size,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


if __name__ == "__main__":
    # Manual smoke test: python reel.py <scheduled-slot-dir>
    slot = Path(sys.argv[1])
    data = json.loads((slot / "source.json").read_text(encoding="utf-8"))
    chart = None
    print(build_reel(slot, data["category"], data["copy"],
                     None, news=data.get("news"), term=data.get("term"),
                     ticker=data.get("ticker"), chart=chart))
