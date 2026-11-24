#!/usr/bin/env python3
"""Backlog item 20: re-post the best post a month later, under a new hook.

At a reach of a few accounts per post almost nobody saw even the best post the
first time, so the cheapest strong post available is one that already beat
the account. generate.py calls pick() before filling the queue; when a post
qualifies, one slot goes to it instead of to a new story.

What qualifies, all of it checked here and not left to judgement:
- published at least REPOST_AFTER_DAYS ago, and never re-posted before (terms;
  episodes re-air every REPOST_AFTER_DAYS with no floor, see pick_episode);
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
import episode_tag
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


def _episode_airings():
    """{episode: [(slot time, slot name, base dir, reel, reach-or-None)]} over
    published and queued slots, oldest first."""
    out = {}
    for base in (PUBLISHED, SCHEDULED):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            reel = _meta(d).get("reel.json")
            t = _slot_time(d.name)
            if reel and reel.get("episode") and t:
                out.setdefault(reel["episode"], []).append((t, d.name, base, reel))
    for v in out.values():
        v.sort()
    return out


def pick_episode(now, snapshot):
    """Item 70m: an animated episode is re-aired whenever its last airing is
    REPOST_AFTER_DAYS old, with no reach floor and no once-only rule.

    The floor was right for terms and wrong for episodes. First-run reach
    measured the account in early October, not the film: bull-bear went 25 on
    its first run and 106 on its re-post; every episode aired since November
    lands at 97 to 207. With 3 followers almost every viewer is new each time,
    so a second airing costs nothing. Fewest airings go first, then the best
    reach any airing had. Only the films already published are candidates;
    one still waiting for its first run in the queue is skipped."""
    best = None
    for episode, airings in _episode_airings().items():
        if any(base == SCHEDULED for _, _, base, _ in airings):
            continue  # a pending airing (first run or re-post) already holds it
        last_t, last_slot, _, last_reel = airings[-1]
        if now - last_t < timedelta(days=REPOST_AFTER_DAYS):
            continue
        original = next((s for _, s, _, r in airings if not r.get("repost_of")), airings[0][1])
        reach = max((snapshot.get(s, {}).get("reach") or 0) for _, s, _, _ in airings)
        key = (-len(airings), reach)
        if best is None or key > best["_key"]:
            caption = (PUBLISHED / last_slot / "caption.txt").read_text(encoding="utf-8")
            best = {"slot": last_slot, "original_slot": original, "kind": "episode",
                    "reach": reach, "airings": len(airings), "original_format": "reel",
                    "hook": caption.strip().splitlines()[0].strip(),
                    "caption": caption, "reel": last_reel, "source": None,
                    "floor": 0, "_key": key}
    if best:
        best.pop("_key")
    return best


def pick(now=None):
    """The post to re-post now, as a dict, or None."""
    now = now or datetime.now(timezone.utc)
    # Every re-post slot counts, not one per original: since 70m an episode
    # can be re-aired more than once, and past_reposts() keeps only one each.
    repost_times = [_slot_time(d.name) for base in (SCHEDULED, PUBLISHED) if base.is_dir()
                    for d in base.iterdir()
                    if any(m.get("repost_of") for m in _meta(d).values())]
    # Calendar days: the fill runs at 08:00 and re-posts land at 12:00, so
    # timedelta days read a week as 6 and pushed a weekly re-post to every
    # other week.
    if any(t and abs((now.date() - t.date()).days) < MIN_DAYS_BETWEEN for t in repost_times):
        return None

    snapshot = winners.latest_snapshot()
    if not snapshot:
        return None
    ep = pick_episode(now, snapshot)
    if ep:
        return ep
    done = past_reposts()
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
            continue  # episodes go through pick_episode (70m)
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


RELEASE_REPO = "ofirozon/stocklearneasy-instagram"


def _tagged_copy(episode, video_url, slot_dir):
    """Download the original film, burn in the lesson tag, upload it as this
    slot's own asset. Returns the reel.json fields that change."""
    import tempfile
    import urllib.request
    with tempfile.TemporaryDirectory(prefix="repost-tag-") as work:
        src = Path(work) / "src.mp4"
        with urllib.request.urlopen(video_url, timeout=120) as r:
            src.write_bytes(r.read())
        asset = Path(work) / f"reel-{slot_dir.name}.mp4"
        if not episode_tag.tag_video(episode, src, asset):
            raise RuntimeError("episode not mapped")
        up = subprocess.run(["gh", "release", "upload", "media", str(asset), "--clobber",
                             "--repo", RELEASE_REPO], capture_output=True, text=True)
        if up.returncode != 0:
            raise RuntimeError(f"release upload failed: {up.stderr.strip()[-300:]}")
        url = f"https://github.com/{RELEASE_REPO}/releases/download/media/{asset.name}"
        # Kept untracked (*.mp4 is ignored), the same as a first-run slot.
        (slot_dir / "reel.mp4").write_bytes(asset.read_bytes())
        return {"video_url": url, "size_bytes": asset.stat().st_size, "lesson_tag": True}


def queue_episode_repost(candidate, slot_dir, hook):
    """Re-queue an animated episode: the same video, a new first caption line.

    A film already tagged with its app lesson (70d) is reused from the media
    release as is. An older, untagged one is tagged and uploaded under this
    slot's own asset name (70k), so the original asset is never overwritten.
    """
    src_dir = PUBLISHED / candidate["slot"]
    lines = candidate["caption"].strip().splitlines()
    caption = "\n".join([hook] + lines[1:]).strip() + "\n"
    reel = dict(candidate["reel"])
    episode = reel.get("episode")
    # Item 70k: an episode first run before 70d (8.11) has a generic app line
    # and an untagged film. The re-post is the one that reaches 100 to 200, so
    # it gets the named lesson in both places. Caption and film are tagged
    # independently; a failed film tag keeps the old video rather than losing
    # the slot.
    if episode and episode_tag.GENERIC_LINE in caption:
        caption = episode_tag.tag_caption(episode, caption)
    slot_dir.mkdir(parents=True, exist_ok=False)
    (slot_dir / "caption.txt").write_text(caption, encoding="utf-8")
    if episode and not reel.get("lesson_tag") and episode_tag.lesson_for(episode):
        try:
            reel.update(_tagged_copy(episode, reel["video_url"], slot_dir))
        except Exception as e:
            print(f"WARNING: repost {slot_dir.name}: film not tagged, original kept ({e})",
                  file=sys.stderr)
    cover = reel.get("cover")
    if cover and (src_dir / cover).is_file():
        (slot_dir / cover).write_bytes((src_dir / cover).read_bytes())
    else:
        reel.pop("cover", None)
    reel.update({"repost_of": candidate.get("original_slot", candidate["slot"]),
                 "aired_from": candidate["slot"], "original_hook": candidate["hook"],
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
