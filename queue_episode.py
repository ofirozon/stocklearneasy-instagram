#!/usr/bin/env python3
"""Queue one animated episode as a scheduled reel.

    ./queue_episode.py bull-bear 2026-10-02T1430

Builds scheduled/<slot>/ with the caption, the cover and a reel.json, and
uploads the video to the "media" GitHub release so Instagram has a public URL
to fetch. The video itself is never committed: at ~5MB an episode, a year of
them in git history would be several gigabytes that git cannot forget.

The cover matters more than it looks. Instagram shows a reel in the profile
grid as the centre square of its cover, and left to itself it picks a frame
of its own choosing, which is how a grid ends up full of dark half-drawn
stills. `render.py --cover` composes one deliberately for that square.

This only queues. Publishing belongs to the cloud publisher, which sends each
slot once its time has passed.
"""
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
ANIM = ROOT / "animation"
SCHEDULED = ROOT / "scheduled"
REPO = "ofirozon/stocklearneasy-instagram"
RELEASE_URL = f"https://github.com/{REPO}/releases/download/media"


def caption_for(episode: str) -> str:
    """Pull the episode's post text out of episodes/CAPTIONS.md."""
    src = ANIM / "episodes" / "CAPTIONS.md"
    lines = src.read_text(encoding="utf-8").splitlines()
    out, grabbing = [], False
    for line in lines:
        if line.startswith("## "):
            if grabbing:
                break
            grabbing = line[3:].strip() == episode
            continue
        if grabbing and line.startswith("> "):
            out.append(line[2:])
        elif grabbing and line.strip() == ">":
            out.append("")
    if not out:
        sys.exit(f"no caption block for '{episode}' in {src}")
    # collapse the runs of blank lines the markdown quoting introduces
    text, blank = [], False
    for line in out:
        if not line.strip():
            if blank:
                continue
            blank = True
        else:
            blank = False
        text.append(line)
    return "\n".join(text).strip() + "\n"


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    episode, slot = sys.argv[1], sys.argv[2]

    mp4 = ANIM / "out" / f"{episode}.mp4"
    cover = ANIM / "out" / f"{episode}-cover.jpg"
    for p, what in ((mp4, "video"), (cover, "cover")):
        if not p.is_file():
            sys.exit(f"{what} missing at {p}")

    slot_dir = SCHEDULED / slot
    if slot_dir.exists():
        sys.exit(f"{slot_dir} already exists; pick another slot or clear it")
    slot_dir.mkdir(parents=True)

    (slot_dir / "caption.txt").write_text(caption_for(episode), encoding="utf-8")
    shutil.copyfile(cover, slot_dir / "cover.jpg")
    shutil.copyfile(mp4, slot_dir / "reel.mp4")

    asset = f"reel-{slot}.mp4"
    tmp = pathlib.Path("/tmp") / asset
    shutil.copyfile(mp4, tmp)
    up = subprocess.run(["gh", "release", "upload", "media", str(tmp),
                         "--clobber", "--repo", REPO],
                        capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if up.returncode != 0:
        shutil.rmtree(slot_dir)
        sys.exit(f"release upload failed: {up.stderr.strip()}")

    duration = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(mp4)],
        capture_output=True, text=True, check=True).stdout.strip()

    (slot_dir / "reel.json").write_text(json.dumps({
        "episode": episode,
        "duration_seconds": round(float(duration), 2),
        "size_bytes": mp4.stat().st_size,
        "video_url": f"{RELEASE_URL}/{asset}",
        "cover": "cover.jpg",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"queued {episode} -> {slot}")


if __name__ == "__main__":
    main()
