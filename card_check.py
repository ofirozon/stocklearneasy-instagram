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

# 4:5 since 16.10.2026. The square size stays legal: the 16.10 switch left
# one square slot in the queue and this gate threw it into rejected/, losing
# the 16.10 18:00 post. Both are real Instagram feed sizes; the gate exists to
# catch an error page, not to enforce a format change on cards already queued.
EXPECTED_SIZES = {(1080, 1350), (1080, 1080)}
MAX_CORNER_BRIGHTNESS = 200
# The light "paper" layout (templates/news_pro, 24.11.2026) has a warm off-white ground, #fbf8f1. A browser error page is
# pure white (255,255,255) with grey text, so a corner is accepted only if it is dark (the original navy cards) or
# within LIGHT_TOLERANCE of this exact paper colour on every channel. White fails, as before.
LIGHT_CARD_BG = (251, 248, 241)
LIGHT_TOLERANCE = 3


def is_valid_card(png_path):
    """Returns (True, "ok") or (False, reason)."""
    try:
        im = Image.open(png_path)
        im.load()
    except Exception as e:
        return False, f"unreadable image: {e}"

    if im.size not in EXPECTED_SIZES:
        return False, f"unexpected size {im.size}, expected one of {sorted(EXPECTED_SIZES)}"

    im = im.convert("RGB")
    w, h = im.size
    for pt in [(5, 5), (w - 5, 5), (5, h - 5), (w - 5, h - 5)]:
        r, g, b = im.getpixel(pt)
        brightness = (r + g + b) / 3
        paper = all(abs(v - ref) <= LIGHT_TOLERANCE for v, ref in zip((r, g, b), LIGHT_CARD_BG))
        if brightness > MAX_CORNER_BRIGHTNESS and not paper:
            return False, (
                f"corner {pt} is too bright (rgb={r},{g},{b}) - looks like a "
                f"blank/error page, not our rendered card"
            )
    return True, "ok"
