#!/usr/bin/env python3
"""
Stock Learn Easy - Instagram post generator.

Pulls live market news across a few categories (IPOs, big movers, macro
news, plus an evergreen "term of the day"), writes a beginner-friendly
English caption (Stock Learn Easy's voice, fixed disclaimer every time),
and renders a 1080x1080 image card via headless Chrome. Tops up the
`scheduled/` queue to TARGET_QUEUE_DEPTH future slots (2/day), rotating
through categories and skipping headlines/terms already used (tracked
in seen-headlines.json / seen-terms.json).

Runs locally (has Chrome + Keychain); GitHub Actions only runs publish.py.
"""
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from card_check import is_valid_card

ROOT = Path(__file__).resolve().parent
SCHEDULED = ROOT / "scheduled"
PUBLISHED = ROOT / "published"
SEEN_FILE = ROOT / "seen-headlines.json"
SEEN_TERMS_FILE = ROOT / "seen-terms.json"

RSS_FEEDS = [
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
]
DISCLAIMER = "Educational content only. Not financial or investment advice."

# Two slots a day, 12:00 and 18:00 UTC (15:00 and 21:00 Israel).
DAILY_SLOTS_UTC_HOUR = [12, 18]
TARGET_QUEUE_DEPTH = 6  # 3 days worth at 2/day

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# MarketWatch’s feeds mix in personal-advice columns ("The Moneyist",
# written by Quentin Fottrell) that have nothing to do with markets.
# Filter those out rather than post them under a stock-market-education
# brand. The author byline turned out to be a 100% reliable signal for
# this - every off-brand post seen so far is by this one columnist -
# so that’s the primary check now. Keyword matching is kept as a
# backup for when the feed has no author, or a different columnist
# writes similarly personal content.
OFF_BRAND_AUTHORS = {"quentin fottrell"}

# NOTE: apostrophes/quotes in real headlines are the Unicode curly
# forms (‘ ’ “ ”), not ASCII ones, and a headline can
# open with a quoted phrase before the "I" (e.g. "’I’m burned
# out’: I’m constantly helping..."). Both gaps let posts slip
# through undetected on 18-19.9.2026 before the author check existed.
OFF_BRAND_PATTERN = re.compile(
    r"^[\"’‘’“”\s]*(my |i |i[’’]m |i[’’]ve |we |our )|"
    r"\b(husband|wife|boyfriend|girlfriend|in-law|inheritance|divorce|"
    r"mother|father|parent|sibling|cousin|elderly|funeral|estate|alzheimer)\b",
    re.IGNORECASE,
)

# Category rotation, cycled by slot index. "term" is evergreen and
# needs no news source.
CATEGORY_CYCLE = ["ipo", "movers", "macro", "term"]

CATEGORY_META = {
    "ipo": {"tag": "\U0001F680 IPO Watch", "label": "IPO news"},
    "movers": {"tag": "\U0001F4C9\U0001F4C8 Market Movers", "label": "market-moving news"},
    "macro": {"tag": "\U0001F3E6 Macro Watch", "label": "macro/economic news"},
    "news": {"tag": "\U0001F4F0 Today's Market News", "label": "market news"},
    "term": {"tag": "\U0001F4D8 Term of the Day", "label": "term of the day"},
}

CATEGORY_KEYWORDS = {
    "ipo": re.compile(
        r"\bipo\b|initial public offering|goes public|go public|"
        r"public debut|ipo priced|begin(?:s)? trading|files for an? ipo",
        re.IGNORECASE,
    ),
    "movers": re.compile(
        r"shares (?:of|slip|rise|slide|jump|fall|climb|sink|surge|slump|soar|tumble)|"
        r"stock (?:jumps?|soars?|plunges?|tumbles?|surges?|falls?|rises?|slides?|sinks?|slumps?)",
        re.IGNORECASE,
    ),
    "macro": re.compile(
        r"federal reserve|\bfed\b|interest rate|inflation|\bcpi\b|jobs report|"
        r"unemployment|\bgdp\b|rate cut|rate hike|powell|treasury yield|jobless claims|"
        r"manufacturing pmi|services pmi",
        re.IGNORECASE,
    ),
}

# Categories where the headline is reliably about one specific company,
# so it's worth trying to attach its ticker symbol.
TICKER_CATEGORIES = {"movers", "ipo", "news"}

_LEADING_CONNECTORS = {"of", "the", "&", "and"}

# Common sentence-starting words that are capitalized but are not company
# names, and single letters, which are too short to safely match against.
_NOT_A_COMPANY = {
    "a", "an", "the", "more", "why", "how", "what", "new", "this", "these",
    "some", "most", "here", "there", "so", "no", "yes", "us", "it", "its",
}


