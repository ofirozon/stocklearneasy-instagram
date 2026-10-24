#!/usr/bin/env python3
"""Backlog item 20: re-post the best post a month later, under a new hook.

At a reach of a few accounts per post almost nobody saw even the best post the
first time, so the cheapest strong post available is one that already beat
the account. generate.py calls pick() before filling the queue; when a post
qualifies, one slot goes to it instead of to a new story.

What qualifies, all of it checked here and not left to judgement:
- published at least REPOST_AFTER_DAYS ago, and never re-posted before;
- reach at least REACH_FLOOR and at least MEDIAN_MULTIPLE times the median,
  so a post that merely got lucky at reach 3 is never recycled;
- evergreen: an animated episode or a term-of-the-day. A news story a month
  old is no longer news, and re-running it would present stale facts as fresh;
- no re-post in the last MIN_DAYS_BETWEEN days, so the grid stays mostly new.

The hook is always new (that is the point of the item), and is gated: it must
differ from the original, open on a different word, fit the hook word limit
and carry none of the banned phrases. A hook that cannot pass in three tries
means no re-post this run, never a re-post under the old hook.

    ./repost.py           print what would be re-posted today, change nothing
"""
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import copy_check
import fallback_still
import story
import winners

ROOT = Path(__file__).resolve().parent
SCHEDULED = ROOT / "scheduled"
PUBLISHED = ROOT / "published"

REPOST_AFTER_DAYS = 30
REACH_FLOOR = 10
MEDIAN_MULTIPLE = 3
MIN_DAYS_BETWEEN = 7
HOOK_MAX_WORDS = 8
EVERGREEN_CATEGORIES = {"term"}


