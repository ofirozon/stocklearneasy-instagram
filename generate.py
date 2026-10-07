#!/usr/bin/env python3
"""
Stock Learn Easy - Instagram post generator.

Pulls live market news across a few categories (IPOs, big movers, macro
news, plus an evergreen "term of the day"), writes a beginner-friendly
English caption (Stock Learn Easy's voice, fixed disclaimer every time),
and renders a 1080x1080 carousel via headless Chrome: hook, then a real
price chart when the story has one to show, then the concept, then the
takeaway. Tops up the `scheduled/` queue to TARGET_QUEUE_DEPTH future
slots (2/day), rotating through categories and skipping headlines/terms
already used (tracked in seen-headlines.json / seen-terms.json).

One slot a day is built as a Reel instead (see reel.py): a static
carousel from an account with no followers is shown to almost nobody,
and Reels are the only surface on Instagram that still reaches people
who don't follow you.

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

import copy_check
import design
import market_data
import reel
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
DISCLAIMER = design.DISCLAIMER

# Two slots a day, 12:00 and 18:00 UTC (15:00 and 21:00 Israel).
DAILY_SLOTS_UTC_HOUR = [12, 18]
TARGET_QUEUE_DEPTH = 6  # 3 days worth at 2/day

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Item 84: which rules from instagram-backlog.md this generation is running
# under, stamped into every source.json. When a week of numbers comes back,
# this is what says which change the week was testing. Update it when the
# generator's rules change, not when the code is merely refactored.
BACKLOG_ITEMS = [6, 7, 15, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
                 33, 34, 35, 36, 37, 38, 16, 84, 95, 13, 14, 46]

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
        # A fund named after a company is not the company. On 29.9.2026 an
        # Anthropic IPO story got "$ANTW" (the "Anthropic AI Lab Ecosystem
        # ETF") and a chart of that ETF presented as the market's view of
        # Anthropic. A private company has no ticker; better no chart.
        if re.search(r"\b(etf|fund|trust|tokenized|index|etn)\b", name_field):
            continue
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


def pick_headline_for_category(category, candidates, seen, recent=()):
    """The first fresh, on-brand, not-already-covered headline for a category.

    `recent` is the last 14 posts; a candidate that overlaps one of them on two
    distinctive words is skipped even though its exact title is new, because
    the same event reaches these feeds under three different headlines (item
    36). The topic check is applied inside the category match AND inside the
    fallback, so a duplicate cannot sneak in through the general-news path.
    """
    fresh = [h for h in candidates if h["title"] not in seen and is_on_brand(h)]

    def first_fresh_topic(pool):
        for h in pool:
            dup = is_duplicate_topic(h, recent)
            if dup:
                print(f"  skipping '{h['title'][:50]}': already covered by {dup}")
                continue
            return h
        return None

    if category in CATEGORY_KEYWORDS:
        matched = [h for h in fresh if CATEGORY_KEYWORDS[category].search(h["title"])]
        picked = first_fresh_topic(matched)
        if picked:
            return picked
    # Fall back to general market news if nothing matches this category today.
    return first_fresh_topic(fresh)


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


# --- Per-post copy -----------------------------------------------------------
#
# Until 28.9.2026 every post was assembled from fixed template strings, so a
# three-slide carousel carried exactly one piece of information: a headline
# copied off the RSS feed. Slide 2 reprinted the headline and added the same
# sentence every time ("Why it matters if you're just starting out: every
# headline like this is a chance to..."), which is true of literally any
# headline and therefore teaches nothing. An account that promises the "why"
# behind the news never once explained a why.
#
# Copy is now written per post, against the specific story, by claude -p on
# this Mac, the same way the other scheduled jobs here call it. If that call
# fails for any reason the old templates still run, because a dull post beats
# an empty queue.

COPY_TIMEOUT = 120

# Ofir's feedback on 2026-09-30, by voice: the cards now look professional, and
# what is left is the words. "רואים מלל לפעמים ארוך מדי" (the text is sometimes
# too long) and the slides do not carry each other. A card is read in about a
# second and a half while someone is scrolling, so a 320-character paragraph is
# not read at all, it is scrolled past. These rules go into both prompts and are
# enforced in code below, because a limit that only lives in a prompt is a
# suggestion.
_COPY_FLOW_RULES = """The four slides are read in order, in about six seconds total, so they have to pull each other:

- The hook asks something. The explain answers exactly that, not a neighbouring question. If the explain would read fine under a different hook, the hook is wrong.
- The takeaway is the line someone repeats to a friend. It does not summarise the explain, it lands it.
- Never restate a slide you already wrote. No slide opens by re-introducing the company, the term or the number the previous slide just gave.
- Short sentences. A reader is scrolling, and the card has to survive a glance, not a reading.
- Concrete beats complete. One real number a beginner can picture beats three that cover the topic.
- One idea per slide. If a slide contains "and also", or a second clause that could stand alone, cut it.
- Nothing about the post. Delete any sentence that describes what you are explaining instead of explaining it.
- Write to one person, in the second person. "You" lands where "investors" does not.
- Plain words. Someone who has never owned a share has to get it on one read, so no sentence should need a second pass."""

_NEWS_COPY_PROMPT = """You write for Stock Learn Easy, an Instagram account that teaches stock market beginners.

Today's story:
Headline: {title}
Summary: {description}
Ticker: {ticker}

Write the post. Return ONLY a JSON object, no prose around it, with these keys:

"hook": one line, max 8 WORDS and max 70 characters, for the first slide. It must NOT restate the headline. State the consequence, not the topic: "Germany just slipped under the growth line" lands, "German services PMI falls" is a filing. No abstract nouns on their own (volatility, sentiment, momentum) without the concrete thing they happened to. Name the company or ticker when the story has one, because that is what people search. It has to make sense on its own to someone who never sees the card, since this is also the first line of the caption.
"concept": the transferable idea this story illustrates, named in 2 to 5 words, title case. Something a reader could apply to a different stock next month.
"explain": 2 sentences, max 200 characters total, explaining the actual mechanism in THIS story in plain English. Reference the real company, and it MUST contain at least one real number: a price, a percentage, a count, a date. A number is what makes a mechanism picturable; a sentence without one is a paraphrase of the headline. No hedging, no filler, no "it's important to understand that".
"takeaway": one sentence, max 80 characters, the rule of thumb a beginner should remember. Write it the way someone would say it out loud to a friend, not the way a textbook would summarise it. If it reads like a chapter heading, rewrite it.
"question": one specific question about this story for the comments, max 90 characters. Two tests it must pass: it only makes sense under THIS post, and a complete beginner can answer it without already knowing any market term. "Does 49.4 worry you more than a factory miss?" fails the second test. Ask about their reaction, their guess or their experience, never about a definition.
"tags": exactly 4 hashtag strings including the leading #. Pick only tags a person actually browses: a broad tag with real content behind it (#investing, #stockmarket, #personalfinance) or the ticker or company the post is about. No invented tags, no long compounds nobody searches (#EconomicIndicators), no underscores. Do not include #StockLearnEasy.

""" + _COPY_FLOW_RULES + """

The fact rule, and it outranks every style rule above. It separates two things that are easy to confuse:

- **Claims about THIS story** must come from the material you were given. Do not state what this company reported, what a figure came in at, who said what or when it happened unless the headline, the summary or the ticker says so. Do not complete a missing detail with something that sounds plausible. An invented figure about the story is a worse failure than a dull post.
- **Established background facts are allowed, and are usually what makes the post worth reading.** The 1973 oil shock, how a P/E is calculated, what the S&P 500 is: a textbook fact you are confident about, used to explain the mechanism, is exactly the job. It must be correct and it must be old enough to be settled, never this week's number.

Where the summary is thin, this is the way out: lean the explain on a settled background fact that makes the mechanism concrete, rather than restating the headline in different words.

Rules: no investment advice, no price targets, no predictions, no "should you buy". Explain, never recommend. Plain words over jargon; if you use a market term, define it inline in three words. Write for someone who has never owned a share."""

_TERM_COPY_PROMPT = """You write for Stock Learn Easy, an Instagram account that teaches stock market beginners.

Today's term: {name}
Working definition: {definition}

A dictionary definition is not worth a follow. Turn this into something a beginner would save. Return ONLY a JSON object, no prose around it, with these keys:

"hook": one line, max 8 WORDS and max 70 characters, for the first slide. Not the term as a label. Pose the confusion this term resolves, as a consequence a beginner would feel. It has to make sense on its own to someone who never sees the card, since this is also the first line of the caption.
"concept": the term itself, exactly as given.
"explain": 2 sentences, max 200 characters, defining it through a concrete worked example with real numbers a beginner can follow. Prefer "a $50 stock earning $2 a share has a P/E of 25" over an abstract restatement. The worked example is not optional: the numbers must be in there.
"takeaway": one sentence, max 80 characters, naming the DECISION this term would change. Not what it means, what you would do differently once you know it. The app sells decisions, not vocabulary, so a takeaway that only restates the definition is a failed post. Write it the way someone would say it out loud to a friend.
"question": one specific question that makes someone apply the term, max 90 characters. A complete beginner must be able to answer it without knowing any other market term.
"tags": exactly 4 hashtag strings including the leading #. Pick only tags a person actually browses: a broad tag with real content behind it (#investing, #stockmarket, #personalfinance) or the ticker or company the post is about. No invented tags, no long compounds nobody searches (#EconomicIndicators), no underscores. Do not include #StockLearnEasy.

""" + _COPY_FLOW_RULES + """

