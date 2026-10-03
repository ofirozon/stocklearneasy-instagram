#!/usr/bin/env python3
"""Publish any due Instagram post from scheduled/ for Stock Learn Easy.

A scheduled post is a directory:
    scheduled/<YYYY-MM-DDTHHMM>/post.png     (image, time is UTC)
    scheduled/<YYYY-MM-DDTHHMM>/caption.txt  (caption text)

It is published once its slot time is in the past, then moved to
published/ so it can never be sent twice. The image is fetched by
Instagram from its raw.githubusercontent.com URL, so this script must
run AFTER the post's commit is pushed and visible there.

Env:
    IG_ACCESS_TOKEN   long-lived Instagram access token
    IG_USER_ID        Instagram professional account id (from /me)
    MAX_LATE_HOURS    skip posts more than this many hours overdue (default 20)
    MAX_PER_RUN       how many slots one run may publish (default 1)
    MIN_GAP_MINUTES   minimum spacing between two publishes (default 45)
    DRY_RUN           if "1", print what would happen and change nothing
"""
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from card_check import is_valid_card

ROOT = pathlib.Path(__file__).resolve().parent
SCHEDULED = ROOT / "scheduled"
PUBLISHED = ROOT / "published"
REJECTED = ROOT / "rejected"
SKIPPED = ROOT / "skipped"
LOG = ROOT / "published-log.jsonl"

GRAPH = "https://graph.instagram.com/v21.0"
RAW_BASE = "https://raw.githubusercontent.com/ofirozon/stocklearneasy-instagram/main"

# The only account this repo may ever post to. See check_account().
EXPECTED_USERNAME = "stocklearneasy"

MAX_LATE_HOURS = float(os.environ.get("MAX_LATE_HOURS", "20"))

# One slot per run, and never two publishes inside the same 45 minutes.
# On 3.10.2026 a backlog of three slots (the 09:30 reel, the 12:00 reel and the
# 18:00 carousel) all went live inside the same two minutes once a gate bug was
# fixed, because this script published every due slot in one pass. For an
# account this small that is the worst possible way to spend three posts: the
# feed shows a dump, the posts compete with each other for the same impressions,
# and a profile visitor sees three identical timestamps. The workflow runs every
# 10 minutes, so a backlog now drains one post at a time instead.
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "1"))
MIN_GAP_MINUTES = float(os.environ.get("MIN_GAP_MINUTES", "45"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"

# Instagram transcodes an uploaded reel before the container is publishable.
# Measured on a 30-second 1080x1920 clip: well over a minute. 10 minutes of
# headroom costs nothing, since the job is idle-waiting either way.
REEL_STATUS_TRIES = 60
REEL_STATUS_DELAY = 10


def slot_time(path: pathlib.Path):
    try:
        return datetime.strptime(path.name, "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def last_publish_time():
    """When the most recent post actually went live, or None.

    Read from published-log.jsonl rather than from file mtimes, because every
    run starts from a fresh checkout where every file is seconds old.
    """
    if not LOG.is_file():
        return None
    newest = None
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            stamp = json.loads(line).get("published_at")
            when = datetime.fromisoformat(stamp)
        except Exception:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if newest is None or when > newest:
            newest = when
    return newest


def api_post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_get(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def wait_finished(creation_id: str, token: str, tries=20, delay=5):
    for _ in range(tries):
        status = api_get(f"{GRAPH}/{creation_id}?fields=status_code&access_token={token}")
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError(f"container failed processing: {status}")
        time.sleep(delay)
    raise RuntimeError("container never finished processing")


def publish_single(slot_dir: pathlib.Path, caption: str, token: str, ig_user_id: str):
    image_url = f"{RAW_BASE}/scheduled/{slot_dir.name}/post.png"

    created = api_post(f"{GRAPH}/{ig_user_id}/media", {
        "image_url": image_url,
        "caption": caption,
        "access_token": token,
    })
    if "id" not in created:
        raise RuntimeError(f"container creation failed: {created}")
    creation_id = created["id"]
    wait_finished(creation_id, token)

    published = api_post(f"{GRAPH}/{ig_user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": token,
    })
    if "id" not in published:
        raise RuntimeError(f"media_publish failed: {published}")
    return published["id"]


def publish_carousel(slot_dir: pathlib.Path, image_names, caption: str, token: str, ig_user_id: str):
    child_ids = []
    for name in image_names:
        image_url = f"{RAW_BASE}/scheduled/{slot_dir.name}/{name}"
        created = api_post(f"{GRAPH}/{ig_user_id}/media", {
            "image_url": image_url,
            "is_carousel_item": "true",
            "access_token": token,
        })
        if "id" not in created:
            raise RuntimeError(f"carousel child container creation failed ({name}): {created}")
        wait_finished(created["id"], token)
        child_ids.append(created["id"])

    parent = api_post(f"{GRAPH}/{ig_user_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption,
        "access_token": token,
    })
    if "id" not in parent:
        raise RuntimeError(f"carousel parent container creation failed: {parent}")
    creation_id = parent["id"]
    wait_finished(creation_id, token)

    published = api_post(f"{GRAPH}/{ig_user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": token,
    })
    if "id" not in published:
        raise RuntimeError(f"media_publish failed: {published}")
    return published["id"]


def publish_reel(slot_dir: pathlib.Path, video_url: str, caption: str, token: str,
                 ig_user_id: str, cover_name: str | None = None):
    """Publish the slot as a Reel.

    Video containers take minutes, not seconds: Instagram downloads and
    transcodes the file before the container reports FINISHED, so this waits
    far longer than the image path does. Publishing a Reel before it finishes
    just fails, and a failed slot is skipped for the day.

    `cover_name` is a file sitting next to the video in the slot directory.
    Without one Instagram picks the cover itself, and what it picks is what
    the grid shows forever: a dark or half-drawn frame makes the whole profile
    look broken even when the reel is fine. The cover is fetched from the
    repo the same way the carousel images are.
    """
    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": token,
    }
    if cover_name and (slot_dir / cover_name).is_file():
        params["cover_url"] = f"{RAW_BASE}/scheduled/{slot_dir.name}/{cover_name}"
    created = api_post(f"{GRAPH}/{ig_user_id}/media", params)
    if "id" not in created:
        raise RuntimeError(f"reel container creation failed: {created}")
    creation_id = created["id"]
    wait_finished(creation_id, token, tries=REEL_STATUS_TRIES, delay=REEL_STATUS_DELAY)

    published = api_post(f"{GRAPH}/{ig_user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": token,
    })
    if "id" not in published:
        raise RuntimeError(f"media_publish failed: {published}")
    return published["id"]


