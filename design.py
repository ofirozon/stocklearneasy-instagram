"""The Stock Learn Easy visual language, shared by the carousel and the reel.

Until 29.9.2026 the cards were a generic navy gradient in "Inter", except
Inter was never actually drawn: it was @import-ed from Google Fonts and
headless Chrome took the screenshot before the font arrived, so most cards
went out in the system fallback (Helvetica) and a few in Inter, depending
on the network. They also looked nothing like the app they exist to sell.

The look now comes from the app itself (stock-learn-easy-mobile,
src/theme): DM Serif Display for headings over DM Sans for text, the app's
green pill, its yellow "example" highlight, and the graph-paper grid from
its icon. Fonts and icon ship in assets/ and load from disk, so a render
never depends on the network. Someone who taps through from a post to the
App Store sees the same brand on both sides.

Direction picked out of three on the design canvas "Stock Learn Easy IG
Card Directions" (A. Lesson Card).
"""
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
ICON_URI = (ASSETS / "app-icon.png").as_uri()

# Tokens. Contrast checked against INK_BG: TEXT 17:1, MUTED 9:1, FAINT 6:1.
INK_BG = "#0b1a2e"       # navy ground, darker than the app's #0f172a text colour
PANEL = "#13294a"        # raised navy (CTA strip)
TEXT = "#f8fafc"
MUTED = "#b6c4d6"
FAINT = "#8ea0b8"
GREEN = "#22c55e"        # app success / the "START HERE" pill
GREEN_INK = "#052e16"
GREEN_TEXT = "#4ade80"   # green used as text on navy
HIGHLIGHT = "#facc15"    # app "example" yellow, for the numbers in a hook
# The lesson panel was a solid white card until 30.9.2026, copied from the app's
# white lesson list. On a navy post it read as a bright slab pasted over the
# design, and Ofir named it as the one thing still wrong ("רק הריבוע הלבן עם
# המלל בעייתי"). It is now a translucent lift of the background with a hairline
# border, so the words sit in the design instead of on top of it.
PAPER = "#f8fafc"        # still used where a genuinely light surface is wanted
PAPER_INK = "#0f172a"
# Backlog item 46 (7.10.2026): the dots are the only cue that a carousel has
# more than one slide, and at #52647c and 12px they disappeared at phone size.
DOT_OFF = "#8193ab"

DISCLAIMER = "Educational content only. Not financial or investment advice."

CATEGORY_LABEL = {
    "ipo": "IPO WATCH",
    "movers": "MARKET MOVERS",
    "macro": "MACRO WATCH",
    "news": "MARKET NEWS",
    "term": "TERM OF THE DAY",
}


def font_face_css():
    faces = [
        ("DM Serif Display", 400, "DMSerifDisplay_400Regular.ttf"),
        ("DM Sans", 400, "DMSans_400Regular.ttf"),
        ("DM Sans", 500, "DMSans_500Medium.ttf"),
        ("DM Sans", 700, "DMSans_700Bold.ttf"),
    ]
    return "\n".join(
        f"@font-face {{ font-family:'{fam}'; font-weight:{w}; font-style:normal; "
        f"src:url('{(FONTS / f).as_uri()}') format('truetype'); }}"
        for fam, w, f in faces
    )


SERIF = "'DM Serif Display', Georgia, serif"
SANS = "'DM Sans', 'Helvetica Neue', Arial, sans-serif"

