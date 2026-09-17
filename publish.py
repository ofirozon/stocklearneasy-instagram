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

ROOT = pathlib.Path(__file__).resolve().parent
SCHEDULED = ROOT / "scheduled"
PUBLISHED = ROOT / "published"
LOG = ROOT / "published-log.jsonl"

GRAPH = "https://graph.instagram.com/v21.0"
RAW_BASE = "https://raw.githubusercontent.com/ofirozon/stocklearneasy-instagram/main"

MAX_LATE_HOURS = float(os.environ.get("MAX_LATE_HOURS", "20"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"


def slot_time(path: pathlib.Path):
    try:
        return datetime.strptime(path.name, "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def api_post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_get(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def publish_one(slot_dir: pathlib.Path, token: str, ig_user_id: str):
    caption = (slot_dir / "caption.txt").read_text(encoding="utf-8")
    image_url = f"{RAW_BASE}/scheduled/{slot_dir.name}/post.png"

    created = api_post(f"{GRAPH}/{ig_user_id}/media", {
        "image_url": image_url,
        "caption": caption,
        "access_token": token,
    })
    if "id" not in created:
        raise RuntimeError(f"container creation failed: {created}")
    creation_id = created["id"]

    for _ in range(20):
        status = api_get(f"{GRAPH}/{creation_id}?fields=status_code&access_token={token}")
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"container failed processing: {status}")
        time.sleep(5)
    else:
        raise RuntimeError("container never finished processing")

    published = api_post(f"{GRAPH}/{ig_user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": token,
    })
    if "id" not in published:
        raise RuntimeError(f"media_publish failed: {published}")
    return published["id"]


def main() -> int:
    token = os.environ.get("IG_ACCESS_TOKEN")
    ig_user_id = os.environ.get("IG_USER_ID")
    if not token or not ig_user_id:
        print("IG_ACCESS_TOKEN / IG_USER_ID not set, nothing to do.", file=sys.stderr)
        return 0

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
    for when, slot_dir in due:
        late_hours = (now - when).total_seconds() / 3600
        if late_hours > MAX_LATE_HOURS:
            print(f"skip (too late, {late_hours:.1f}h): {slot_dir.name}")
            continue

        if DRY_RUN:
            print(f"[DRY RUN] would publish {slot_dir.name}")
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

    print(f"done: {published} published, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
