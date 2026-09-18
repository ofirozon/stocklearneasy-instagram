"""Shared safety check, used by both generate.py and publish.py.

Rejects any card image that isn't actually our rendered card - most
importantly a browser's own "page not available" error screen, which is
what got published on 18.9.2026 after a script wrote a relative
file:// path. Chrome happily screenshots its own error page and exits
0, so nothing about that failure was loud until it was already live.

Two independent checks, either one is enough to catch a bad render:
- exact expected image size
- corners sampled dark: our card background is a dark navy gradient
  everywhere; a blank/error page is white. A real card's brightest
  corner tops out well under 100; anything above 200 is not our card.
"""
from PIL import Image

EXPECTED_SIZE = (1080, 1080)
CORNERS = [(5, 5), (1075, 5), (5, 1075), (1075, 1075)]
MAX_CORNER_BRIGHTNESS = 200


def is_valid_card(png_path):
    """Returns (True, "ok") or (False, reason)."""
    try:
        im = Image.open(png_path)
        im.load()
    except Exception as e:
        return False, f"unreadable image: {e}"

    if im.size != EXPECTED_SIZE:
        return False, f"unexpected size {im.size}, expected {EXPECTED_SIZE}"

    im = im.convert("RGB")
    for pt in CORNERS:
        r, g, b = im.getpixel(pt)
        brightness = (r + g + b) / 3
        if brightness > MAX_CORNER_BRIGHTNESS:
            return False, (
                f"corner {pt} is too bright (rgb={r},{g},{b}) - looks like a "
                f"blank/error page, not our rendered card"
            )
    return True, "ok"
