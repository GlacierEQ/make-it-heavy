import tempfile
import unittest
from pathlib import Path

from data_lake_inventory import build_manifest, identify_case_and_docket, inventory_file, scan_root


class DataLakeInventoryTests(unittest.TestCase):
    def test_bare_docket_number_is_identified_only_with_case_context(self):
        case, docket = identify_case_and_docket("/Case_1FDV-23-0001009/193.pdf")
        self.assertEqual(case, "1FDV-23-0001009")
        self.assertEqual(docket, 193)
        case, docket = identify_case_and_docket("/random/193.pdf")
        self.assertIsNone(case)
        self.assertIsNone(docket)

    def test_independent_court_acquisitions_are_never_collapsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "1FDV-23-0001009"
            a = root / "download_2025" / "193.pdf"
            b = root / "download_2026" / "193.pdf"
            a.parent.mkdir(parents=True)
            b.parent.mkdir(parents=True)
            a.write_bytes(b"same court bytes")
            b.write_bytes(b"same court bytes")

            records = scan_root(root, source="dropbox")
            manifest = build_manifest(records)
            self.assertEqual(manifest["file_count"], 2)
            self.assertEqual(len(manifest["exact_content_groups"]), 1)
            queue = manifest["court_temporal_comparison_queue"]
            self.assertIn("1FDV-23-0001009:DKT-193", queue)
            self.assertEqual(len(queue["1FDV-23-0001009:DKT-193"]), 2)
            self.assertNotEqual(records[0].acquisition_id, records[1].acquisition_id)
            self.assertFalse(records[0].destructive_deduplication_allowed)
            self.assertFalse(records[1].destructive_deduplication_allowed)

    def test_rename_is_proposed_but_never_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "1FDV-23-0001009" / "DKT 201.pdf"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"court")
            record = inventory_file(path, source="google-drive")
            self.assertEqual(record.rename_state, "PROPOSED")
            self.assertIn("1FDV-23-0001009__DKT-201", record.proposed_name)
            self.assertTrue(path.exists())
            manifest = build_manifest([record])
            self.assertEqual(manifest["mutations_applied"], 0)
            self.assertEqual(manifest["rename_proposals"][0]["state"], "PROPOSED_NOT_APPLIED")

    def test_different_bytes_same_docket_enter_temporal_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "1FDV-23-0001009"
            a = root / "DKT-195.pdf"
            b = root / "copy" / "DKT-195.pdf"
            b.parent.mkdir(parents=True)
            a.write_bytes(b"version A")
            b.write_bytes(b"version B")
            manifest = build_manifest(scan_root(root, source="box"))
            self.assertEqual(len(manifest["exact_content_groups"]), 0)
            self.assertEqual(
                len(manifest["court_temporal_comparison_queue"]["1FDV-23-0001009:DKT-195"]),
                2,
            )


if __name__ == "__main__":
    unittest.main()
