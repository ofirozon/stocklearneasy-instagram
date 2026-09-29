"""Real market data for Stock Learn Easy cards.

Until 28.9.2026 every card was the same dark-navy rectangle with text on
it: 42 posts, zero charts, zero numbers. A finance account whose images
contain no data looks like a quote account, and it gives a scroller no
reason to stop. This module fetches an actual price series and renders it
as inline SVG, so a card can show the thing it is talking about.

Inline SVG on purpose: the cards are rendered by headless Chrome from a
local file:// HTML, and anything fetched over the network at render time
(a chart image service, a JS charting library from a CDN) is one outage
away from publishing a blank card. SVG we build ourselves always draws.

Source is Yahoo Finance's chart endpoint. Stooq was the other candidate
and is now behind a JavaScript proof-of-work challenge, so it cannot be
used from a script at all.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CHART_API = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

UP = "#22c55e"
DOWN = "#f87171"


def fetch_series(symbol, rng="6mo", interval="1d", timeout=20):
    """Return a dict of series + summary stats, or None if unavailable.

    Never raises: a missing chart must degrade to a normal text card, it
    must never take down the whole post build.
    """
    url = CHART_API.format(symbol=urllib.parse.quote(symbol)) + f"?range={rng}&interval={interval}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        stamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception:
        return None

    points = [(t, c) for t, c in zip(stamps, closes) if c is not None]
    if len(points) < 10:
        return None

    values = [c for _, c in points]
    first, last = values[0], values[-1]
    if first <= 0:
        return None

    return {
        "symbol": meta.get("symbol", symbol),
        # Yahoo reports currency "USD" for indices and yields too, which is
        # how "$5.25" ended up next to a 5.25% Treasury yield in testing.
        # An index is points and a yield is a percentage, neither is money.
        "currency": _display_unit(meta.get("symbol", symbol), meta.get("currency", "USD")),
        "points": points,
        "values": values,
        "first": first,
        "last": last,
        "low": min(values),
        "high": max(values),
        "change_pct": (last - first) / first * 100.0,
        "range_label": _range_label(rng),
        "start": datetime.fromtimestamp(points[0][0], timezone.utc),
        "end": datetime.fromtimestamp(points[-1][0], timezone.utc),
    }


YIELD_SYMBOLS = {"^TNX", "^FVX", "^TYX", "^IRX"}


def _display_unit(symbol, currency):
    if symbol in YIELD_SYMBOLS:
        return "PCT"
    if symbol.startswith("^") or symbol.endswith(".NYB"):
        return "POINTS"
    return currency


def _range_label(rng):
    return {
        "1mo": "past month",
        "3mo": "past 3 months",
        "6mo": "past 6 months",
        "1y": "past year",
        "2y": "past 2 years",
        "5y": "past 5 years",
    }.get(rng, rng)


def fmt_price(value, currency="USD"):
    if currency == "PCT":
        return f"{value:,.2f}%"
    sign = "$" if currency == "USD" else ""
    if currency == "POINTS":
        sign = ""
    if value >= 1000:
        return f"{sign}{value:,.0f}"
    if value >= 10:
        return f"{sign}{value:,.2f}"
    return f"{sign}{value:,.3f}".rstrip("0").rstrip(".")


def fmt_pct(value):
    return f"{value:+.1f}%"


def sparkline_svg(series, width=840, height=380):
    """An area chart of the close series, as a self-contained SVG string.

    Drawn with a flat baseline fill rather than a bare line: at Instagram
    card size a 2px line on a dark background disappears in the feed
    thumbnail, the filled area survives the downscale.
    """
    values = series["values"]
    lo, hi = min(values), max(values)
    span = hi - lo or (hi or 1) * 0.01
    # pad_bottom has to clear two rows, not one: the axis-low label sits just
    # under the plot and the date row sits under that. At 52 they collided.
    pad_top, pad_bottom = 24, 82
    plot_h = height - pad_top - pad_bottom

    n = len(values)
    step = width / (n - 1)
    coords = [
        (i * step, pad_top + plot_h - ((v - lo) / span) * plot_h)
        for i, v in enumerate(values)
    ]

    line = " ".join(
        ("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords)
    )
    area = line + f" L{width:.1f},{pad_top + plot_h:.1f} L0,{pad_top + plot_h:.1f} Z"

    rising = series["change_pct"] >= 0
    color = UP if rising else DOWN
    last_x, last_y = coords[-1]

    grid = "".join(
        f'<line x1="0" y1="{pad_top + plot_h * f:.1f}" x2="{width}" '
        f'y2="{pad_top + plot_h * f:.1f}" stroke="rgba(255,255,255,0.10)" stroke-width="2"/>'
        for f in (0.0, 0.5, 1.0)
    )

    start_label = series["start"].strftime("%b %Y")
    end_label = series["end"].strftime("%b %Y")

    return f"""<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{color}" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>
    </linearGradient>
  </defs>
  {grid}
  <path d="{area}" fill="url(#fill)"/>
  <path d="{line}" fill="none" stroke="{color}" stroke-width="5"
        stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="11" fill="{color}"/>
  <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="20" fill="{color}" opacity="0.28"/>
  <text x="0" y="{height - 14}" fill="rgba(255,255,255,0.55)"
        font-family="Inter, sans-serif" font-size="26">{start_label}</text>
  <text x="{width}" y="{height - 14}" text-anchor="end" fill="rgba(255,255,255,0.55)"
        font-family="Inter, sans-serif" font-size="26">{end_label}</text>
  <text x="0" y="{pad_top - 4}" fill="rgba(255,255,255,0.45)"
        font-family="Inter, sans-serif" font-size="24">{fmt_price(hi, series['currency'])}</text>
  <text x="0" y="{pad_top + plot_h + 30}" fill="rgba(255,255,255,0.45)"
        font-family="Inter, sans-serif" font-size="24">{fmt_price(lo, series['currency'])}</text>