def extract_company_name(title):
    """Best-effort leading company name from a headline, e.g.
    'Vestas Wind Systems stock slumps as...' -> 'Vestas Wind Systems'."""
    words = title.split()
    picked = []
    for w in words:
        core = w.strip(",.:;\"")
        if not core:
            break
        bare = core.rstrip("'’s").rstrip("'’")
        if bare.lower() in _LEADING_CONNECTORS or (core and core[0].isupper()):
            picked.append(core)
        else:
            break
    while picked and picked[-1].lower() in _LEADING_CONNECTORS:
        picked.pop()
    if not picked:
        return None
    name = " ".join(picked)
    for suffix in ("'s", "’s", "'", "’"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    if not name:
        return None
    first_word = name.split()[0].lower()
    if first_word in _NOT_A_COMPANY or len(first_word) < 3:
        return None
    return name


def lookup_ticker(company_name):
    """Confirm a company name against Yahoo Finance's search endpoint and
    return its ticker symbol, or None if there's no confident match."""
    if not company_name:
        return None
    try:
        q = urllib.parse.quote(company_name)
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=5&newsCount=0"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"WARNING: ticker lookup failed for '{company_name}': {e}")
        return None

    first_word = company_name.split()[0].lower()
    for quote in data.get("quotes", []):
        if quote.get("quoteType") != "EQUITY":
            continue
        name_field = (quote.get("shortname") or quote.get("longname") or "").lower()
        if first_word in re.findall(r"[a-z0-9']+", name_field):
            return quote.get("symbol")
    return None


TERMS = [
    ("P/E Ratio", "Price-to-Earnings ratio: a company's share price divided by its earnings per share. A high P/E often means investors expect strong growth; a low one can mean the stock is undervalued, or that the market has doubts."),
    ("Market Cap", "The total value of a company's shares (share price times shares outstanding). It's how \"big\" a company is on paper, and it decides whether it counts as small-, mid-, or large-cap."),
    ("Dividend", "A portion of a company's profits paid out to shareholders, usually per share and often quarterly. Not every company pays one."),
    ("Bull Market", "A period when prices are rising and investor confidence is high, usually for a sustained stretch, not just a good week."),
    ("Bear Market", "A period when prices are falling, typically defined as a drop of 20% or more from recent highs."),
    ("Volatility", "How much and how fast a stock's price swings up and down. High volatility means bigger, faster moves in either direction."),
    ("Diversification", "Spreading your money across different companies, sectors, or asset types so one bad outcome doesn't sink your whole portfolio."),
    ("ETF", "Exchange-Traded Fund: a basket of stocks or other assets that trades on an exchange like a single stock, often tracking an index."),
    ("Blue Chip", "Shares of large, well-established, financially sound companies with a long track record."),
    ("Short Selling", "Betting a stock's price will fall: you borrow shares, sell them, then aim to buy them back cheaper later and pocket the difference."),
    ("Stock Split", "When a company divides its existing shares into more shares, lowering the price per share without changing the company's total value."),
    ("Market Order vs. Limit Order", "A market order buys or sells immediately at the current price. A limit order only executes at a price you choose, or better."),
    ("Volume", "The number of shares traded in a given period. Unusually high volume often signals unusual interest or momentum."),
    ("52-Week High/Low", "The highest and lowest prices a stock has traded at over the past year, a quick reference point for where it stands now."),
    ("Index Fund", "A fund built to track a market index, like the S&P 500, rather than trying to beat it. Low cost, broad exposure."),
    ("Yield", "The income return on an investment, usually shown as a percentage of the price you paid."),
    ("IPO", "Initial Public Offering: the first time a private company sells shares to the public and starts trading on an exchange."),
    ("Liquidity", "How easily an asset can be bought or sold without moving its price much. Cash is the most liquid asset there is."),
    ("Beta", "A measure of how much a stock tends to move compared to the overall market. Above 1 means more volatile than the market; below 1 means less."),
]


def is_on_brand(headline):
    author = (headline.get("author") or "").strip().lower()
    if author in OFF_BRAND_AUTHORS:
        return False
    return not OFF_BRAND_PATTERN.search(headline["title"])


def load_json_set(path):
    if path.exists():
        return set(json.loads(path.read_text()))
    return set()


def save_json_set(path, data):
    path.write_text(json.dumps(sorted(data), ensure_ascii=False, indent=2))


RSS_NS = {"dc": "http://purl.org/dc/elements/1.1/"}


def fetch_headlines():
    items, seen_titles = [], set()
    for url in RSS_FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_bytes = resp.read()
            root = ET.fromstring(xml_bytes)
        except Exception as e:
            print(f"WARNING: failed to fetch {url}: {e}")
            continue
        for item in root.findall("./channel/item"):
            title = item.find("title").text
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            desc_el = item.find("description")
            creator_el = item.find("dc:creator", RSS_NS)
            items.append({
                "title": title,
                "description": desc_el.text if desc_el is not None else "",
                "link": item.find("link").text,
                "author": creator_el.text if creator_el is not None else "",
            })
    return items


def pick_headline_for_category(category, candidates, seen):
    fresh = [h for h in candidates if h["title"] not in seen and is_on_brand(h)]
    if category in CATEGORY_KEYWORDS:
        matched = [h for h in fresh if CATEGORY_KEYWORDS[category].search(h["title"])]
        if matched:
            return matched[0]
    # Fall back to general market news if nothing matches this category today.
    return fresh[0] if fresh else None


def slot_time_from_name(name):
    try:
        return datetime.strptime(name, "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def next_free_slots(target_depth):
    """UTC datetimes for enough future slots (2/day) to reach target_depth total queued."""
    existing = set()
    now = datetime.now(timezone.utc)
    future_count = 0
    if SCHEDULED.is_dir():
        for p in SCHEDULED.iterdir():
            if not p.is_dir():
                continue
            existing.add(p.name)
            when = slot_time_from_name(p.name)
            if when and when > now:
                future_count += 1
    if PUBLISHED.is_dir():
        existing.update(p.name for p in PUBLISHED.iterdir() if p.is_dir())

    count = max(0, target_depth - future_count)
    slots = []
    day = now.date()
    while len(slots) < count:
        for hour in DAILY_SLOTS_UTC_HOUR:
            candidate = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
            if candidate > now:
                name = candidate.strftime("%Y-%m-%dT%H%M")
                if name not in existing:
                    slots.append(candidate)
                    if len(slots) >= count:
                        break
        day += timedelta(days=1)
    return slots


def next_category_index():
    """Cycle position based on how many posts already exist (scheduled + published)."""
    n = 0
    if SCHEDULED.is_dir():
        n += sum(1 for p in SCHEDULED.iterdir() if p.is_dir())
    if PUBLISHED.is_dir():
        n += sum(1 for p in PUBLISHED.iterdir() if p.is_dir())
    return n % len(CATEGORY_CYCLE)


def make_caption(category, news=None, term=None, ticker=None):
    tag = CATEGORY_META[category]["tag"]
    if category == "term":
        name, definition = term
        body = (
            f"{tag}\n\n"
            f"{name}\n\n"
            f"{definition}\n\n"
            f"Knowing the vocabulary is step one to actually understanding what you're reading."
        )
    else:
        ticker_line = f"${ticker}\n\n" if ticker else ""
        body = (
            f"{tag}\n\n"
            f"{news['title']}\n\n"
            f"{ticker_line}"
            f"{news['description']}\n\n"
            f"Why it matters if you're just starting out: every headline like this "
            f"is a chance to understand how real events move stocks and indexes, "
            f"not just another number to skim past."
        )
    return (
        f"{body}\n\n"
        f"Want to understand the \"why\" behind the headlines? Stock Learn Easy "
        f"teaches it step by step.\n\n"
        f"⚠️ {DISCLAIMER}\n\n"
        f"#StockLearnEasy #StockMarket #Investing #StockNews #FinancialEducation #Stocks"
    )


def render_card_html(category, when_utc, news=None, term=None, ticker=None):
    tag = CATEGORY_META[category]["tag"]
    date_str = when_utc.strftime("%b %d, %Y")
    if category == "term":
        name, definition = term
        headline_html = escape(name)
        sub_html = f'<div class="sub">{escape(definition)}</div>'
    else:
        headline_html = escape(news["title"])
        sub_html = f'<div class="ticker">${escape(ticker)}</div>' if ticker else ""
    return f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    width:1080px; height:1080px;
    font-family:'Inter', sans-serif;
    background: linear-gradient(160deg, #0b1220 0%, #0f2743 55%, #123a5e 100%);
    color:#f5f7fa;
    display:flex; flex-direction:column; justify-content:space-between;
    padding:120px;
  }}
  .tag {{
    display:inline-block;
    background:#22c55e; color:#06210f;
    font-weight:800; font-size:30px;
    padding:14px 34px; border-radius:999px;
    align-self:flex-start;
  }}
  .headline {{
    font-size:64px; font-weight:800; line-height:1.35;
    margin-top:60px;
  }}
  .sub {{
    font-size:30px; font-weight:400; line-height:1.5; opacity:0.85;
    margin-top:28px;
  }}
  .ticker {{
    align-self:flex-start;
    font-size:32px; font-weight:800; color:#4dd8ff;
    background:rgba(77,216,255,0.12);
    border:2px solid rgba(77,216,255,0.4);
    border-radius:10px;
    padding:8px 20px;
    margin-top:30px;
  }}
  .accent {{ color:#4dd8ff; }}
  .footer {{
    border-top:2px solid rgba(255,255,255,0.15);
    padding-top:28px;
  }}
  .footer-row {{
    display:flex; justify-content:space-between; align-items:center;
  }}
  .brand {{ font-size:36px; font-weight:800; }}
  .date {{ font-size:28px; opacity:0.7; }}
  .disclaimer {{
    margin-top:18px; font-size:20px; opacity:0.55; line-height:1.4;
  }}
</style>
</head>
<body>
  <div class="tag">{tag}</div>
  <div class="headline">{headline_html}</div>
  {sub_html}
  <div class="footer">
    <div class="footer-row">
      <div class="brand">Stock <span class="accent">Learn</span> Easy</div>
      <div class="date">{date_str}</div>
    </div>
    <div class="disclaimer">{DISCLAIMER}</div>
  </div>
</body>
</html>
"""


def render_png(html_path: Path, png_path: Path):
    """Render html_path to png_path via headless Chrome, then verify the
    result is actually our card and not a browser error page.

    Always resolves to absolute paths before building the file:// URL,
    regardless of what the caller passed in: a relative path silently
    produces an INVALID file:// URL (the first path segment gets parsed
    as a bogus host), which is exactly what caused a browser error page
    to get published as a real post on 18.9.2026. Chrome exits 0 and
    happily screenshots its own error page, so this validates the
    result rather than trusting the exit code.
    """
    html_path = html_path.resolve()
    png_path = png_path.resolve()
    if not html_path.is_file():
        raise RuntimeError(f"render_png: source HTML does not exist: {html_path}")

    subprocess.run(
        [CHROME, "--headless", "--disable-gpu",
         f"--screenshot={png_path}", "--window-size=1080,1080",
         f"file://{html_path}"],
        check=True, capture_output=True, timeout=30,
    )

    ok, reason = is_valid_card(png_path)
    if not ok:
        raise RuntimeError(f"render_png: rendered image failed validation ({reason}): {png_path}")


def main():
    seen_headlines = load_json_set(SEEN_FILE)
    seen_terms = load_json_set(SEEN_TERMS_FILE)
    candidates = fetch_headlines()

    slots = next_free_slots(TARGET_QUEUE_DEPTH)
    if not slots:
        print("Queue already full.")
        return

    cat_idx = next_category_index()
    made, failed = 0, 0
    for slot in slots:
        category = CATEGORY_CYCLE[cat_idx % len(CATEGORY_CYCLE)]
        cat_idx += 1

        news, term = None, None
        if category == "term":
            available = [t for t in TERMS if t[0] not in seen_terms]
            if not available:
                seen_terms = set()  # exhausted the list, start over
                available = TERMS
            term = available[0]
            seen_terms.add(term[0])
        else:
            news = pick_headline_for_category(category, candidates, seen_headlines)
            if news is None:
                print(f"No fresh headline available for '{category}' or fallback, skipping slot.")
                continue
            seen_headlines.add(news["title"])
            candidates = [h for h in candidates if h["title"] != news["title"]]
            if not CATEGORY_KEYWORDS.get(category, re.compile("$^")).search(news["title"]):
                category = "news"  # fell back to general news, label it honestly

        ticker = None
        if news is not None and category in TICKER_CATEGORIES:
            ticker = lookup_ticker(extract_company_name(news["title"]))
            if ticker is None and news.get("description"):
                # The company name sometimes only appears in the description,
                # e.g. "This is the only cybersecurity stock..." / "Zscaler's
                # stock has missed out on...".
                ticker = lookup_ticker(extract_company_name(news["description"]))

        slot_name = slot.strftime("%Y-%m-%dT%H%M")
        out_dir = SCHEDULED / slot_name
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            html_path = out_dir / "card.html"
            html_path.write_text(render_card_html(category, slot, news=news, term=term, ticker=ticker), encoding="utf-8")
            render_png(html_path, out_dir / "post.png")
            html_path.unlink()

            (out_dir / "caption.txt").write_text(make_caption(category, news=news, term=term, ticker=ticker), encoding="utf-8")
            (out_dir / "source.json").write_text(
                json.dumps({"category": category, "news": news, "term": term, "ticker": ticker}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            # Never leave a half-written or invalid slot behind: an empty
            # scheduled/ directory with no post.png is harmless (publish.py
            # just won't find one to send), a bad post.png published live
            # is the exact failure this whole check exists to prevent.
            print(f"ERROR: failed to build {slot_name} [{category}]: {e}", file=sys.stderr)
            for f in out_dir.glob("*"):
                f.unlink()
            out_dir.rmdir()
            failed += 1
            continue

        made += 1
        label = term[0] if term else news["title"]
        ticker_note = f" (${ticker})" if ticker else ""
        print(f"Queued {slot_name} [{category}]: {label}{ticker_note}")

    save_json_set(SEEN_FILE, seen_headlines)
    save_json_set(SEEN_TERMS_FILE, seen_terms)
    print(f"Made {made} new post(s), {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
