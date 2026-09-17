#!/usr/bin/env python3
"""
Stock Learn Easy - Instagram post generator.

Fetches live market-news headlines, writes a beginner-friendly English
caption (Stock Learn Easy's voice, fixed disclaimer every time), and
renders a 1080x1080 image card via headless Chrome. Tops up the
`scheduled/` queue to TARGET_QUEUE_DEPTH future daily slots, skipping
headlines already used (tracked in seen-headlines.json).

Runs locally (has Chrome + Keychain); GitHub Actions only runs publish.py.
"""
import json
import re
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEDULED = ROOT / "scheduled"
PUBLISHED = ROOT / "published"
SEEN_FILE = ROOT / "seen-headlines.json"

RSS_URL = "https://feeds.content.dowjones.io/public/rss/mw_topstories"
DISCLAIMER = "Educational content only. Not financial or investment advice."

# One post a day, 18:00 UTC (21:00 Israel). Adjust if a different
# cadence/time is wanted later.
DAILY_SLOT_UTC_HOUR = 18
TARGET_QUEUE_DEPTH = 3

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2))


def fetch_headlines(limit=15):
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        xml_bytes = resp.read()
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        items.append({
            "title": item.find("title").text,
            "description": item.find("description").text,
            "link": item.find("link").text,
        })
    return items


def next_free_slots(count):
    """UTC datetimes for the next `count` daily slots not already queued/published."""
    existing = set()
    for d in (SCHEDULED, PUBLISHED):
        if d.is_dir():
            existing.update(p.name for p in d.iterdir() if p.is_dir())

    slots = []
    now = datetime.now(timezone.utc)
    day = now.date()
    while len(slots) < count:
        candidate = datetime(day.year, day.month, day.day, DAILY_SLOT_UTC_HOUR, tzinfo=timezone.utc)
        if candidate > now:
            name = candidate.strftime("%Y-%m-%dT%H%M")
            if name not in existing:
                slots.append(candidate)
        day += timedelta(days=1)
    return slots


def make_caption(news):
    return (
        f"\U0001F4F0 Market News, Simplified\n\n"
        f"{news['title']}\n\n"
        f"{news['description']}\n\n"
        f"Why it matters if you're just starting out: every headline like this "
        f"is a chance to understand how real events move stocks and indexes, "
        f"not just another number to skim past.\n\n"
        f"Want to understand the \"why\" behind the headlines? Stock Learn Easy "
        f"teaches it step by step.\n\n"
        f"⚠️ {DISCLAIMER}\n\n"
        f"#StockLearnEasy #StockMarket #Investing #StockNews #FinancialEducation #Stocks"
    )


def render_card_html(news, when_utc):
    title = escape(news["title"])
    date_str = when_utc.strftime("%b %d, %Y")
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
    padding:80px;
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
  <div class="tag">\U0001F4F0 Today's Market News</div>
  <div class="headline">{title}</div>
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
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu",
         f"--screenshot={png_path}", "--window-size=1080,1080",
         f"file://{html_path}"],
        check=True, capture_output=True, timeout=30,
    )


def main():
    seen = load_seen()
    headlines = fetch_headlines()
    fresh = [h for h in headlines if h["title"] not in seen]

    slots = next_free_slots(TARGET_QUEUE_DEPTH)
    if not slots:
        print("Queue already full.")
        return
    if len(fresh) < len(slots):
        print(f"Only {len(fresh)} fresh headline(s) available, filling what we can.")

    made = 0
    for slot, news in zip(slots, fresh):
        slot_name = slot.strftime("%Y-%m-%dT%H%M")
        out_dir = SCHEDULED / slot_name
        out_dir.mkdir(parents=True, exist_ok=True)

        html_path = out_dir / "card.html"
        html_path.write_text(render_card_html(news, slot), encoding="utf-8")
        render_png(html_path, out_dir / "post.png")
        html_path.unlink()

        (out_dir / "caption.txt").write_text(make_caption(news), encoding="utf-8")
        (out_dir / "source.json").write_text(
            json.dumps(news, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        seen.add(news["title"])
        made += 1
        print(f"Queued {slot_name}: {news['title']}")

    save_seen(seen)
    print(f"Made {made} new post(s).")


if __name__ == "__main__":
    main()
