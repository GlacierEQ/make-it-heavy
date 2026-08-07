from pathlib import Path
import re
import unittest


class PublicSecretHygieneTests(unittest.TestCase):
    def test_deadmans_switch_does_not_publish_memory_context_token(self):
        text = Path("DEADMANS_SWITCH.md").read_text(encoding="utf-8")
        patterns = [
            r"Supermemory Context Key:\s*(?!\[REDACTED)[A-Za-z0-9_-]{16,}",
            r"Supermemory key:\s*(?!\[REDACTED)[A-Za-z0-9_-]{16,}",
        ]
        for pattern in patterns:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, text, flags=re.IGNORECASE))

    def test_redaction_marks_historical_value_compromised(self):
        text = Path("DEADMANS_SWITCH.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("historical value must be treated as compromised"), 2)


if __name__ == "__main__":
    unittest.main()
