#!/usr/bin/env python3
"""Backlog item 97 (28.10.2026): a monthly "best of" carousel.

At a reach of a few accounts per post, almost nobody saw last month's posts,
and the one line in each that is meant to outlive its story is the takeaway
(the "rule of thumb" card). Once a month one evening carousel collects the
four takeaways from last month's posts that reached the most people, one per
card, ending on the app.

Nothing here is written by the model. The takeaways are the ones that already
passed every copy gate when they first shipped, and the hook and caption are
fixed text, so the post cannot claim anything the account did not already say.

What qualifies, checked here:
- published in the calendar month before the slot, with a source.json and a
  takeaway; app posts, re-posts and earlier best-ofs never count;
- ranked by reach from the latest metrics snapshot, then by likes, saves and
  shares, then newest first; one card per concept and per takeaway;
- at least MIN_PICKS of them, or the slot stays a normal post.

The slot: the first Tuesday, Thursday or Sunday 18:00 carousel of the month.
Those are the evening slots that are not already a weekly test (Monday chart
first, Wednesday question, Friday app, Saturday plain hook), so no running
experiment loses a post to this one.

    python best_of.py 2026-11-01T1800     print what that slot would collect
"""
import calendar
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import design
import winners

ROOT = Path(__file__).resolve().parent
PUBLISHED = ROOT / "published"
PICKS = 4
MIN_PICKS = 3
FREE_WEEKDAYS = (1, 3, 6)  # Tuesday, Thursday, Sunday
TAGS = ["#investingforbeginners", "#stockmarket", "#personalfinance", "#learninvesting"]


def wants_best_of(slot):
    if slot is None or slot.hour < 15 or slot.weekday() not in FREE_WEEKDAYS:
        return False
    first = next(d for d in range(1, 8)
                 if slot.replace(day=d).weekday() in FREE_WEEKDAYS)
    return slot.day == first


def previous_month(slot):
    return (slot.year - 1, 12) if slot.month == 1 else (slot.year, slot.month - 1)


def pick(slot):
    """Last month's top takeaways for this slot, best first, or [] if too few."""
    year, month = previous_month(slot)
    prefix = f"{year:04d}-{month:02d}-"
    snapshot = winners.latest_snapshot()
    rows = []
    for d in sorted(PUBLISHED.glob(prefix + "*")):
        p = d / "source.json"
        if not p.is_file():
            continue
        try:
            src = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        copy = src.get("copy") or {}
        if src.get("category") in ("app", "bestof") or src.get("repost_of"):
            continue
        takeaway, concept = (copy.get("takeaway") or "").strip(), (copy.get("concept") or "").strip()
        if not takeaway or not concept:
            continue
        m = snapshot.get(d.name, {})
        rows.append({
            "slot": d.name, "concept": concept, "takeaway": takeaway,
            "reach": m.get("reach", 0),
            "engagement": sum(m.get(k, 0) or 0 for k in ("likes", "saved", "shares")),
        })
    rows.sort(key=lambda r: (r["reach"], r["engagement"], r["slot"]), reverse=True)
    out, seen = [], set()
    for r in rows:
        key_c, key_t = r["concept"].lower(), r["takeaway"].lower()
        if key_c in seen or key_t in seen:
            continue
        seen |= {key_c, key_t}
        out.append(r)
        if len(out) == PICKS:
            break
    return out if len(out) >= MIN_PICKS else []


def month_name(slot):
    return calendar.month_name[previous_month(slot)[1]]


def hook(slot, picks):
    return f"{month_name(slot)}, in {len(picks)} rules of thumb"