Rules: no investment advice, no predictions. Explain, never recommend. Write for someone who has never owned a share."""

_COPY_KEYS = ("hook", "concept", "explain", "takeaway", "question", "tags")

# The same numbers the prompts state, enforced here as well. Until 30.9.2026 the
# limits existed only in the prompt, nothing checked them, and the fit script
# quietly shrank whatever came back, so an over-long explain shipped as smaller
# text instead of being rejected. Over the limit now means the copy is refused
# and rewritten once (see write_post_copy), which is the behaviour Ofir's
# "the text is sometimes too long" asks for.
_COPY_LIMITS = {"hook": 70, "explain": 200, "takeaway": 80, "question": 90}
_HOOK_MAX_WORDS = 8


def _fallback_copy(category, news=None, term=None):
    """The pre-28.9.2026 template copy, kept as the safety net."""
    if category == "term":
        name, definition = term
        return {
            "hook": name,
            "concept": name,
            "explain": definition,
            "takeaway": "Knowing the vocabulary is step one to understanding what you're reading.",
            "question": "Which term should we break down next? Drop it in the comments.",
            "tags": ["#StockMarket", "#Investing", "#FinancialEducation", "#LearnToInvest"],
        }
    return {
        "hook": news["title"],
        "concept": "Market Basics",
        "explain": news.get("description")
        or (
            "Every headline like this is a chance to understand how real events move "
            "stocks and indexes, not just another number to skim past."
        ),
        "takeaway": "Read the reason behind the move, not just the percentage.",
        "question": "What's on your watchlist this week? Tell us in the comments.",
        "tags": ["#StockMarket", "#Investing", "#StockNews", "#FinancialEducation"],
    }


def _clean_copy(raw, category, news=None, term=None, recent_openings=(),
                last_attempt=False, question_hook=False):
    """Accept the model's JSON only if every field is usable.

    Returns (copy, problems). A copy of None means nothing usable came back.
    A copy with problems attached means it failed a gate, and the problems are
    written to be pasted into the retry prompt verbatim: telling the model
    "that was too long" costs a round trip that "explain is 240 chars, limit
    200" does not.

    On the last attempt the soft gates (reading level only) are reported but
    not enforced, because the alternative is the template copy, which is worse
    on every axis including the one being gated.
    """
    if not isinstance(raw, dict):
        return None, ["the answer was not a JSON object"]
    out = {}
    for key in _COPY_KEYS:
        value = raw.get(key)
        if key == "tags":
            if not isinstance(value, list):
                return None, ["tags was not a list"]
            tags = [str(t).strip() for t in value if str(t).strip()]
            tags = [t if t.startswith("#") else f"#{t}" for t in tags]
            # A tag with a space in it is not a tag; Instagram would cut it at
            # the space and post the remainder as plain text.
            tags = [t for t in tags if " " not in t][:4]
            if not tags:
                return None, ["no usable hashtags in tags"]
            out[key] = tags
        else:
            if not isinstance(value, str) or not value.strip():
                return None, [f"{key} was missing or empty"]
            out[key] = value.strip()

    hard = [f"{k} is {len(out[k])} chars, limit {_COPY_LIMITS[k]}"
            for k in _COPY_LIMITS if len(out[k]) > _COPY_LIMITS[k]]
    # 70 characters still allows a 13-word sentence, which is longer than
    # anyone reads at scroll speed. The hook is the one line that has to land
    # in about a second, so it is capped in words as well as characters.
    hook_words = len(out["hook"].split())
    if hook_words > _HOOK_MAX_WORDS:
        hard.append(f"hook is {hook_words} words, limit {_HOOK_MAX_WORDS}")

    # The rest of the gates live in copy_check.py: banned phrases, a number in
    # the explain, no two slides opening on the same word, and the reading
    # level. See instagram-backlog.md items 26, 33, 34, 35, 37.
    extra_hard, soft = copy_check.check(out, recent_openings=recent_openings,
                                         question_hook=question_hook)
    hard += extra_hard

    problems = hard + ([] if last_attempt else soft)
    if problems:
        return out, problems
    if soft:
        print("NOTE: shipping copy with a soft problem: " + "; ".join(soft),
              file=sys.stderr)
    return out, []


# Three attempts, not two. A single retry was enough when the only gate was
# length; with the content gates added on 4.10.2026 a first answer fails
# something about a third of the time, and a third pass is still cheaper than
# shipping the template copy.
_COPY_ATTEMPTS = 3


def write_post_copy(category, news=None, term=None, ticker=None,
                    recent_openings=(), question_hook=False):
    """Story-specific copy from claude -p, falling back to the old templates.

    Returns (copy, prompt): the prompt is kept so source.json can record the
    exact text that produced the post (backlog item 95), which is the only way
    a good post can be reproduced rather than admired.
    """
    if category == "term":
        name, definition = term
        prompt = _TERM_COPY_PROMPT.format(name=name, definition=definition)
    else:
        prompt = _NEWS_COPY_PROMPT.format(
            title=news["title"],
            description=news.get("description") or "(no summary in the feed)",
            ticker=f"${ticker}" if ticker else "(unknown)",
        )
    if recent_openings:
        prompt += (
            "\n\nThe last posts on this account already opened their hooks on "
            "these words: " + ", ".join(f'"{w}"' for w in recent_openings if w)
            + ". Open on none of them. Four posts that start the same way read "
            "as one post in the grid."
        )
    if question_hook:
        prompt += QUESTION_HOOK_PROMPT

    best, ask = None, prompt
    for attempt in range(1, _COPY_ATTEMPTS + 1):
        try:
            result = subprocess.run(
                ["with-claude-token", "claude", "-p", ask, "--output-format", "text"],
                capture_output=True, text=True, timeout=COPY_TIMEOUT, check=True,
            )
            text = result.stdout.strip()
            # The model is asked for bare JSON but sometimes fences it.
            match = re.search(r"\{.*\}", text, re.DOTALL)
            parsed, problems = _clean_copy(
                json.loads(match.group(0)) if match else None, category,
                news=news, term=term, recent_openings=recent_openings,
                last_attempt=(attempt == _COPY_ATTEMPTS),
                question_hook=question_hook,
            )
            if parsed and not problems:
                return parsed, prompt
            if parsed is not None:
                best = parsed  # complete and usable, just not yet clean
            print(f"WARNING: copy rejected for '{category}' on attempt {attempt}: "
                  + "; ".join(problems), file=sys.stderr)
            # Name the actual failures. A retry that only hears "try again"
            # tends to return the same answer with different adjectives.
            ask = prompt + (
                "\n\nYour previous answer was rejected. Fix exactly these problems "
                "and change nothing else that was working:\n- "
                + "\n- ".join(problems)
                + "\n\nEvery limit above is a hard maximum. Cut words, never cut "
                  "the number or the worked example."
            )
        except Exception as e:
            print(f"WARNING: copy generation failed for '{category}' on attempt {attempt} ({e})", file=sys.stderr)

    # A complete answer that failed a style gate still beats the template copy,
    # which fails more of them and says less. The template is for when the
    # model could not be reached at all.
    if best is not None:
        print(f"WARNING: shipping the last answer for '{category}' despite its "
              f"problems, which is still better than the template", file=sys.stderr)
        return best, prompt
    print(f"WARNING: falling back to the template copy for '{category}'", file=sys.stderr)
    return _fallback_copy(category, news=news, term=term), prompt


# Until 29.9.2026 no caption named the app, so the only path from a post to an
# install was a viewer who happened to open the profile and tap the bio link.
# The account exists to drive app installs, so every caption now says where
# the lessons behind the post live. One line, above the disclaimer.
APP_CTA = "📲 Want the full lesson? Stock Learn Easy on the App Store, link in bio."


# Backlog item 16 (4.10.2026). One post in five asks for the follow, and says
# what following gets you. Asking every time reads as needy and stops being
# read; never asking leaves the one action that compounds unasked. Keyed on the
# slot time so a rebuild gives the same answer, and counted in half-days so it
# lands on one generated slot in five rather than one calendar day in five.
FOLLOW_CTA = "👋 New here? Follow @stocklearneasy: the market story of the day, explained from zero."


def wants_follow_line(slot):
    if slot is None:
        return False
    return (slot.toordinal() * 2 + (slot.hour >= 15)) % 5 == 0


# Backlog item 13 (5.10.2026). One carousel a week, the Wednesday 18:00 slot,
# opens on a question the reader can answer from their own life in a few
# words. A comment from someone who does not follow the account is the
# cheapest real engagement signal available, and the usual hook ("Your
# paycheck isn't what's pushing prices up") gives nobody a reason to type.
# Gated in copy_check.question_hook_problems, not only asked for. Wednesday
# 18:00 is a carousel slot, so the test is not confounded with the reel.
QUESTION_HOOK_PROMPT = """

