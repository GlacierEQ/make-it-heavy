import tempfile
import unittest
from pathlib import Path

from data_lake_temporal_audit import audit_pair, compare_files, fingerprint_file, first_difference_offset


class TemporalCourtAuditTests(unittest.TestCase):
    def test_byte_identical_copies_preserve_distinct_acquisitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "193_early.pdf"
            right = root / "193_later.pdf"
            payload = b"%PDF-1.7\nidentical court record\n%%EOF\n"
            left.write_bytes(payload)
            right.write_bytes(payload)

            report = audit_pair(
                left,
                right,
                document_id="1FDV-23-0001009:DKT-193",
                left_acquisition_id="ACQ-193-001",
                right_acquisition_id="ACQ-193-002",
                left_source="gmail-nef",
                right_source="later-court-download",
                left_acquired_at="2025-06-24T15:14:00-10:00",
                right_acquired_at="2026-08-24T12:00:00-10:00",
            )

            self.assertEqual(report["comparison"]["classification"], "BYTE_IDENTICAL")
            self.assertFalse(report["destructive_deduplication_allowed"])
            self.assertEqual(len(report["acquisitions"]), 2)
            self.assertNotEqual(
                report["acquisitions"][0]["acquisition_id"],
                report["acquisitions"][1]["acquisition_id"],
            )
            self.assertEqual(report["next_action"], "PRESERVE_ACQUISITION_PROVENANCE")

    def test_one_byte_change_escalates_and_reports_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "order_a.pdf"
            right = root / "order_b.pdf"
            left.write_bytes(b"ABCDEF")
            right.write_bytes(b"ABCXEF")

            comparison = compare_files(
                left,
                right,
                left_acquisition_id="A",
                right_acquisition_id="B",
            )
            self.assertFalse(comparison.byte_identical)
            self.assertEqual(comparison.first_difference_offset, 3)
            self.assertEqual(
                comparison.classification,
                "BINARY_DIFFERENT_REQUIRES_FORENSIC_DELTA",
            )

    def test_size_only_difference_reports_first_appended_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "left.pdf"
            right = root / "right.pdf"
            left.write_bytes(b"ABC")
            right.write_bytes(b"ABCDEF")
            self.assertEqual(first_difference_offset(left, right), 3)

    def test_fingerprint_uses_two_independent_digests(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.pdf"
            path.write_bytes(b"court record")
            fp = fingerprint_file(path)
            self.assertEqual(fp.byte_size, 12)
            self.assertEqual(len(fp.sha256), 64)
            self.assertEqual(len(fp.sha512), 128)


if __name__ == "__main__":
    unittest.main()
