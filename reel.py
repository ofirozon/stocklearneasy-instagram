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

import design
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
        "source_label": "TODAY'S TERM" if category == "term" else "IN THE NEWS",
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
        "eyebrow_title": copy["concept"],
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
        "sub": "Daily lessons in the app. Link in bio.",
        "say": "Want the full lesson? Get the Stock Learn Easy app. Link in bio.",
    })

    return scenes


CATEGORY_META_TAG = design.CATEGORY_LABEL
DISCLAIMER = design.DISCLAIMER

# Instagram draws its own UI over a reel: the top bar eats roughly the first
# 160px and the caption, audio row and action buttons cover the bottom ~320px
# (and the right ~130px of the lower half). Everything that must stay
# readable, including the disclaimer, lives inside this box. The look is the
# carousel's (design.py), scaled up for a phone held upright.
REEL_PADDING = "180px 96px 330px 96px"


def _reel_head(eyebrow):
    pill = (
        f'<div class="pill" style="font-size:30px;padding:14px 32px;">{escape(eyebrow)}</div>'
        if eyebrow else ""
    )
    return (
        '<div class="head">'
        f'<div class="lockup" style="font-size:38px;"><img src="{design.ICON_URI}" '
        'width="76" height="76" alt="">Stock Learn Easy</div>'
        f'{pill}</div>'
    )


def _reel_foot():
    return (
        '<div style="display:flex;flex-direction:column;gap:14px;">'
        f'<div class="faint" style="font-size:26px;">@stocklearneasy</div>'
        f'<div class="faint" style="font-size:24px;">{DISCLAIMER}</div>'
        '</div>'
    )


def scene_html(scene):
    kind = scene["kind"]
    eyebrow = scene.get("eyebrow") or ""
    if kind == "chart":
        main = (
            '<div class="main">'
            + chart_scene_body(scene["chart"]) +
            '</div>'
        )
        head = _reel_head("THE CHART")
    elif kind == "hook":
        px = design.size_for(scene["title"], [(40, 124), (58, 112), (72, 102), (999, 92)])
        main = (
            '<div class="main" data-fit-box style="gap:56px;">'
            f'<div class="serif" data-fit="64" style="font-size:{px}px;line-height:1.08;">'
            f'{design.highlight_numbers(scene["title"])}</div>'
            '<div style="display:flex;flex-direction:column;gap:14px;">'
            '<div class="eyebrow faint" style="font-size:26px;">'
            f'{escape(scene.get("source_label", "IN THE NEWS"))}</div>'
            f'<div class="muted" style="font-size:38px;line-height:1.4;">{escape(scene["sub"])}</div>'
            '</div></div>'
        )
        head = _reel_head(eyebrow)
    elif kind == "concept":
        px = design.size_for(scene["title"], [(200, 56), (280, 52), (999, 48)])
        main = (
            '<div class="main" style="gap:36px;">'
            f'<div class="eyebrow" style="font-size:30px;color:{design.GREEN_TEXT};">THE LESSON</div>'
            f'<div class="serif" style="font-size:84px;line-height:1.05;">{escape(scene["eyebrow_title"])}</div>'
            '<div class="lesson" data-fit-box style="padding:56px 60px;max-height:900px;">'
            f'<div data-fit="30" style="font-size:{px}px;line-height:1.45;">{escape(scene["title"])}</div>'
            '</div></div>'
        )
        head = _reel_head("")
    elif kind == "takeaway":
        px = design.size_for(scene["title"], [(50, 96), (70, 86), (999, 76)])
        main = (
            '<div class="main" data-fit-box style="gap:44px;">'
            # Matches the carousel's last slide; see the note in generate.py.
            f'<div class="eyebrow" style="font-size:30px;color:{design.HIGHLIGHT};">RULE OF THUMB · SEND TO A FRIEND</div>'
            f'<div class="serif" data-fit="52" style="font-size:{px}px;line-height:1.1;">{escape(scene["title"])}</div>'
            f'<div class="muted" style="font-size:40px;line-height:1.4;">{escape(scene["sub"])}</div>'
            '</div>'
        )
        head = _reel_head("")
    else:  # cta
        main = (
            '<div class="main" style="align-items:center;text-align:center;gap:48px;">'
            f'<img src="{design.ICON_URI}" width="260" height="260" alt="" '
            'style="border-radius:22%;box-shadow:0 30px 80px rgba(0,0,0,0.45);">'
            '<div class="serif" style="font-size:104px;line-height:1.05;">Investing, explained from zero.</div>'
            f'<div class="muted" style="font-size:42px;line-height:1.4;">{escape(scene["sub"])}</div>'
            f'<div class="pill" style="font-size:36px;padding:22px 48px;letter-spacing:1px;">'
            'Stock Learn Easy · App Store</div>'
            '</div>'
        )
        head = '<div></div>'
    return design.page(WIDTH, HEIGHT, REEL_PADDING, f"{head}{main}{_reel_foot()}")


def chart_scene_body(chart):
    series = chart["series"]
    rising = series["change_pct"] >= 0
    return (
        '<div style="display:flex;flex-direction:column;gap:30px;">'
        f'<div class="eyebrow" style="font-size:30px;color:{design.GREEN_TEXT};">'
        f'{escape(series["range_label"].upper())}</div>'
        f'<div class="serif" style="font-size:100px;line-height:1.05;">{escape(chart["label"])}</div>'
        '<div style="display:flex;align-items:center;gap:28px;">'
        f'<div class="num" style="font-size:60px;font-weight:500;">'
        f'{market_data.fmt_price(series["last"], series["currency"])}</div>'
        f'<div class="chg {"up" if rising else "down"}" style="font-size:44px;padding:10px 28px;">'
        f'{market_data.fmt_pct(series["change_pct"])}</div>'
        '</div>'
        f'<div style="margin-top:20px;">{market_data.sparkline_svg(series, width=888, height=520)}</div>'
        f'<div class="muted" style="font-size:40px;line-height:1.4;">{escape(chart["why"])}</div>'
        '</div>'
    )

def render_frame(html: str, png_path: Path):
    html_path = png_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
         "--virtual-time-budget=5000", f"--screenshot={png_path.resolve()}",
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
