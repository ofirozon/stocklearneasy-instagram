"""Legal stop switches for the Instagram generators (stdlib only).

Read from compliance.json next to this file. Both switches ship OFF (false), which is the safe default:

  rss_headlines_allowed   false: generate.py does not read the MarketWatch RSS feeds and builds only original
                          educational "term" posts. Dow Jones' Terms of Use (effective 4 Nov 2026) bar using content from
                          its RSS feeds, including headlines and summaries, in a commercial product without written consent.
  yahoo_display_allowed   false: no price, index level or percent change from the unofficial Yahoo Finance endpoint is
                          drawn on a card or reel. Yahoo's Terms bar automated collection, commercial reuse and
                          redistribution.

Set a switch to true only after the owner holds a written permission or a licence that covers it (see the research report
"Finance Instagram professional playbook", open questions 4, 5 and 7). A missing, unreadable or malformed file means
both switches are off: failing closed.
"""
import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "compliance.json"


def _flag(name, config=CONFIG):
    try:
        d = json.loads(Path(config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(d, dict) and d.get(name) is True


def rss_headlines_allowed(config=CONFIG):
    return _flag("rss_headlines_allowed", config)


def yahoo_display_allowed(config=CONFIG):
    return _flag("yahoo_display_allowed", config)


def autofill_allowed(config=CONFIG):
    """false: generate.py queues nothing on its own (owner decision of 25.11.2026, old formats stopped).
    Missing or malformed config means off."""
    return _flag("autofill_allowed", config)


def require_yahoo_display(what, config=CONFIG):
    """Raise before any Yahoo-based number is drawn, with a message that says what to do."""
    if not yahoo_display_allowed(config):
        raise RuntimeError(f"{what} needs licensed price data: yahoo_display_allowed is false in compliance.json")