def publish_one(slot_dir: pathlib.Path, token: str, ig_user_id: str):
    caption = (slot_dir / "caption.txt").read_text(encoding="utf-8")

    # A reel.json means generate.py built a video for this slot and the queue
    # script uploaded it; the URL it points at is a GitHub release asset, not
    # a file in the repo, so the repo never carries megabytes of video.
    reel_meta = slot_dir / "reel.json"
    if reel_meta.is_file():
        meta = json.loads(reel_meta.read_text(encoding="utf-8"))
        video_url = meta.get("video_url")
        if video_url:
            try:
                return publish_reel(slot_dir, video_url, caption, token,
                                    ig_user_id, meta.get("cover"))
            except Exception as e:
                # Nothing is live at this point (a failure here is either the
                # container never finishing or media_publish being rejected),
                # so the carousel built for the same slot is still a safe
                # thing to send. Losing the reel beats losing the day.
                print(f"{slot_dir.name}: reel publish failed ({e}), falling back to the carousel",
                      file=sys.stderr)
        else:
            print(f"{slot_dir.name}: reel.json has no video_url, falling back to the carousel",
                  file=sys.stderr)

    carousel_images = sorted(
        (p.name for p in slot_dir.glob("post_*.png")),
        key=lambda n: int(n.split("_")[1].split(".")[0]),
    )
    if carousel_images:
        return publish_carousel(slot_dir, carousel_images, caption, token, ig_user_id)
    return publish_single(slot_dir, caption, token, ig_user_id)


def check_account(token: str) -> bool:
    """Refuse to publish unless the token belongs to EXPECTED_USERNAME.

    Two Instagram pipelines now run from this Mac into two different accounts,
    and their GitHub secrets were both set within the same minute on 3.10.2026.
    A token pasted into the wrong repo would publish one brand's cards to the
    other brand's followers, which is not undoable. One cheap call per run
    makes that mistake impossible instead of merely unlikely.
    """
    try:
        me = api_get(f"{GRAPH}/me?fields=username&access_token={token}")
    except Exception as e:
        print(f"could not identify the connected account ({e}), not publishing",
              file=sys.stderr)
        return False
    username = me.get("username")
    if username != EXPECTED_USERNAME:
        print(f"WRONG ACCOUNT: token belongs to @{username}, expected "
              f"@{EXPECTED_USERNAME}. Not publishing anything.", file=sys.stderr)
        return False
    print(f"connected account: @{username}")
    return True


