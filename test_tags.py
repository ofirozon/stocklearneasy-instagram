"""A/B test tags for the Instagram test plan (stdlib only: no PIL, safe to import anywhere).

When a test is enabled in test_plan/active_test.json, every slot the generators build inside the test window is stamped
with the test id and the arm it belongs to, so the daily insights run can join each post's numbers to its arm.
With no file, or "enabled": false, nothing is stamped and nothing about the generators changes.

Arms alternate by calendar day (day ordinal modulo number of arms), which gives A,B,A,B... across consecutive days and
cancels weekday effects over a few weeks. The key is "test_variant", never "variant": generate.py already stores its own
post variant under "variant" in source.json and reel.py stores full/short/silent under "variant" in reel.json.

    import test_tags
    record.update(test_tags.tags_for(slot, topic=..., hook_text=..., cta_type=..., has_duo=...))
"""
import json
from datetime import date
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "test_plan" / "active_test.json"
FIELDS = ("topic", "hook_text", "length_s", "cta_type", "has_duo")


def load(config=CONFIG):
    """The active test as a dict, or None when there is no file, it is disabled or it is malformed."""
    try:
        d = json.loads(Path(config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("enabled") is not True or not d.get("test_id"):
        return None
    arms = d.get("arms")
    if not (isinstance(arms, list) and len(arms) >= 2 and all(isinstance(a, str) and a for a in arms)):
        return None
    try:
        start, end = date.fromisoformat(d["start"]), date.fromisoformat(d["end"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"test_id": str(d["test_id"]), "arms": arms, "start": start, "end": end}


def arm_for(slot, test):
    """The arm of a slot name such as 2026-12-01T1200, or None when it is outside the test window."""
    try:
        day = date.fromisoformat(str(slot)[:10])
    except ValueError:
        return None
    if not (test["start"] <= day <= test["end"]):
        return None
    return test["arms"][day.toordinal() % len(test["arms"])]


def tags_for(slot, config=CONFIG, **fields):
    """{} when no test applies, else test_id, test_variant and whichever of FIELDS were given (None values are left out)."""
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise TypeError(f"unknown tag fields: {', '.join(sorted(unknown))}")
    test = load(config)
    if test is None:
        return {}
    arm = arm_for(slot, test)
    if arm is None:
        return {}
    out = {"test_id": test["test_id"], "test_variant": arm}
    out.update({k: v for k, v in fields.items() if v is not None})
    return out
