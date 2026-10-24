#!/usr/bin/env python3
"""Backlog item 75 (24.10.2026): one post a week is the app itself.

Every other post teaches a market idea and mentions the app in one caption
line. Nothing on the account ever showed what is inside the app, so a reader
who liked a post had no picture of what "the full lesson" would look like.
The Friday 18:00 carousel is now two slides cut from the App Store's own
screenshots: one feature (rotating weekly through five), then the "No account.
No email." closer. The caption explains that one feature.

Screenshots come from the live App Store listing (iTunes lookup API), so when
the listing changes, the posts follow. A copy sits in assets/app-store/ and is
used when the lookup fails, so a network blip never costs the slot. The copy
is fixed text written here, not by the model: every claim in it is printed on
the screenshot it sits under (44 lessons, 82 terms, quiz, no account).

    python app_post.py <slot_dir>     build one slot, for testing
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import design
from card_check import is_valid_card

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "assets" / "app-store"
SANS = ROOT / "assets" / "fonts" / "DMSans_500Medium.ttf"
APP_ID = "6761296421"
LOOKUP = f"https://itunes.apple.com/lookup?id={APP_ID}"
W, H = 1080, 1350
STRIP = 92  # bottom band that carries the disclaimer

# Friday, the evening (18:00 UTC) carousel. Monday, Wednesday and Saturday
# 18:00 are already weekly tests (chart-first, question hook, plain hook).
def wants_app_post(slot):
    return slot is not None and slot.weekday() == 4 and slot.hour >= 15


# Screenshot number (1-based, App Store order) -> what the caption says.
FEATURES = [
    (1, "Investing, explained from zero.",
     "44 lessons in plain English, in six learning paths: Stock Market Basics, "
     "Fundamental Analysis, Stock Valuation, Risk Management, Technical "
     "Analysis and more. Start at lesson one, no background needed."),
    (2, "10 minutes, one lesson done.",
     "Every lesson is short enough for a coffee break, and ends in a quick "
     "quiz so it actually sticks."),
    (3, "Reads like a story, not a textbook.",
     "Real examples instead of formulas thrown at you. What a stock is, why "
     "companies issue them, and what the market does with them."),
    (4, "82 market terms, one tap away.",
     "Saw a word in the news you did not know? Search the glossary, read a "
     "two-minute explainer, move on."),
    (5, "Everything in one app.",
     "6 learning paths, 44 lessons, 82 glossary terms, a quiz after every "
     "lesson, XP levels and streaks, and notes with bookmarks and highlights."),
]
CLOSER = 6
TAGS = ["#investingforbeginners", "#stockmarket", "#personalfinance", "#learninvesting"]


def feature_for(slot):
    return FEATURES[slot.isocalendar()[1] % len(FEATURES)]


def refresh_cache():
    """Pull the current screenshots into assets/app-store/. Best effort."""
    try:
        with urllib.request.urlopen(LOOKUP, timeout=20) as r:
            urls = json.load(r)["results"][0]["screenshotUrls"]
    except Exception as e:
        print(f"app_post: lookup failed ({e}), using cached screenshots", file=sys.stderr)
        return False
    CACHE.mkdir(parents=True, exist_ok=True)
    for i, url in enumerate(urls, 1):
        big = url.rsplit("/", 1)[0] + "/1290x2796bb.png"
        try:
            with urllib.request.urlopen(big, timeout=30) as r:
                data = r.read()
            tmp = CACHE / f"{i:02d}.tmp"
            tmp.write_bytes(data)
            im = Image.open(tmp).convert("RGB")
            im.resize((W, round(im.height * W / im.width))).save(CACHE / f"{i:02d}.png")
            tmp.unlink()
        except Exception as e:
            print(f"app_post: screenshot {i} failed ({e}), keeping cached copy", file=sys.stderr)
    return True


def _shot(n):
    path = CACHE / f"{n:02d}.png"
    im = Image.open(path).convert("RGB")
    if im.width != W:
        im = im.resize((W, round(im.height * W / im.width)))
    return im


def _disclaimer_strip(card):
    """Navy band at the bottom with the fixed disclaimer, faded in from above
    so it does not read as a bar pasted over the phone."""
    draw = ImageDraw.Draw(card)
    bg = tuple(int(design.INK_BG[i:i + 2], 16) for i in (1, 3, 5))
    fade = 120
    top = H - STRIP - fade
    for y in range(fade):
        a = y / fade
        row = card.crop((0, top + y, W, top + y + 1))
        card.paste(Image.blend(row, Image.new("RGB", row.size, bg), a), (0, top + y))
    draw.rectangle((0, H - STRIP, W, H), fill=bg)
    font = ImageFont.truetype(str(SANS), 26)
    text = design.DISCLAIMER
    tw = draw.textlength(text, font=font)
    draw.text(((W - tw) / 2, H - STRIP + (STRIP - 26) / 2 - 4), text, font=font,
              fill=design.FAINT)
    return card


def feature_card(n):
    """The screenshot at full width, cut below the headline and the top of the
    phone. Headline at full size is what reads in the grid and the feed."""
    shot = _shot(n)
    return _disclaimer_strip(shot.crop((0, 0, W, H)))


def closer_card():
    """Screenshot 6 is mostly empty navy around the icon, so it is cut in two:
    the headline from the top, the icon and wordmark from the middle."""
    shot = _shot(CLOSER)
    sh = shot.height
    # Headline only: the subtitle under it is said in the caption, and keeping
    # it leaves no room for the icon block without a crowded join.
    head_end = 0.188
    head = shot.crop((0, 0, W, round(sh * head_end)))
    mid = shot.crop((0, round(sh * 0.475), W, round(sh * 0.765)))
    mid_top = H - STRIP - 60 - mid.height
    # Ground: the screenshot's own left-edge gradient, so the two cut pieces
    # sit on the colour they had in the original and the joins disappear.
    edge = shot.crop((0, 0, 1, sh)).convert("RGB")
    card = Image.new("RGB", (W, H))
    for y in range(H):
        src = round(y * sh * head_end / head.height) if y < head.height else \
            round(sh * head_end + (y - head.height) * (sh * (0.76 - head_end)) / (H - head.height))
        card.paste(edge.getpixel((0, max(0, min(sh - 1, src)))), (0, y, W, y + 1))
    for piece, top, feather in ((head, 0, 16), (mid, mid_top, 70)):
        mask = Image.new("L", piece.size, 255)
        d = ImageDraw.Draw(mask)
        for i in range(feather):
            a = round(255 * i / feather)
            if top > 0:
                d.line((0, i, W, i), fill=a)
            d.line((0, piece.height - 1 - i, W, piece.height - 1 - i), fill=a)
        card.paste(piece, (0, top), mask)
    return _disclaimer_strip(card)


def caption(slot):
    _, title, body = feature_for(slot)
    return (
        f"{title}\n\n"
        f"{body}\n\n"
        "This is Stock Learn Easy, the app behind this account. No account, no "
        "email: open it and start lesson one. Pro unlocks the advanced paths.\n\n"
        "📲 Free to start, on the App Store. Link in bio.\n\n"
        f"⚠️ {design.DISCLAIMER}\n\n"
        f"{' '.join(['#StockLearnEasy', *TAGS])}"
    )


def build(out_dir: Path, slot):
    """Write post_1.png, post_2.png, caption.txt and source.json. Raises on a
    card that fails the gate, so generate.py drops the slot like any other."""
    refresh_cache()
    n, title, body = feature_for(slot)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("post_*.png"):
        old.unlink()
    cards = [feature_card(n), closer_card()]
    for i, card in enumerate(cards, 1):
        path = out_dir / f"post_{i}.png"
        card.save(path)
        ok, reason = is_valid_card(path)
        if not ok:
            raise ValueError(f"app card {i} failed card_check: {reason}")
    (out_dir / "caption.txt").write_text(caption(slot), encoding="utf-8")
    record = {
        "category": "app",
        "news": None,
        "term": None,
        "ticker": None,
        "copy": {"hook": title, "explain": body, "tags": TAGS},
        "slides": [f"app-store-{n:02d}", f"app-store-{CLOSER:02d}"],
        "chart": None,
        "backlog_items": [75],
        "variant": "app-screenshot",
    }
    (out_dir / "source.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


if __name__ == "__main__":
    d = Path(sys.argv[1])
    when = datetime.strptime(d.name, "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc)
    print(build(d, when)["copy"]["hook"])
