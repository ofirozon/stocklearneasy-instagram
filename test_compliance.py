import json
import tempfile
import unittest
from pathlib import Path

import compliance


def cfg(text):
    p = Path(tempfile.mkdtemp()) / "compliance.json"
    p.write_text(text)
    return p


class Switches(unittest.TestCase):
    def test_shipped_config_is_off(self):
        self.assertFalse(compliance.rss_headlines_allowed())
        self.assertFalse(compliance.yahoo_display_allowed())
        self.assertFalse(compliance.autofill_allowed())

    def test_autofill_off_queues_nothing(self):
        import contextlib
        import io
        from unittest import mock
        try:
            import generate
        except ImportError as e:  # Pillow is only in the queue venv
            self.skipTest(str(e))
        boom = AssertionError("autofill is off, nothing may be built")
        with mock.patch.object(compliance, "autofill_allowed", return_value=False), \
                mock.patch.object(generate, "fetch_headlines", side_effect=boom), \
                mock.patch.object(generate, "next_free_slots", side_effect=boom), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(generate.main())
        self.assertIn("Autofill is off", out.getvalue())

    def test_autofill_on_only_when_explicitly_true(self):
        self.assertTrue(compliance.autofill_allowed(cfg(json.dumps({"autofill_allowed": True}))))
        self.assertFalse(compliance.autofill_allowed(cfg(json.dumps({"autofill_allowed": "true"}))))

    def test_on_only_when_explicitly_true(self):
        on = cfg(json.dumps({"rss_headlines_allowed": True, "yahoo_display_allowed": True}))
        self.assertTrue(compliance.rss_headlines_allowed(on))
        self.assertTrue(compliance.yahoo_display_allowed(on))
        for v in ("true", 1, "yes", None):
            self.assertFalse(compliance.rss_headlines_allowed(cfg(json.dumps({"rss_headlines_allowed": v}))), v)

    def test_missing_or_malformed_fails_closed(self):
        self.assertFalse(compliance.yahoo_display_allowed(Path("/nonexistent/compliance.json")))
        self.assertFalse(compliance.yahoo_display_allowed(cfg("{not json")))
        self.assertFalse(compliance.yahoo_display_allowed(cfg("[]")))

    def test_switches_are_independent(self):
        c = cfg(json.dumps({"rss_headlines_allowed": True}))
        self.assertTrue(compliance.rss_headlines_allowed(c))
        self.assertFalse(compliance.yahoo_display_allowed(c))

    def test_require_raises_with_what(self):
        with self.assertRaises(RuntimeError) as cm:
            compliance.require_yahoo_display("the market-update layout")
        self.assertIn("market-update layout", str(cm.exception))
        compliance.require_yahoo_display("x", cfg(json.dumps({"yahoo_display_allowed": True})))


if __name__ == "__main__":
    unittest.main()
