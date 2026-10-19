#!/usr/bin/env python3
"""Give a reel-only slot something to publish if the reel fails.

Backlog item 68 (19.10.2026). A news or term reel always has its carousel
behind it, so publish.py falls back to the cards when the video container
errors. An episode reel (queue_episode.py) and an episode re-post (repost.py)
had only cover.jpg and the video: if Instagram rejected the video, publish.py
fell through to publish_single, found no post.png, and the slot was lost.

This writes post.png: the centre 4:5 of the 9:16 cover, which is the frame
render.py composes for the grid anyway, with the fixed disclaimer as fine
print at the bottom so the still carries it like every other card. It is
checked against card_check before it is kept; a still that fails the gate is
deleted rather than left for the cloud to reject the whole slot over.

    python fallback_still.py <slot_dir>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import design
from card_check import is_valid_card

ROOT = Path(__file__).resolve().parent
FONT = ROOT / "assets" / "fonts" / "DMSans_500Medium.ttf"
W, H = 1080, 1350
# The cover's lockup sits near the top, so the crop leans up a little rather
# than taking the exact centre, which clipped the logo.
UPWARD_BIAS = 60


def write_fallback_still(slot_dir: Path) -> bool:
    cover = slot_dir / "cover.jpg"
    out = slot_dir / "post.png"
    if not cover.is_file():
        print(f"{slot_dir.name}: no cover.jpg, no fallback still", file=sys.stderr)
        return False

    im = Image.open(cover).convert("RGB")
    if im.width != W:
        im = im.resize((W, round(im.height * W / im.width)))
    if im.height < H:
        print(f"{slot_dir.name}: cover too short for a 4:5 still", file=sys.stderr)
        return False
    top = max((im.height - H) // 2 - UPWARD_BIAS, 0)
    im = im.crop((0, top, W, top + H))

    draw = ImageDraw.Draw(im, "RGBA")
    draw.rectangle((0, H - 64, W, H), fill=(11, 18, 32, 215))
    font = ImageFont.truetype(str(FONT), 18)
    text = design.DISCLAIMER
    tw = draw.textlength(text, font=font)
    draw.text(((W - tw) / 2, H - 42), text, font=font, fill=design.FAINT)
    im.save(out)

    ok, reason = is_valid_card(out)
    if not ok:
        out.unlink(missing_ok=True)
        print(f"{slot_dir.name}: fallback still failed the card gate ({reason})",
              file=sys.stderr)
        return False
    return True


if __name__ == "__main__":
    sys.exit(0 if write_fallback_still(Path(sys.argv[1])) else 1)
