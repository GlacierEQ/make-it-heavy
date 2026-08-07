from pathlib import Path
import unittest


class PublicSecretHygieneTests(unittest.TestCase):
    def test_deadmans_switch_uses_exact_memory_token_redactions(self):
        text = Path("DEADMANS_SWITCH.md").read_text(encoding="utf-8")
        expected = "[REDACTED — historical value must be treated as compromised]"
        labels = ["Supermemory Context Key", "Supermemory key"]

        for label in labels:
            with self.subTest(label=label):
                matches = []
                for line in text.splitlines():
                    marker = f"{label}:"
                    if marker.casefold() in line.casefold():
                        before, value = line.split(":", 1)
                        self.assertTrue(before.casefold().endswith(label.casefold()))
                        matches.append(value.strip())
                self.assertEqual(matches, [expected])

    def test_redaction_marks_historical_value_compromised(self):
        text = Path("DEADMANS_SWITCH.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            text.count("historical value must be treated as compromised"), 2
        )


if __name__ == "__main__":
    unittest.main()