</svg>"""


# Macro stories have no ticker, but they do have a market the reader can
# see. These are the proxies we are willing to show, keyed by what the
# headline is actually about. Anything not on this list gets no chart at
# all - an unrelated index next to an unrelated story is worse than text.
MACRO_PROXIES = [
    (("inflation", "cpi", "prices", "cost of living", "consumer price"), "^TNX",
     "10-year Treasury yield", "Bond yields track what markets expect inflation to do"),
    (("fed", "interest rate", "rate cut", "rate hike", "fomc", "powell"), "^TNX",
     "10-year Treasury yield", "The yield moves before and after every Fed decision"),
    (("oil", "crude", "opec", "gasoline", "energy prices"), "CL=F",
     "Crude oil", "The price the whole energy complex is priced off"),
    (("gold", "safe haven", "precious metal"), "GC=F",
     "Gold", "Where money goes when it wants out of risk"),
    (("dollar", "currency", "forex", "exchange rate"), "DX-Y.NYB",
     "US dollar index", "A stronger dollar makes everything priced in dollars pricier abroad"),
    (("volatility", "vix", "fear gauge", "market swings", "selloff", "sell-off"), "^VIX",
     "VIX", "Wall Street's fear gauge: how big a swing traders are bracing for"),
    (("recession", "jobs", "unemployment", "payroll", "gdp", "consumer confidence",
      "economy", "tariff", "trade war", "pmi", "manufacturing", "retail sales",
      "housing", "growth"), "^GSPC",
     "S&P 500", "The market's running vote on the US economy"),
]

# A story about Europe should not be illustrated with an American index. When
# the headline is clearly about another region, the same "what does the market
# think" chart is swapped for that region's benchmark.
REGION_INDEX = [
    (("germany", "german", "eurozone", "euro zone", "europe", "european", "ecb",
      "france", "french", "italy", "spain"), "^STOXX50E", "Euro Stoxx 50",
     "Europe's benchmark index, the market's running vote on the European economy"),
    (("japan", "japanese", "boj", "tokyo"), "^N225", "Nikkei 225",
     "Japan's benchmark index, the market's running vote on the Japanese economy"),
    (("uk", "britain", "british", "bank of england", "london"), "^FTSE", "FTSE 100",
     "The UK's benchmark index, the market's running vote on the British economy"),
]

# Some terms are far better shown than defined. Only the ones where the chart
# IS the definition are listed; a P/E ratio has no honest single chart, so it
# stays a text card.
TERM_PROXIES = {
    "Volatility": ("^VIX", "VIX", "The index that measures exactly this: expected swings"),
    "Bear Market": ("^GSPC", "S&P 500", "The index those 20% drops are usually measured on"),
    "Bull Market": ("^GSPC", "S&P 500", "The index those long climbs are usually measured on"),
    "ETF": ("SPY", "SPY", "The oldest US ETF, one share of the whole S&P 500"),
    "Blue Chip": ("^DJI", "Dow Jones", "Thirty of the bluest chips America has, in one index"),
    "Index Fund": ("^GSPC", "S&P 500", "The index most index funds are built to copy"),
}


def macro_proxy(headline):
    """Pick an honest chart for a macro story, or None."""
    text = (headline or "").lower()
    for keywords, symbol, label, why in MACRO_PROXIES:
        if not any(k in text for k in keywords):
            continue
        # Region override only applies to the broad "what does the market
        # think" proxy; oil, gold and the dollar are global prices already.
        if symbol == "^GSPC":
            for region_keys, r_symbol, r_label, r_why in REGION_INDEX:
                if any(k in text for k in region_keys):
                    return {"symbol": r_symbol, "label": r_label, "why": r_why}
        return {"symbol": symbol, "label": label, "why": why}
    return None


def term_proxy(term_name):
    """A chart that illustrates a term of the day, or None."""
    entry = TERM_PROXIES.get(term_name)
    if not entry:
        return None
    symbol, label, why = entry
    return {"symbol": symbol, "label": label, "why": why}