This post is the week's question post, and that overrides the hook rule above. The hook is a question addressed to the reader ("you", "your") that a complete beginner can answer in the comments from their own life, in a few words, with no market knowledge: their choice, their guess or their experience. "Would you keep $1,000 in cash or in an index fund?" works. "Why do rates move stocks?" fails, because it asks for knowledge nobody types into a comment box. It still has to be about THIS story, max 8 words, and end with "?". The explain then gives the answer the story suggests."""


def wants_question_hook(slot):
    return slot is not None and slot.weekday() == 2 and slot.hour >= 15


# Backlog item 14 (7.10.2026). One carousel a week, the Saturday 18:00 slot,
# opens on the hook alone: flat background, no logo lockup, no category pill,
# no headline underneath. A branded template reads as an ad and gets scrolled,
# and this costs one slot a week to find out. Saturday, not Wednesday, so it is
# never the same post as the question test. The disclaimer and the dots stay,
# the disclaimer because it is on every card without exception. Keyed on the
# slot time inside render_slide_html, so a rebuild gives the same card.
def wants_plain_hook(slot):
    return slot is not None and slot.weekday() == 5 and slot.hour >= 15


def post_variant(slot):
    if wants_question_hook(slot):
        return "question-hook"
    if wants_plain_hook(slot):
        return "plain-hook"
    return None


def make_caption(category, copy, news=None, term=None, ticker=None, slot=None):
    tag = CATEGORY_META[category]["tag"]
    follow_line = f"{FOLLOW_CTA}\n" if wants_follow_line(slot) else ""
    headline = term[0] if category == "term" else news["title"]
    ticker_line = f"${ticker}\n\n" if ticker else ""
    tags = " ".join(["#StockLearnEasy", *copy["tags"]])
    # The hook leads. Until 4.10.2026 the first line was the category label
    # ("🏦 Macro Watch"), which is the one line Instagram shows collapsed in
    # feed and the text its search indexes most heavily, spent on a word that
    # tells the reader nothing. The label already appears as the eyebrow on the
    # card, so it moves down to sit with the hashtags rather than being
    # repeated at the top.
    return (
        f"{copy['hook']}\n\n"
        f"{headline}\n\n"
        f"{ticker_line}"
        f"{copy['concept'].upper()}\n"
        f"{copy['explain']}\n\n"
        f"{copy['takeaway']}\n\n"
        f"{copy['question']}\n\n"
        f"{follow_line}"
        f"{APP_CTA}\n\n"
        f"⚠️ {DISCLAIMER}\n\n"
        f"{tag}\n"
        f"{tags}"
    )


# --- Slide plan --------------------------------------------------------------
#
# The carousel used to be exactly three text cards. From 28.9.2026 a post that
# has an honest chart to show gets a fourth slide carrying it, right after the
# hook, because the chart is the reason to stop scrolling. A post with nothing
# real to plot stays at three: an unrelated index next to an unrelated story is
# worse than no chart at all.

CHART_RANGE = "6mo"