def main() -> int:
    token = os.environ.get("IG_ACCESS_TOKEN")
    ig_user_id = os.environ.get("IG_USER_ID")
    if not token or not ig_user_id:
        print("IG_ACCESS_TOKEN / IG_USER_ID not set, nothing to do.", file=sys.stderr)
        return 0

    if not check_account(token):
        return 1

    if not SCHEDULED.is_dir():
        print("No scheduled/ directory, nothing to do.")
        return 0

    now = datetime.now(timezone.utc)
    due = []
    for slot_dir in sorted(SCHEDULED.iterdir()):
        if not slot_dir.is_dir():
            continue
        when = slot_time(slot_dir)
        if when is None:
            print(f"skip (bad name): {slot_dir.name}", file=sys.stderr)
            continue
        if when <= now:
            due.append((when, slot_dir))

    if not due:
        print("Nothing due.")
        return 0

    published, failed = 0, 0
    last_live = last_publish_time()
    for when, slot_dir in due:
        late_hours = (now - when).total_seconds() / 3600
        if late_hours > MAX_LATE_HOURS:
            # Park it instead of leaving it in scheduled/, where it would be
            # re-read and re-skipped by every run from now until forever and
            # would keep inflating any count of "posts still queued".
            print(f"skip (too late, {late_hours:.1f}h): {slot_dir.name}")
            if not DRY_RUN:
                SKIPPED.mkdir(exist_ok=True)
                slot_dir.rename(SKIPPED / slot_dir.name)
            continue

        if published >= MAX_PER_RUN:
            print(f"deferred (already published {published} this run): {slot_dir.name}")
            break

        if last_live is not None:
            gap = (now - last_live).total_seconds() / 60
            if gap < MIN_GAP_MINUTES:
                print(f"deferred ({gap:.0f}min since the last post, "
                      f"want {MIN_GAP_MINUTES:.0f}): {slot_dir.name}")
                break

        if DRY_RUN:
            print(f"[DRY RUN] would publish {slot_dir.name}")
            published += 1
            last_live = now
            continue

        # Final gate: never publish anything that isn't actually our
        # rendered card. This is what should have caught the 18.9.2026
        # incident (a browser error-page screenshot got published) even
        # if a bad image somehow slipped past generate.py's own check.
        # Carousel slots (post_1.png, post_2.png, ...) get every slide
        # checked; a single bad slide rejects the whole slot, since a
        # carousel publishes all its children together or not at all.
        # A reel slot has no card to check: its content is the video, built by
        # our own pipeline and already uploaded. Running the card gate over it
        # looks for a post.png that was never supposed to exist, fails, and
        # throws the slot into rejected/. That silently killed the first four
        # animated episodes before anyone noticed they had not gone out.
        reel_meta = slot_dir / "reel.json"
        is_reel = False
        if reel_meta.is_file():
            try:
                is_reel = bool(json.loads(reel_meta.read_text()).get("video_url"))
            except Exception:
                is_reel = False

        # Any card that exists is still checked, including a carousel sitting
        # behind a reel as its fallback. Only a reel with no cards at all gets
        # a pass, because there is nothing there to validate.
        images = sorted(slot_dir.glob("post_*.png"))
        if not images and not is_reel:
            images = [slot_dir / "post.png"]
        bad = None
        for img in images:
            ok, reason = is_valid_card(img)
            if not ok:
                bad = (img.name, reason)
                break
        if bad is not None:
            print(f"REJECTED {slot_dir.name}: {bad[0]}: {bad[1]}", file=sys.stderr)
            REJECTED.mkdir(exist_ok=True)
            slot_dir.rename(REJECTED / slot_dir.name)
            failed += 1
            continue

        try:
            media_id = publish_one(slot_dir, token, ig_user_id)
        except Exception as e:
            print(f"FAILED {slot_dir.name}: {e}", file=sys.stderr)
            failed += 1
            continue

        PUBLISHED.mkdir(exist_ok=True)
        dest = PUBLISHED / slot_dir.name
        slot_dir.rename(dest)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "slot": slot_dir.name,
                "media_id": media_id,
                "published_at": now.isoformat(),
            }, ensure_ascii=False) + "\n")
        print(f"published {slot_dir.name} -> media {media_id}")
        published += 1
        last_live = now

    print(f"done: {published} published, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
