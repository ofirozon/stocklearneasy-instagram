"""Backlog item 74 (20.10.2026): name the lesson that continues in the app.

Until now every caption and every closing card said "the full lesson", which
promises nothing in particular. A reader who just learned what a stock split
is will tap for "Dividends & Stock Splits", not for "the full lesson".

The catalogue below is the English app's own lesson list, copied from
~/stock-learn-easy-mobile/src/data/en/lessons (44 lessons, the number on the
App Store page) on 20.10.2026. If a lesson is renamed in the app, rename it
here; the title must be one a user can actually find.

Gated, not asked for: the copy model never writes the lesson name. It is
picked here from the post's own words, and a post that matches nothing well
enough keeps the generic line. An invented lesson title cannot ship, because
the only titles that can come out of this module are the ones in LESSONS.
"""

import re

# (app title, short title for the card, keyword phrases). Phrases are matched
# as whole words, case-insensitive. Keep them specific: a phrase that fits half
# the news ("market", "stock") would route everything to one lesson.
LESSONS = [
    ("What Are Stocks?", "What Are Stocks?",
     ["what is a stock", "shareholder", "shareholders", "equity", "preferred stock",
      "common stock", "ownership", "ipo", "going public", "blue chip"]),
    ("How Stock Markets Work", "How Stock Markets Work",
     ["stock exchange", "nyse", "nasdaq", "market maker", "market makers",
      "bid-ask", "bid ask", "bid-ask spread", "trading hours", "liquidity", "short selling"]),
    ("Understanding Market Capitalization", "Market Capitalization",
     ["market cap", "market capitalization", "large-cap", "small-cap", "mid-cap",
      "magnificent seven", "megacap", "mega-cap", "index concentration"]),
    ("Bull & Bear Markets", "Bull & Bear Markets",
     ["bull market", "bear market", "correction", "market cycle", "sentiment",
      "record high", "52-week high/low", "selloff", "sell-off", "rally", "52-week high", "52-week low",
      "calendar effect", "october"]),
    ("Dividends & Stock Splits", "Dividends & Stock Splits",
     ["dividend", "dividends", "dividend yield", "stock split", "reverse split",
      "payout", "ex-dividend", "buyback", "buybacks"]),
    ("Types of Stock Orders", "Types of Stock Orders",
     ["limit order", "market order", "stop-loss", "stop loss", "order type"]),
    ("Income Statement Analysis", "The Income Statement",
     ["revenue", "earnings", "profit", "profits", "margin", "margins", "ebitda",
      "net income", "quarterly results", "sales"]),
    ("Balance Sheet Fundamentals", "The Balance Sheet",
     ["balance sheet", "debt", "liabilities", "assets", "book value"]),
    ("Cash Flow Statement", "Cash Flow Statement",
     ["cash flow", "free cash flow", "capex", "capital spending", "big spending",
      "deferred costs"]),
    ("Key Financial Ratios", "Key Financial Ratios",
     ["ratio", "ratios", "roe", "return on equity", "leverage"]),
    ("Growth Metrics & Analysis", "Growth Metrics",
     ["growth", "slowing growth", "cagr", "peg", "growth rate", "eps growth"]),
    ("Competitive Analysis", "Competitive Analysis",
     ["competitor", "competitors", "competition", "moat", "market share",
      "rival", "rivals", "soda wars", "picks and shovels", "contract", "contracts"]),
    ("Valuation Basics & Intrinsic Value", "Valuation Basics",
     ["valuation", "valuations", "intrinsic value", "overvalued", "undervalued",
      "fair value", "expectations"]),
    ("Price-to-Earnings (P/E) Analysis", "P/E Analysis",
     ["p/e", "pe ratio", "price-to-earnings", "price to earnings", "earnings multiple",
      "forward earnings", "cape"]),
    ("Discounted Cash Flow (DCF) Model", "The DCF Model",
     ["dcf", "discounted cash flow", "discount rate", "present value"]),
    ("Dividend Discount Model (DDM)", "Dividend Discount Model",
     ["dividend discount", "gordon growth"]),
    ("Risk Basics & Fundamentals", "Risk Basics",
     ["risk tolerance", "time horizon", "risk"]),
    ("Types of Investment Risk", "Types of Investment Risk",
     ["credit risk", "interest rate risk", "inflation risk", "currency risk",
      "headline risk", "new competitor risk", "concentration risk", "default"]),
    ("Risk Assessment & Measurement", "Measuring Risk",
     ["volatility", "vix", "beta", "drawdown", "standard deviation", "sharpe"]),
    ("Behavioral & Psychological Risk", "Behavioral Risk",
     ["fear", "greed", "panic", "fomo", "bias", "biases", "herd", "anxiety",
      "emotion", "emotions", "happiness"]),
    ("Hedging Techniques", "Hedging Techniques",
     ["hedge", "hedging", "options", "put option", "inverse etf"]),
    ("Chart Basics & Candlesticks", "Chart Basics",
     ["candlestick", "candlesticks", "chart", "price chart"]),
    ("Support & Resistance", "Support & Resistance",
     ["support", "resistance", "breakout"]),
    ("Moving Averages", "Moving Averages",
     ["moving average", "200-day", "50-day"]),
    ("Volume Analysis", "Volume Analysis",
     ["volume", "trading volume"]),
    ("Technical Indicators", "Technical Indicators",
     ["rsi", "macd", "indicator", "indicators", "overbought", "oversold"]),
    ("Trend Analysis", "Trend Analysis",
     ["trend", "trends", "trendline", "uptrend", "downtrend"]),
    ("Asset Allocation Strategies", "Asset Allocation",
     ["asset allocation", "stocks and bonds", "bonds", "bond", "60/40",
      "yields get attractive", "treasury", "treasuries", "yield", "yields"]),
    ("Diversification Strategies", "Diversification",
     ["diversification", "diversify", "diversified", "index fund", "etf", "etfs",
      "s&p 500", "three-fund"]),
    ("Dollar-Cost Averaging", "Dollar-Cost Averaging",
     ["dollar-cost averaging", "dollar cost averaging", "dca", "every month",
      "lump sum"]),
    ("Portfolio Rebalancing", "Portfolio Rebalancing",
     ["rebalance", "rebalancing", "drift"]),
    ("International Investing", "International Investing",
     ["international", "emerging markets", "china", "europe", "japan", "germany",
      "global", "tariff", "tariffs"]),
    ("Retirement Portfolio Planning", "Retirement Planning",
     ["retirement", "retire", "401(k)", "401k", "ira", "social security", "pension"]),
    ("Tax-Efficient Investing", "Tax-Efficient Investing",
     ["tax", "taxes", "capital gains", "roth", "tax-loss"]),
    ("Investment Goal Setting", "Setting Goals",
     ["goal", "goals", "saving", "savings", "credit card", "credit cards",
      "budget", "paycheck"]),
    ("Performance Tracking", "Performance Tracking",
     ["performance", "returns", "benchmark", "beat the market"]),
]

