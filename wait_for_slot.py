"""Hold a publish run until the next queued slot is due (added 10.11.2026).

GitHub's */10 schedule is delivered every 3 to 4 hours in practice. While the
Mac is awake it kicks this workflow minutes after each slot, so posts go out
on time; while it sleeps the cloud cron is the only trigger, and 21 of 80
slots since 1.10.2026 went out more than 30 minutes late, up to 8 hours
(9.11: the 12:00 reel at 19:51 UTC, reach 1). A run that lands before a slot
therefore waits for it here instead of exiting with "Nothing due", so one
cron tick every few hours is enough to publish on time.

Exits 0 immediately when a slot is already due or none is close. Stdlib only.
The workflow re-pulls the branch after this step, so a slot the Mac held or
rebuilt during the wait is read fresh.
"""
import os
import pathlib
import time
from datetime import datetime, timezone

SCHEDULED = pathlib.Path(__file__).resolve().parent / "scheduled"
# Must stay under the job's timeout-minutes, with room for the publish itself.
WAIT_MAX_MIN = float(os.environ.get("WAIT_MAX_MIN", "290"))


def slots():
    if not SCHEDULED.is_dir():
        return []
    out = []
    for d in SCHEDULED.iterdir():
        # A folder without caption.txt is a leftover, not a post (item 70a).
        if not d.is_dir() or not (d / "caption.txt").is_file():
            continue
        try:
            out.append(datetime.strptime(d.name, "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc))
        except ValueError:
            pass
    return sorted(out)


def main():
    now = datetime.now(timezone.utc)
    queued = slots()
    if not queued:
        print("wait: queue empty")
        return
    if queued[0] <= now:
        print(f"wait: {queued[0]:%Y-%m-%dT%H%M} already due, no wait")
        return
    secs = (queued[0] - now).total_seconds()
    if secs > WAIT_MAX_MIN * 60:
        print(f"wait: next slot {queued[0]:%Y-%m-%dT%H%M} is {secs/60:.0f} min away, not waiting")
        return
    print(f"wait: sleeping {secs/60:.1f} min for {queued[0]:%Y-%m-%dT%H%M}", flush=True)
    time.sleep(secs + 20)


if __name__ == "__main__":
    main()