def resolve_chart(category, news=None, ticker=None, term=None):
    """Pick the chart this post is entitled to show, or None.

    Returns {"series", "label", "why"} where label names what is plotted and
    why explains, in one line, what it has to do with the story.
    """
    if ticker:
        series = market_data.fetch_series(ticker, rng=CHART_RANGE)
        if series:
            return {
                "series": series,
                "label": f"${ticker}",
                "why": f"What the market has done with it over the {series['range_label']}",
            }

    # No ticker is the common case, not the rare one: plenty of movers and IPO
    # headlines are about companies Yahoo can't resolve (Hibbett, delisted in
    # 2024, was the first one this hit). Those stories still sit on top of a
    # market the reader can be shown, so fall through to the macro proxies for
    # every news category rather than only for macro.
    if news is not None:
        proxy = market_data.macro_proxy(f"{news['title']} {news.get('description') or ''}")
        if proxy:
            series = market_data.fetch_series(proxy["symbol"], rng=CHART_RANGE)
            if series:
                return {"series": series, "label": proxy["label"], "why": proxy["why"]}

    # A term of the day gets a chart only where the chart is the definition,
    # e.g. volatility next to the VIX. Most terms have no honest single chart
    # and stay text.
    if term is not None:
        proxy = market_data.term_proxy(term[0])
        if proxy:
            series = market_data.fetch_series(proxy["symbol"], rng=CHART_RANGE)
            if series:
                return {"series": series, "label": proxy["label"], "why": proxy["why"]}

    return None


def build_slide_plan(chart):
    plan = ["hook"]
    if chart:
        plan.append("chart")
    plan += ["concept", "takeaway"]
    return plan


def chart_summary(chart):
    """The chart, reduced to what's worth recording in source.json.

    The raw series is ~126 points per post and would bloat every commit for
    no benefit; what matters later is what was plotted and what it said.
    """
    if not chart:
        return None
    series = chart["series"]
    return {
        "symbol": series["symbol"],
        "label": chart["label"],
        "range": CHART_RANGE,
        "last": round(series["last"], 4),
        "change_pct": round(series["change_pct"], 2),
        "why": chart["why"],
    }


# One slot a day is a Reel. 12:00 UTC is the one the account already used for
# news, and news is the content most likely to be watched rather than read.
REEL_SLOT_UTC_HOUR = 12


def is_reel_slot(slot):
    return slot.hour == REEL_SLOT_UTC_HOUR

# --- Card rendering ----------------------------------------------------------
#
# The look lives in design.py (shared with the reel). Since 29.9.2026 the
# carousel follows the app's own brand: DM Serif Display over DM Sans, the
# lesson set in a light card like the app's lesson list, the numbers in a hook
# in the app's yellow, and a closing card that shows the app icon and says
# where the full lesson is. Position in the carousel is a row of dots rather
# than "2/4", and the disclaimer sits on every card.

CARD_SIZE = 1080
CARD_PADDING = "84px 96px 72px 96px"


def _card_head(category):
    return (
        '<div class="head">'
        f'<div class="lockup" style="font-size:32px;"><img src="{design.ICON_URI}" '
        'width="64" height="64" alt="">Stock Learn Easy</div>'
        f'<div class="pill" style="font-size:26px;padding:12px 28px;">'
        f'{design.CATEGORY_LABEL.get(category, "MARKET NEWS")}</div>'
        '</div>'
    )


def _card_foot(position, total, right_html):
    return (
        '<div style="display:flex;flex-direction:column;gap:22px;">'
        '<div class="foot">'
        f'{design.dots_html(position, total)}'
        f'<div style="font-size:30px;font-weight:700;">{right_html}</div>'
        '</div>'
        f'<div class="faint" style="font-size:22px;">{design.DISCLAIMER}</div>'
        '</div>'
    )


def chart_body_html(chart, svg_width=888, svg_height=372, scale=1.0):
    """What is plotted, where it stands, why it's here."""
    series = chart["series"]
    rising = series["change_pct"] >= 0
    s = lambda px: f"{round(px * scale)}px"
    return (
        '<div style="display:flex;flex-direction:column;gap:' + s(18) + ';">'
        f'<div class="eyebrow" style="font-size:{s(26)};color:{design.GREEN_TEXT};">THE CHART · '
        f'{escape(series["range_label"].upper())}</div>'
        f'<div style="display:flex;align-items:baseline;gap:{s(26)};flex-wrap:wrap;">'
        f'<div class="serif" style="font-size:{s(76)};line-height:1.05;">{escape(chart["label"])}</div>'
        f'<div class="num" style="font-size:{s(44)};font-weight:500;">'
        f'{market_data.fmt_price(series["last"], series["currency"])}</div>'
        f'<div class="chg {"up" if rising else "down"}" style="font-size:{s(32)};padding:{s(8)} {s(22)};">'
        f'{market_data.fmt_pct(series["change_pct"])}</div>'
        '</div>'
        f'<div style="margin-top:{s(10)};">{market_data.sparkline_svg(series, width=svg_width, height=svg_height)}</div>'
        f'<div class="muted" style="font-size:{s(32)};line-height:1.4;">{escape(chart["why"])}</div>'
        f'<div class="faint" style="font-size:{s(22)};">Price data: Yahoo Finance. '
        'Past performance is not a prediction.</div>'
        '</div>'
    )


