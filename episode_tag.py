#!/usr/bin/env python3
"""Name the app lesson inside an animated episode (backlog 70d, 8.11.2026).

Episodes are the only shape on the account that leaves the follower base (the
6.11 volatility re-post reached 207), but the film itself never said there is
a lesson behind it, and the caption only said "Want the full lesson?" without
naming one. Most reel viewers never open the caption.

Two things, both keyed on a fixed map checked against the app's own catalogue
(lessons.TITLES), so a title that does not exist in the app cannot ship:

  * a static tag under the brand mark, "IN THE APP: <short title>", burned in
    from the first frame to the last, so the loop seam stays clean (the reason
    village.html chose a small mark over an end card);
  * the caption's app line names the lesson.

An episode missing from the map keeps the generic line and an untagged film:
a vague pointer beats a confident wrong one.

    episode_tag.py <episode> <src.mp4> <dest.mp4>   # tag one file
"""
import pathlib
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

import lessons

ROOT = pathlib.Path(__file__).resolve().parent
FONT = ROOT / "assets" / "fonts" / "DMSans_700Bold.ttf"

# episode -> app title. compound has no honest match in the catalogue.
EPISODE_LESSONS = {
    "bull-bear": "Bull & Bear Markets",
    "correction": "Bull & Bear Markets",
    "volatility": "Risk Assessment & Measurement",
    "diversify": "Diversification Strategies",
    "inflation": "Types of Investment Risk",
    "split": "Dividends & Stock Splits",
}
assert set(EPISODE_LESSONS.values()) <= lessons.TITLES, "episode lesson not in the app"

GENERIC_LINE = "📲 Want the full lesson? Stock Learn Easy on the App Store, link in bio."

# On the brand row of animation/village.html (#brand: left 70, top 286, 54 tall,
# wordmark ends near x 415), so it never meets the hook title card below it.
TAG_X, TAG_Y = 440, 287


def lesson_for(episode):
    """(app title, short title) or None."""
    title = EPISODE_LESSONS.get(episode)
    if not title:
        return None
    short = next(s for t, s, _ in lessons.LESSONS if t == title)
    return title, short


def app_line(episode):
    hit = lesson_for(episode)
    if not hit:
        return GENERIC_LINE
    return (f"📲 The full lesson is \"{hit[0]}\" in Stock Learn Easy. "
            "App Store, link in bio.")


def tag_caption(episode, caption):
    """Swap the generic app line for the named one. Unchanged if unmapped."""
    line = app_line(episode)
    if line == GENERIC_LINE:
        return caption
    if GENERIC_LINE not in caption:
        raise ValueError(f"{episode}: caption has no generic app line to replace")
    return caption.replace(GENERIC_LINE, line)


def tag_png(short, dest):
    font = ImageFont.truetype(str(FONT), 24)
    label, name = "IN THE APP: ", short.upper()
    lw = font.getlength(label)
    nw = font.getlength(name)
    pad_x, h = 18, 52
    w = int(pad_x * 2 + lw + nw)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2,
                        fill=(8, 16, 30, 190), outline=(251, 191, 36, 210), width=2)
    y = h // 2
    d.text((pad_x, y), label, font=font, fill=(205, 218, 232, 255), anchor="lm")
    d.text((pad_x + lw, y), name, font=font, fill=(251, 191, 36, 255), anchor="lm")
    img.save(dest)
    return w, h


def tag_video(episode, src, dest):
    """Burn the tag into src, write dest. Returns False if the episode is unmapped."""
    hit = lesson_for(episode)
    if not hit:
        return False
    with tempfile.TemporaryDirectory(prefix="eptag-") as work:
        png = pathlib.Path(work) / "tag.png"
        w, _ = tag_png(hit[1], png)
        if TAG_X + w > 1080 - 70:
            raise ValueError(f"{episode}: tag {w}px wide runs off the frame")
        res = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-i", str(png),
             "-filter_complex", f"[0:v][1:v]overlay={TAG_X}:{TAG_Y}:format=auto[v]",
             "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-profile:v", "high",
             "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "copy",
             "-movflags", "+faststart", str(dest)],
            capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(res.stderr[-1500:])
    return True


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    ok = tag_video(sys.argv[1], sys.argv[2], sys.argv[3])
    print("tagged" if ok else "unmapped, not tagged")