BASE_CSS = f"""
{font_face_css()}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family:{SANS};
  color:{TEXT};
  background-color:{INK_BG};
  background-image:
    radial-gradient(circle at 85% 0%, rgba(59,130,246,0.18), rgba(59,130,246,0) 55%),
    linear-gradient(rgba(148,184,230,0.055) 2px, transparent 2px),
    linear-gradient(90deg, rgba(148,184,230,0.055) 2px, transparent 2px);
  background-size: 100% 100%, 72px 72px, 72px 72px;
  display:flex; flex-direction:column; gap:32px;
  -webkit-font-smoothing:antialiased;
}}
.head {{ display:flex; justify-content:space-between; align-items:center; gap:24px; }}
.lockup {{ display:flex; align-items:center; gap:18px; font-weight:700; }}
.lockup img {{ border-radius:22%; display:block; }}
.pill {{
  background:{GREEN}; color:{GREEN_INK}; font-weight:700;
  letter-spacing:2px; border-radius:999px; white-space:nowrap;
}}
.main {{ flex:1; min-height:0; display:flex; flex-direction:column; justify-content:center; overflow:hidden; }}
.serif {{ font-family:{SERIF}; font-weight:400; text-wrap:balance; }}
.hl {{ color:{HIGHLIGHT}; }}
.eyebrow {{ font-weight:700; letter-spacing:3px; }}
.muted {{ color:{MUTED}; }}
.faint {{ color:{FAINT}; }}
.lesson {{
  background:rgba(255,255,255,0.055); color:{TEXT}; border-radius:28px;
  border:1px solid rgba(255,255,255,0.09);
  min-height:0; overflow:hidden;
}}
.lesson b {{ font-weight:700; }}
.cta {{ display:flex; align-items:center; background:{PANEL}; border-radius:28px; }}
.cta img {{ border-radius:22%; display:block; flex-shrink:0; }}
.cta .t1 {{ font-weight:700; }}
.cta .t2 {{ color:{MUTED}; }}
.foot {{ display:flex; justify-content:space-between; align-items:center; gap:24px; }}
.dots {{ display:flex; gap:14px; align-items:center; }}
.dots span {{ width:16px; height:16px; border-radius:8px; background:{DOT_OFF}; }}
.dots span.on {{ width:56px; background:{TEXT}; }}
.chg {{ font-weight:700; border-radius:999px; white-space:nowrap; font-variant-numeric:tabular-nums; }}
.chg.up {{ color:{GREEN_INK}; background:{GREEN}; }}
.chg.down {{ color:#2a0a0a; background:#f87171; }}
.num {{ font-variant-numeric:tabular-nums; }}
"""

# Shrinks any [data-fit] element's font until its box stops overflowing.
# The size tiers in the Python below already pick a size that fits typical
# copy; this is the safety net for the unusually long one, so text is never
# cut off. It waits for the local fonts first, since DM Sans and the
# fallback measure differently.
FIT_JS = """
<script>
(function(){
  function fit(){
    document.querySelectorAll('[data-fit]').forEach(function(el){
      var box = el.closest('[data-fit-box]') || el;
      var size = parseFloat(getComputedStyle(el).fontSize);
      var min = parseFloat(el.getAttribute('data-fit')) || 20;
      var guard = 0;
      while ((box.scrollHeight > box.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)
             && size > min && guard++ < 80) {
        size -= 2; el.style.fontSize = size + 'px';
      }
    });
  }
  if (document.fonts && document.fonts.ready) { document.fonts.ready.then(fit); }
  window.addEventListener('load', fit);
})();
</script>
"""

# Numbers in a hook are what stops a thumb: "4-month high", "10x", "$50",
# "43.2", "26%". They get the app's yellow. Matched on the raw text and
# escaped piece by piece, because escaping first would turn an apostrophe
# into &#x27; and the 27 in it would get highlighted.
_NUMBER = re.compile(
    r"\$?\d[\d,]*(?:\.\d+)?"
    r"(?:\s?(?:%|x|trillion|billion|million|bps)\b|%|x\b)?"
    r"(?:-(?:month|year|week|day|decade)s?)?",
    re.IGNORECASE,
)


def highlight_numbers(text):
    out, last = [], 0
    for m in _NUMBER.finditer(text):
        out.append(escape(text[last:m.start()]))
        out.append(f'<span class="hl">{escape(m.group(0))}</span>')
        last = m.end()
    out.append(escape(text[last:]))
    return "".join(out)


def size_for(text, tiers):
    """Pick a font size from [(max_chars, px), ...] by text length."""
    n = len(text or "")
    for max_chars, px in tiers:
        if n <= max_chars:
            return px
    return tiers[-1][1]


def dots_html(position, total):
    return '<div class="dots">' + "".join(
        f'<span class="{"on" if i == position else ""}"></span>' for i in range(1, total + 1)
    ) + "</div>"


def page(width, height, padding, body_html):
    return f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<style>{BASE_CSS}
body {{ width:{width}px; height:{height}px; padding:{padding}; }}
</style>
</head>
<body>
{body_html}
{FIT_JS}
</body>
</html>
"""
