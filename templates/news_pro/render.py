#!/usr/bin/env python3
"""Market-update carousel, professional layout (5 cards, 1080x1350).

    python3 templates/news_pro/render.py <published-or-scheduled slot dir> <out dir> [--img path.png] [--cutoff YYYY-MM-DD]

Reads source.json from the slot (the same news + copy the pipeline already writes), pulls real index closes from
market_data.py (Yahoo Finance), computes every number, and screenshots post_pro.html once per card with headless Chrome.
Nothing here publishes anything, and generate.py / publish.py are untouched.

Rules baked in (owner, 24.11.2026):
  * an app lesson is named only if lessons.pick_lesson() picks one; otherwise the card says "Stock Learn Easy";
  * numbers are computed, never typed;
  * the illustration is optional: pass --img for a text-free picture, or the cover shows the data strip only.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
import compliance  # noqa: E402
import lessons  # noqa: E402
import market_data as md  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
INDICES = [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow")]
CARDS = 5


def series_until(symbol, cutoff):
    d = md.fetch_series(symbol, rng="1mo")
    if not d:
        sys.exit(f"no data for {symbol}; not rendering a card with missing numbers")
    pts = [(datetime.utcfromtimestamp(t).date(), c) for t, c in d["points"]]
    pts = [(day, c) for day, c in pts if day.isoformat() <= cutoff]
    if len(pts) < 8:
        sys.exit(f"too little history for {symbol} up to {cutoff}")
    return pts


def build(slot_dir, cutoff, img):
    compliance.require_yahoo_display("the news_pro market-update layout")
    src = json.loads((slot_dir / "source.json").read_text())
    news, copy = src.get("news"), src.get("copy")
    if not news or not copy:
        sys.exit("this slot has no news item; the market-update layout needs one")
    items = []
    for sym, label in INDICES:
        pts = series_until(sym, cutoff)
        last, base = pts[-1][1], pts[-6][1]
        items.append({"symbol": sym, "label": label, "last": round(last, 2),
                      "week_pct": round((last / base - 1) * 100, 2),
                      "series": [[d.isoformat(), round(c, 2)] for d, c in pts],
                      "last_date": pts[-1][0].isoformat()})
    picked = lessons.pick_lesson(copy, None, news)
    return {
        "tag": "MARKET UPDATE",
        "date": datetime.fromisoformat(cutoff).strftime("%b %-d, %Y").upper(),
        "headline": copy["hook"], "facts": [news["title"], news["description"]],
        "lesson": picked[0] if picked else None, "indices": items, "news_source": "MarketWatch",
        "concept": copy["concept"], "explain": copy["explain"], "takeaway": copy["takeaway"],
        "question": copy["question"],
        "fine": "Index data: Yahoo Finance closes. News summary: MarketWatch. Educational content only. Not financial advice.",
        "img": img,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slot")
    ap.add_argument("out")
    ap.add_argument("--img", default="")
    ap.add_argument("--cutoff", help="last trading day to use; default: the slot date")
    a = ap.parse_args()
    slot = Path(a.slot)
    cutoff = a.cutoff or slot.name[:10]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    data = build(slot, cutoff, Path(a.img).resolve().as_uri() if a.img else "")
    data_js = HERE / "_data.js"
    data_js.write_text("window.NEWS = " + json.dumps(data, ensure_ascii=False) + ";\n")
    try:
        for s in range(CARDS):
            dest = out / f"post_{s + 1}.png"
            subprocess.run([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                            "--virtual-time-budget=4000", "--window-size=1080,1350", f"--screenshot={dest}",
                            f"{(HERE / 'post_pro.html').as_uri()}?d=_data.js&s={s}"], capture_output=True, timeout=180)
            if not dest.exists():
                sys.exit(f"no card written for {dest.name}")
            print(dest)
    finally:
        data_js.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
