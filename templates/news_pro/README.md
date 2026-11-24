# News update card layout, professional (news_pro)

Five 1080x1350 cards for a market-news post: cover with index strip, S&P 500 chart, what happened + table, the concept, takeaway.

```
python3 templates/news_pro/render.py published/2026-11-20T1200 /tmp/cards --img illustration.png
```

- Reads `source.json` (news + copy) from the slot, pulls real closes from `market_data.py`, computes every number.
- App lesson: only `lessons.pick_lesson()` may name one; otherwise the card says "Stock Learn Easy".
- `--img` is optional and must be a picture with no text in any language (check it by eye before using it).
- `card_check.py` now also accepts this layout's paper background (#fbf8f1 within 3 per channel). A white or error page
  still fails, and the dark navy cards pass as before. Any other light background is still rejected on purpose.

Not wired: `generate.py` does not call this yet, and nothing here writes into `scheduled/` or publishes. To use it, call
`render.py` into a slot directory as `post_1.png..post_5.png` next to a `caption.txt` (the publisher already reads `post_*.png`).
Not verified here: that `publish.py` accepts five cards for a carousel (Instagram allows up to ten).