def render_slide_html(kind, position, total, category, when_utc, copy,
                      news=None, term=None, ticker=None, chart=None):
    """Render one carousel slide.

    Each slide has to earn its swipe. Before 28.9.2026 slide 2 reprinted the
    headline from slide 1 and slide 3 was a full-page ad for the account, so
    two thirds of the carousel carried nothing new.
    """
    head = _card_head(category)

    if kind == "hook" and wants_plain_hook(when_utc):
        hook_px = design.size_for(copy["hook"], [(40, 120), (58, 108), (72, 98), (999, 86)])
        main = (
            '<div class="main" data-fit-box style="justify-content:center;">'
            f'<div class="serif" data-fit="60" style="font-size:{hook_px}px;line-height:1.08;">'
            f'{design.highlight_numbers(copy["hook"])}</div>'
            '</div>'
        )
        foot = _card_foot(position, total, '<span class="muted">Swipe →</span>')
        # Flat ground: the grid and the glow are part of the brand frame too.
        flat = '<style>body { background-image:none; }</style>'
        return design.page(CARD_SIZE, CARD_SIZE, CARD_PADDING, f'{flat}{main}{foot}')

    if kind == "hook":
        source = term[0] if category == "term" else news["title"]
        source_label = "TODAY'S TERM" if category == "term" else "IN THE NEWS"
        hook_px = design.size_for(copy["hook"], [(40, 104), (58, 94), (72, 86), (999, 76)])
        ticker_html = (
            f'<span class="num" style="color:{design.TEXT};font-weight:700;margin-left:14px;">'
            f'${escape(ticker)}</span>' if ticker else ""
        )
        main = (
            '<div class="main" data-fit-box style="gap:44px;">'
            f'<div class="serif" data-fit="56" style="font-size:{hook_px}px;line-height:1.08;">'
            f'{design.highlight_numbers(copy["hook"])}</div>'
            '<div style="display:flex;flex-direction:column;gap:10px;">'
            f'<div class="eyebrow faint" style="font-size:22px;">{source_label}{ticker_html}</div>'
            f'<div class="muted" style="font-size:30px;line-height:1.4;">{escape(source)}</div>'
            '</div></div>'
        )
        foot = _card_foot(position, total, "Swipe for the answer →")
    elif kind == "chart":
        main = f'<div class="main">{chart_body_html(chart)}</div>'
        foot = _card_foot(position, total, "Swipe →")
    elif kind == "concept":
        text_px = design.size_for(copy["explain"], [(200, 46), (280, 42), (999, 40)])
        main = (
            # Centered, because the panel now hugs its text instead of
            # stretching: left at flex-start the whole block sat at the top with
            # a dead band above the footer.
            '<div class="main" style="justify-content:center;gap:24px;">'
            f'<div class="eyebrow" style="font-size:26px;color:{design.GREEN_TEXT};">THE LESSON</div>'
            f'<div class="serif" style="font-size:{design.size_for(copy["concept"], [(24, 76), (34, 66), (999, 56)])}px;'
            f'line-height:1.05;">{escape(copy["concept"])}</div>'
            # No flex:1. The panel used to stretch to the bottom of the card and
            # left a band of empty surface under short copy, which is most of
            # them now that the explain is capped at 200 characters.
            '<div class="lesson" data-fit-box style="padding:46px 52px;margin-top:8px;'
            'display:flex;align-items:center;">'
            f'<div data-fit="24" style="font-size:{text_px}px;line-height:1.45;">'
            f'{escape(copy["explain"])}</div>'
            '</div></div>'
        )
        foot = _card_foot(position, total, "Swipe →")
    else:
        take_px = design.size_for(copy["takeaway"], [(50, 80), (70, 70), (999, 62)])
        main = (
            '<div class="main" data-fit-box style="justify-content:flex-start;gap:30px;padding-top:12px;">'
            # "SAVE THIS" since 29.9, and 7 days of posts returned 0 saves. The
            # ask is now a send, because a send is the signal Instagram says it
            # weighs most for recommending a post to non-followers, and because
            # sending is the one action that puts the card in front of someone
            # who has never heard of the account. Honest caveat for whoever
            # reads this next: at a reach of 1 to 5 per post neither ask can be
            # measured, so do not credit or blame this for a move in `shares`.
            f'<div class="eyebrow" style="font-size:26px;color:{design.HIGHLIGHT};">RULE OF THUMB · SEND TO A FRIEND</div>'
            f'<div class="serif" data-fit="44" style="font-size:{take_px}px;line-height:1.1;">'
            f'{escape(copy["takeaway"])}</div>'
            f'<div class="muted" style="font-size:31px;line-height:1.4;">{escape(copy["question"])}</div>'
            '</div>'
            f'<div class="cta" style="gap:28px;padding:26px 32px;">'
            f'<img src="{design.ICON_URI}" width="104" height="104" alt="">'
            '<div style="display:flex;flex-direction:column;gap:6px;">'
            '<div class="t1" style="font-size:36px;">The full lesson is in the app</div>'
            '<div class="t2" style="font-size:27px;">Stock Learn Easy on the App Store · link in bio</div>'
            '</div></div>'
        )
        foot = _card_foot(position, total, '<span class="faint">@stocklearneasy</span>')

    return design.page(CARD_SIZE, CARD_SIZE, CARD_PADDING,
                       f'{head}{main}{foot}')

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
        # --virtual-time-budget holds the screenshot until the page has
        # settled: the local fonts are loaded and the fit script has run.
        # Without it Chrome shot the page before the font arrived, which is
        # how the old cards ended up in Helvetica.
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
         "--virtual-time-budget=5000",
         f"--screenshot={png_path}", "--window-size=1080,1080",
         f"file://{html_path}"],
        check=True, capture_output=True, timeout=30,
    )

    ok, reason = is_valid_card(png_path)
    if not ok:
        raise RuntimeError(f"render_png: rendered image failed validation ({reason}): {png_path}")


