#!/usr/bin/env python3
"""Write story.png: a 9:16 Story pointing at the slot's feed post.

Backlog item 80 (22.10.2026). Stories sit at the top of a follower's app,
above the feed, and reach followers whose feed never shows the post. publish.py
posts this as a Story right after the feed post goes live.

The Story is the slot's first card (already gated by card_check, and carrying
the fixed disclaimer), centred on the navy ground with a short "new post" line
above it. Built here, at queue time, so the cloud publisher needs no rendering
and only fetches a file from the repo like it does for the cards.

The API cannot attach a link or a "new post" sticker, so the line names where
to go instead: the profile, where the post is the top square.

    python story.py <slot_dir>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import design

ROOT = Path(__file__).resolve().parent
SERIF = ROOT / "assets" / "fonts" / "DMSerifDisplay_400Regular.ttf"
SANS = ROOT / "assets" / "fonts" / "DMSans_500Medium.ttf"
W, H = 1080, 1920
CARD_W = 960
STORY_SIZE = (W, H)


def _font(path: Path, size: int):
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.truetype(str(SANS), size)


def source_card(slot_dir: Path):
    """The image the feed post opens on: slide one, else the single still."""
    for name in ("post_1.png", "post.png"):
        if (slot_dir / name).is_file():
            return slot_dir / name
    return None


def write_story(slot_dir: Path) -> bool:
    """Never raises: the Story is a bonus, and generate.py deletes a slot
    whose build throws, so a font or PIL hiccup here must not cost the post."""
    try:
        return _write_story(slot_dir)
    except Exception as e:
        (slot_dir / "story.png").unlink(missing_ok=True)
        print(f"{slot_dir.name}: story build failed ({e})", file=sys.stderr)
        return False


def _write_story(slot_dir: Path) -> bool:
    out = slot_dir / "story.png"
    card_path = source_card(slot_dir)
    if card_path is None:
        out.unlink(missing_ok=True)
        print(f"{slot_dir.name}: no card, no story", file=sys.stderr)
        return False

    card = Image.open(card_path).convert("RGB")
    card = card.resize((CARD_W, round(card.height * CARD_W / card.width)))

    im = Image.new("RGB", STORY_SIZE, design.INK_BG)
    draw = ImageDraw.Draw(im)

    head = _font(SERIF, 72)
    sub = _font(SANS, 34)
    title, hint = "New post", "Tap our name to see it"
    gap = 56
    block = 72 + 18 + 34 + gap + card.height
    top = max((H - block) // 2, 80)

    tw = draw.textlength(title, font=head)
    draw.text(((W - tw) / 2, top), title, font=head, fill=design.TEXT)
    hw = draw.textlength(hint, font=sub)
    draw.text(((W - hw) / 2, top + 72 + 18), hint, font=sub, fill=design.GREEN_TEXT)

    card_top = top + 72 + 18 + 34 + gap
    im.paste(card, ((W - CARD_W) // 2, card_top))
    draw.rectangle(((W - CARD_W) // 2 - 2, card_top - 2,
                    (W + CARD_W) // 2 + 1, card_top + card.height + 1),
                   outline=design.PANEL, width=2)
    im.save(out)

    ok, reason = is_valid_story(out)
    if not ok:
        out.unlink(missing_ok=True)
        print(f"{slot_dir.name}: story failed its check ({reason})", file=sys.stderr)
        return False
    return True


def is_valid_story(path: Path):
    """The story is made from a card that already passed card_check, so this
    only guards the composition itself: right size, and not a blank frame."""
    try:
        im = Image.open(path)
    except Exception as e:
        return False, f"unreadable ({e})"
    if im.size != STORY_SIZE:
        return False, f"size {im.size}, want {STORY_SIZE}"
    lo, hi = im.convert("L").getextrema()
    if hi - lo < 60:
        return False, "almost no contrast, looks blank"
    return True, "ok"


if __name__ == "__main__":
    sys.exit(0 if write_story(Path(sys.argv[1])) else 1)
