import json
import tempfile
import unittest
from pathlib import Path

import test_tags


def config(**over):
    d = {"enabled": True, "test_id": "T1", "arms": ["A", "B"], "start": "2026-12-01", "end": "2026-12-31"}
    d.update(over)
    p = Path(tempfile.mkdtemp()) / "active_test.json"
    p.write_text(json.dumps(d))
    return p


class Tags(unittest.TestCase):
    def test_no_file_or_disabled_stamps_nothing(self):
        self.assertEqual(test_tags.tags_for("2026-12-02T1200", config=Path("/nonexistent.json"), topic="x"), {})
        self.assertEqual(test_tags.tags_for("2026-12-02T1200", config=config(enabled=False), topic="x"), {})

    def test_shipped_config_is_disabled(self):
        self.assertEqual(test_tags.tags_for("2026-12-02T1200", topic="x"), {})

    def test_arms_alternate_on_consecutive_days(self):
        c = config()
        arms = [test_tags.tags_for(f"2026-12-{d:02d}T1200", config=c)["test_variant"] for d in range(1, 9)]
        self.assertEqual(arms, ["B", "A"] * 4 if arms[0] == "B" else ["A", "B"] * 4)
        self.assertEqual(len(set(arms[0::2])), 1)
        self.assertNotEqual(arms[0], arms[1])

    def test_window_edges_and_outside(self):
        c = config()
        self.assertEqual(test_tags.tags_for("2026-12-01T1200", config=c)["test_id"], "T1")
        self.assertEqual(test_tags.tags_for("2026-12-31T1200", config=c)["test_id"], "T1")
        self.assertEqual(test_tags.tags_for("2026-11-30T1200", config=c), {})
        self.assertEqual(test_tags.tags_for("2027-01-01T1200", config=c), {})

    def test_fields_copied_and_none_left_out(self):
        t = test_tags.tags_for("2026-12-02T1200", config=config(), topic="inflation", has_duo=True, hook_text=None)
        self.assertEqual((t["topic"], t["has_duo"]), ("inflation", True))
        self.assertNotIn("hook_text", t)

    def test_unknown_field_is_an_error(self):
        with self.assertRaises(TypeError):
            test_tags.tags_for("2026-12-02T1200", config=config(), variant="x")

    def test_malformed_configs_stamp_nothing(self):
        for bad in (dict(arms=["A"]), dict(start="soon"), dict(test_id=""), dict(arms="AB")):
            self.assertEqual(test_tags.tags_for("2026-12-02T1200", config=config(**bad)), {}, bad)
        p = Path(tempfile.mkdtemp()) / "bad.json"
        p.write_text("{not json")
        self.assertEqual(test_tags.tags_for("2026-12-02T1200", config=p), {})

    def test_bad_slot_name(self):
        self.assertEqual(test_tags.tags_for("not-a-slot", config=config()), {})


if __name__ == "__main__":
    unittest.main()