def seen_from_disk():
    """What is already queued or published, read back off disk.

    seen-headlines.json is only a cache, and on 28.9.2026 it proved it: a run
    that built three posts was killed before it got to save the file, so the
    next run happily queued the same inflation story and the same "Bear
    Market" term a second time. The slot directories are the actual record of
    what this account has committed to post, so trust those too.
    """
    headlines, terms = set(), set()
    for root in (SCHEDULED, PUBLISHED):
        if not root.is_dir():
            continue
        for slot_dir in root.iterdir():
            source = slot_dir / "source.json"
            if not source.is_file():
                continue
            try:
                data = json.loads(source.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("news"):
                headlines.add(data["news"]["title"])
            if data.get("term"):
                terms.add(data["term"][0])
    return headlines, terms


def recent_posts(limit=14):
    """The last `limit` posts by slot name, newest first, as source.json dicts.

    Slot names sort chronologically because they are ISO timestamps, so this is
    a sort rather than a date parse.
    """
    found = []
    for root in (SCHEDULED, PUBLISHED):
        if not root.is_dir():
            continue
        for slot_dir in root.iterdir():
            source = slot_dir / "source.json"
            if not source.is_file():
                continue
            try:
                found.append((slot_dir.name, json.loads(source.read_text(encoding="utf-8"))))
            except Exception:
                continue
    found.sort(key=lambda pair: pair[0], reverse=True)
    return [data for _, data in found[:limit]]


def recent_openings(posts, depth=3):
    """Item 37: the opening word of the last few hooks, to be avoided.

    Three, not fourteen: by the fourth post back nobody remembers how it
    started, and forbidding fourteen words starves the model of openings.
    """
    out = []
    for data in posts[:depth]:
        hook = (data.get("copy") or {}).get("hook", "")
        word = copy_check.opening_word(hook)
        if word:
            out.append(word)
    return out


# Item 36. Words that say nothing about what a story is about, so two headlines
# sharing only these are not the same story.
_TOPIC_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "of", "to", "in", "on", "at",
    "by", "with", "from", "as", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "it", "its", "has", "have", "had",
    "will", "would", "can", "could", "may", "might", "more", "most", "than",
    "then", "now", "new", "after", "before", "about", "why", "how", "what",
    "when", "who", "stock", "stocks", "market", "markets", "shares", "says",
    "said", "year", "years", "week", "day", "here", "there", "amid", "over",
}


def _topic_words(text):
    return {
        w for w in re.findall(r"[a-z0-9$]{4,}", (text or "").lower())
        if w not in _TOPIC_STOPWORDS
    }


# Two distinctive words in common is the threshold. One is a coincidence
# ("inflation" appears in half of all macro headlines); three almost never
# happens even for genuine duplicates, so it would catch nothing.
_TOPIC_OVERLAP_MIN = 2


def is_duplicate_topic(candidate, posts):
    """Item 36: has this account already covered this subject recently?

    Catches the failure where the same event is reported by two outlets with
    different wording, which the exact-title check in seen-headlines.json
    cannot see. Two PMI posts in a week is the same post twice.
    """
    words = _topic_words(f"{candidate['title']} {candidate.get('description') or ''}")
    if not words:
        return None
    for data in posts:
        news = data.get("news") or {}
        prior = _topic_words(news.get("title"))
        if not prior:
            continue
        shared = words & prior
        if len(shared) >= _TOPIC_OVERLAP_MIN:
            return f"{news.get('title', '')[:60]} (shared: {', '.join(sorted(shared))})"
    return None