# No macro mapping on purpose. The app has no lesson on rates, inflation or the
# Fed, and routing those stories to "Valuation Basics" sent the Social Security
# inflation post to a valuation lesson. A macro post keeps the generic line
# unless its own words point at a real lesson (bonds, retirement, and so on).

TITLES = {title for title, _, _ in LESSONS}

# The weight of a hit depends on where it lands. The term's own name is the
# strongest evidence of what the post teaches, the concept line next, then the
# prose. The headline counts least, because news headlines name companies and
# events, not ideas.
_WEIGHTS = (("term", 5), ("concept", 4), ("hook", 1), ("explain", 1),
            ("takeaway", 1), ("headline", 0.5))

# Below this the match is a guess, and the generic line is better than a
# confident wrong title.
MIN_SCORE = 2


def _count(phrase, text):
    return len(re.findall(r"(?<![\w/])" + re.escape(phrase) + r"(?![\w/])", text))


def pick_lesson(copy, term=None, news=None):
    """Return (app title, card title) for the best-matching lesson, or None."""
    fields = {
        "term": (term[0] if term else "") or "",
        "concept": copy.get("concept", ""),
        "hook": copy.get("hook", ""),
        "explain": copy.get("explain", ""),
        "takeaway": copy.get("takeaway", ""),
        "headline": (news or {}).get("title", "") if news else "",
    }
    fields = {k: v.lower() for k, v in fields.items()}

    best, best_score = None, 0.0
    for title, short, phrases in LESSONS:
        score = 0.0
        for field, weight in _WEIGHTS:
            text = fields[field]
            if not text:
                continue
            score += weight * sum(min(_count(p, text), 2) for p in phrases)
        if score > best_score:
            best, best_score = title, score
    if best is None or best_score < MIN_SCORE:
        return None
    short = next(s for t, s, _ in LESSONS if t == best)
    assert best in TITLES
    return best, short