def _slot_time(name):
    try:
        return datetime.strptime(name, "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _meta(slot_dir):
    """The slot's reel.json and source.json, whichever exist."""
    out = {}
    for name in ("reel.json", "source.json"):
        p = slot_dir / name
        if p.is_file():
            try:
                out[name] = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                pass
    return out


def past_reposts():
    """{original slot: repost slot} across the queue and the published posts."""
    done = {}
    for base in (SCHEDULED, PUBLISHED):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            for meta in _meta(d).values():
                if meta.get("repost_of"):
                    done[meta["repost_of"]] = d.name
    return done


def pick(now=None):
    """The post to re-post now, as a dict, or None."""
    now = now or datetime.now(timezone.utc)
    done = past_reposts()
    recent = [t for t in map(_slot_time, done.values())
              if t and abs((now - t).days) < MIN_DAYS_BETWEEN]
    if recent:
        return None

    snapshot = winners.latest_snapshot()
    if not snapshot:
        return None
    median = statistics.median(r["reach"] for r in snapshot.values())
    floor = max(REACH_FLOOR, MEDIAN_MULTIPLE * median)

    best = None
    for slot, row in snapshot.items():
        when = _slot_time(slot)
        if not when or now - when < timedelta(days=REPOST_AFTER_DAYS):
            continue
        if slot in done or slot in done.values() or row["reach"] < floor:
            continue
        d = PUBLISHED / slot
        meta = _meta(d)
        reel, src = meta.get("reel.json"), meta.get("source.json")
        if reel and reel.get("episode") and not src:
            kind = "episode"
        elif src and src.get("category") in EVERGREEN_CATEGORIES:
            kind = "term"
        else:
            continue
        if src and src.get("repost_of"):
            continue
        if reel and reel.get("repost_of"):
            continue
        if best is None or row["reach"] > best["reach"]:
            caption = (d / "caption.txt").read_text(encoding="utf-8")
            # Item 69: a term that went out as a carousel comes back in the
            # reel slot, so the pair is the same post in both formats.
            fmt = "reel" if reel and (reel.get("video_url") or reel.get("episode")) else "carousel"
            best = {"slot": slot, "kind": kind, "reach": row["reach"],
                    "original_format": fmt,
                    "hook": caption.strip().splitlines()[0].strip(),
                    "caption": caption, "reel": reel, "source": src,
                    "floor": floor}
    return best


_NEW_HOOK_PROMPT = """This Instagram post from @stocklearneasy, an educational account for people who have never invested, did well a month ago and is being posted again. Most of today's audience never saw it.

Its old opening line was: "{hook}"

The whole caption, for context:
---
{body}
---

Write ONE new opening line for the same post. Rules:
- a different angle from the old one, and it must not start with the word "{first}";
- at most {max_words} words, plain words a 15-year-old reads in one second;
- concrete: a number, a moment or a picture the reader recognises;
- educational only: no advice, no prediction, nothing about what to buy or sell.

Return ONLY the line, no quotes, no explanation."""


def hook_problems(new, old):
    problems = []
    if not new:
        return ["the answer was empty"]
    if new.strip(" .!?").lower() == old.strip(" .!?").lower():
        problems.append("it repeats the old hook")
    if copy_check.first_word(new) == copy_check.first_word(old):
        problems.append(f'it opens on "{copy_check.first_word(old)}", the old opening word')
    words = len(new.split())
    if words > HOOK_MAX_WORDS:
        problems.append(f"it is {words} words, limit {HOOK_MAX_WORDS}")
    banned = copy_check.banned_phrases(new)
    if banned:
        problems.append("it uses banned phrases: " + ", ".join(banned))
    return problems


def new_hook(candidate, timeout=120):
    """A fresh, gated hook for the candidate, or None."""
    old = candidate["hook"]
    body = "\n".join(candidate["caption"].strip().splitlines()[1:]).strip()
    prompt = _NEW_HOOK_PROMPT.format(hook=old, body=body, first=copy_check.first_word(old),
                                     max_words=HOOK_MAX_WORDS)
    ask = prompt
    for attempt in range(1, 4):
        try:
            out = subprocess.run(
                ["with-claude-token", "claude", "-p", ask, "--output-format", "text"],
                capture_output=True, text=True, timeout=timeout, check=True,
            ).stdout.strip()
        except Exception as e:
            print(f"WARNING: repost hook call failed on attempt {attempt} ({e})", file=sys.stderr)
            continue
        line = re.sub(r'^["“”\']+|["“”\']+$', "", out.splitlines()[0].strip()) if out else ""
        problems = hook_problems(line, old)
        if not problems:
            return line
        print(f"WARNING: repost hook rejected on attempt {attempt}: {line!r}: "
              + "; ".join(problems), file=sys.stderr)
        ask = prompt + "\n\nYour previous answer was rejected:\n- " + "\n- ".join(problems)
    return None


def queue_episode_repost(candidate, slot_dir, hook):
    """Re-queue an animated episode: the same video, a new first caption line.

    The video is already on the media release under the original slot's
    asset name, so nothing is uploaded and the URL is reused as is.
    """
    src_dir = PUBLISHED / candidate["slot"]
    lines = candidate["caption"].strip().splitlines()
    caption = "\n".join([hook] + lines[1:]).strip() + "\n"
    slot_dir.mkdir(parents=True, exist_ok=False)
    (slot_dir / "caption.txt").write_text(caption, encoding="utf-8")
    reel = dict(candidate["reel"])
    cover = reel.get("cover")
    if cover and (src_dir / cover).is_file():
        (slot_dir / cover).write_bytes((src_dir / cover).read_bytes())
    else:
        reel.pop("cover", None)
    reel.update({"repost_of": candidate["slot"], "original_hook": candidate["hook"],
                 "original_reach": candidate["reach"],
                 "original_format": candidate["original_format"]})
    (slot_dir / "reel.json").write_text(json.dumps(reel, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    # Item 68: an episode slot has no cards, so give it a still to fall back on.
    fallback_still.write_fallback_still(slot_dir)
    # Item 80: the Story is made from that still.
    story.write_story(slot_dir)


if __name__ == "__main__":
    c = pick()
    if not c:
        print("Nothing qualifies for a re-post today.")
    else:
        print(f"Would re-post {c['slot']} ({c['kind']}, reach {c['reach']}, "
              f"floor {c['floor']:g}): \"{c['hook']}\"")