def main():
    seen_headlines = load_json_set(SEEN_FILE)
    seen_terms = load_json_set(SEEN_TERMS_FILE)
    disk_headlines, disk_terms = seen_from_disk()
    seen_headlines |= disk_headlines
    seen_terms |= disk_terms
    candidates = fetch_headlines()

    slots = next_free_slots(TARGET_QUEUE_DEPTH)
    if not slots:
        print("Queue already full.")
        return

    cat_idx = next_category_index()
    made, failed = 0, 0
    # Read once, then kept current in the loop: a run that queues three posts
    # must not let post 3 repeat post 2's subject or its opening word.
    recent = recent_posts()
    for slot in slots:
        category = CATEGORY_CYCLE[cat_idx % len(CATEGORY_CYCLE)]
        cat_idx += 1
        openings = recent_openings(recent)

        news, term = None, None
        if category == "term":
            available = [t for t in TERMS if t[0] not in seen_terms]
            if not available:
                seen_terms = set()  # exhausted the list, start over
                available = TERMS
            term = available[0]
            seen_terms.add(term[0])
        else:
            news = pick_headline_for_category(category, candidates, seen_headlines,
                                              recent=recent)
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
            question_hook = wants_question_hook(slot)
            copy, copy_prompt = write_post_copy(
                category, news=news, term=term, ticker=ticker,
                recent_openings=openings, question_hook=question_hook,
            )
            chart = resolve_chart(category, news=news, ticker=ticker, term=term)
            plan = build_slide_plan(chart)

            for position, kind in enumerate(plan, start=1):
                html_path = out_dir / f"card_{position}.html"
                html_path.write_text(
                    render_slide_html(kind, position, len(plan), category, slot, copy,
                                      news=news, term=term, ticker=ticker, chart=chart),
                    encoding="utf-8",
                )
                render_png(html_path, out_dir / f"post_{position}.png")
                html_path.unlink()

            (out_dir / "caption.txt").write_text(
                make_caption(category, copy, news=news, term=term, ticker=ticker, slot=slot), encoding="utf-8"
            )
            record = {
                "category": category,
                "news": news,
                "term": term,
                "ticker": ticker,
                "copy": copy,
                "slides": plan,
                "chart": chart_summary(chart),
                # Items 84 and 95. The rules this post was generated under,
                # and the exact prompt that produced it. Without these, a week
                # later there is no way to tell whether a good post was the
                # rule or the luck, and no way to reproduce it.
                "backlog_items": BACKLOG_ITEMS,
                "variant": post_variant(slot),
                "copy_prompt": copy_prompt,
            }
            (out_dir / "source.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8",
            )

            # The reel is a bonus on top of a slot that is already complete and
            # publishable, so its failure must never reach the handler below:
            # that one deletes the whole slot, and losing a good carousel
            # because ffmpeg hiccuped would be a worse outcome than no reel.
            if is_reel_slot(slot):
                try:
                    reel.build_reel(out_dir, category, copy, slot,
                                    news=news, term=term, ticker=ticker, chart=chart)
                except Exception as e:
                    print(f"WARNING: reel build failed for {slot_name} ({e}), "
                          f"the slot will publish as a carousel", file=sys.stderr)
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

        # Newest first, so the next slot in this same run sees this post when
        # it checks for a repeated subject or a repeated opening word.
        recent.insert(0, record)
        made += 1
        label = term[0] if term else news["title"]
        ticker_note = f" (${ticker})" if ticker else ""
        print(f"Queued {slot_name} [{category}]: {label}{ticker_note}")

    save_json_set(SEEN_FILE, seen_headlines)
    save_json_set(SEEN_TERMS_FILE, seen_terms)
    backfill_reels()
    print(f"Made {made} new post(s), {failed} failed.")
    return 1 if failed else 0


def backfill_reels():
    """Give any queued reel slot that still has no video one now.

    Covers two cases: slots queued before reels existed, and slots whose reel
    build failed on an earlier run. Without this, one bad ffmpeg run would
    silently cost that day its reel.
    """
    if not SCHEDULED.is_dir():
        return
    for slot_dir in sorted(SCHEDULED.iterdir()):
        if not slot_dir.is_dir() or (slot_dir / "reel.mp4").is_file():
            continue
        try:
            slot = datetime.strptime(slot_dir.name, "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if not is_reel_slot(slot):
            continue
        source = slot_dir / "source.json"
        if not source.is_file():
            continue
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
            chart = resolve_chart(data["category"], news=data.get("news"),
                                  ticker=data.get("ticker"), term=data.get("term"))
            reel.build_reel(slot_dir, data["category"], data["copy"], slot,
                            news=data.get("news"), term=data.get("term"),
                            ticker=data.get("ticker"), chart=chart)
            print(f"Backfilled reel for {slot_dir.name}")
        except Exception as e:
            print(f"WARNING: reel backfill failed for {slot_dir.name}: {e}", file=sys.stderr)


def rebuild_slot(slot_dir: Path):
    """Re-render an already-queued slot from its own source.json.

    The story and the copy are left exactly as they were; only the rendering
    is redone. This is what to run after changing a card layout or widening
    the chart rules, instead of deleting slots and regenerating them, which
    would throw away good copy and pick different stories.
    """
    data = json.loads((slot_dir / "source.json").read_text(encoding="utf-8"))
    slot = datetime.strptime(slot_dir.name, "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc)
    category, copy = data["category"], data["copy"]
    news, term, ticker = data.get("news"), data.get("term"), data.get("ticker")

    chart = resolve_chart(category, news=news, ticker=ticker, term=term)
    plan = build_slide_plan(chart)

    for old in slot_dir.glob("post_*.png"):
        old.unlink()
    for position, kind in enumerate(plan, start=1):
        html_path = slot_dir / f"card_{position}.html"
        html_path.write_text(
            render_slide_html(kind, position, len(plan), category, slot, copy,
                              news=news, term=term, ticker=ticker, chart=chart),
            encoding="utf-8",
        )
        render_png(html_path, slot_dir / f"post_{position}.png")
        html_path.unlink()

    # The caption is a pure function of the stored copy, so rebuild it too;
    # otherwise a caption change only reaches posts queued after it.
    (slot_dir / "caption.txt").write_text(
        make_caption(category, copy, news=news, term=term, ticker=ticker, slot=slot), encoding="utf-8"
    )

    data["slides"] = plan
    data["chart"] = chart_summary(chart)
    data["variant"] = post_variant(slot)
    (slot_dir / "source.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if is_reel_slot(slot):
        reel.build_reel(slot_dir, category, copy, slot,
                        news=news, term=term, ticker=ticker, chart=chart)

    chart_note = f" + {chart['label']} chart" if chart else ""
    print(f"Rebuilt {slot_dir.name} [{category}]: {len(plan)} slides{chart_note}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rebuild":
        targets = sys.argv[2:] or sorted(str(p) for p in SCHEDULED.iterdir() if p.is_dir())
        for target in targets:
            try:
                rebuild_slot(Path(target))
            except Exception as e:
                print(f"ERROR rebuilding {target}: {e}", file=sys.stderr)
        sys.exit(0)
    sys.exit(main())