def caption(slot, picks):
    lines = "\n".join(f"{i}. {p['concept']}: {p['takeaway']}" for i, p in enumerate(picks, 1))
    return (
        f"{hook(slot, picks)}.\n\n"
        f"The {len(picks)} lessons from {month_name(slot)}'s posts that reached the most "
        "people, one per slide. Send it to the friend who keeps asking where to start.\n\n"
        f"{lines}\n\n"
        "📲 The basics behind posts like these are in Stock Learn Easy: 44 lessons, "
        "from zero, on the App Store. Link in bio.\n\n"
        f"⚠️ {design.DISCLAIMER}\n\n"
        f"{' '.join(['#StockLearnEasy', *TAGS])}"
    )


def slide_html(kind, position, total, slot, picks, card_head, card_foot, size):
    """One card. card_head, card_foot and size come from generate.py, so the
    best-of wears the same frame as every other carousel."""
    width, height, padding = size
    if kind == "hook":
        text = hook(slot, picks)
        px = design.size_for(text, [(40, 120), (58, 108), (999, 98)])
        main = (
            '<div class="main" data-fit-box style="gap:44px;">'
            f'<div class="eyebrow" style="font-size:26px;color:{design.HIGHLIGHT};">'
            f'BEST OF {escape(month_name(slot).upper())}</div>'
            f'<div class="serif" data-hook data-fit="56" style="font-size:{px}px;line-height:1.08;">'
            f'{design.highlight_numbers(escape(text))}</div>'
            f'<div class="muted" style="font-size:32px;line-height:1.4;">The lines from last '
            "month's posts that reached the most people. One per slide.</div>"
            '</div>'
        )
        foot = card_foot(position, total, "Swipe →")
        extra = design.PEEK_HTML
    else:
        p = picks[position - 2]
        take_px = design.size_for(p["takeaway"], [(50, 84), (70, 74), (999, 64)])
        last = position == total
        cta = (
            f'<div class="cta" style="gap:28px;padding:26px 32px;border:2px solid rgba(34,197,94,0.45);">'
            f'<img src="{design.ICON_URI}" width="104" height="104" alt="">'
            '<div style="display:flex;flex-direction:column;gap:6px;flex:1;min-width:0;">'
            '<div class="t1" style="font-size:34px;">Learn the basics behind them</div>'
            '<div class="t2" style="font-size:26px;">Stock Learn Easy · 44 lessons</div>'
            '</div>'
            '<div style="display:flex;flex-direction:column;align-items:center;gap:8px;flex-shrink:0;">'
            f'<div style="background:{design.GREEN};color:{design.GREEN_INK};font-weight:700;'
            'font-size:30px;letter-spacing:1px;border-radius:999px;padding:12px 40px;">GET</div>'
            '<div class="t2" style="font-size:20px;">link in bio</div>'
            '</div></div>'
        ) if last else ''
        main = (
            '<div class="main" data-fit-box style="justify-content:center;gap:30px;">'
            f'<div class="eyebrow" style="font-size:26px;color:{design.GREEN_TEXT};">'
            f'RULE {position - 1} OF {total - 1} · {escape(p["concept"].upper())}</div>'
            f'<div class="serif" data-fit="44" style="font-size:{take_px}px;line-height:1.1;">'
            f'{escape(p["takeaway"])}</div>'
            '</div>' + cta
        )
        foot = card_foot(position, total, '' if last else "Swipe →")
        extra = design.END_CSS if last else ''
    return design.page(width, height, padding, f'{card_head("bestof")}{main}{foot}{extra}')


def record(slot, picks):
    return {
        "category": "bestof",
        "news": None,
        "term": None,
        "ticker": None,
        "copy": {"hook": hook(slot, picks), "tags": TAGS},
        "picks": picks,
        "slides": ["hook"] + ["rule"] * len(picks),
        "chart": None,
        "backlog_items": [97],
        "variant": "best-of",
    }


if __name__ == "__main__":
    when = datetime.strptime(sys.argv[1], "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc)
    print("best-of slot:", wants_best_of(when))
    for p in pick(when):
        print(f"  {p['slot']} reach {p['reach']}: {p['concept']}: {p['takeaway']}")
