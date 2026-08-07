import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import docket_monitor
from docket_monitor import DocketMonitorConfigurationError, DocketOSINTMonitor


class DocketMonitorTruthBoundaryTests(unittest.TestCase):
    def test_case_scope_is_required_before_output_directory_creation(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "should-not-exist"
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(
                    DocketMonitorConfigurationError, "case_id is required"
                ):
                    DocketOSINTMonitor(output_dir=str(output))
            self.assertFalse(output.exists())

    def test_default_query_uses_only_explicit_case_scope(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            monitor = DocketOSINTMonitor(case_id="CASE-TEST", output_dir=root)
        self.assertEqual(monitor.queries, ['"CASE-TEST"'])

    def test_new_registry_contains_no_manufactured_milestones(self):
        with tempfile.TemporaryDirectory() as root:
            monitor = DocketOSINTMonitor(case_id="CASE-TEST", output_dir=root)
            registry = monitor.load_registry()
        self.assertEqual(registry["docket_milestones"], [])
        self.assertEqual(registry["osint_promotion_policy"], "never_auto_promote")

    def test_existing_registry_must_match_case_scope(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "DOCKET_MONITOR.json"
            path.write_text(
                json.dumps({"case_id": "OTHER", "docket_milestones": []}),
                encoding="utf-8",
            )
            monitor = DocketOSINTMonitor(case_id="CASE-TEST", output_dir=root)
            with self.assertRaisesRegex(
                DocketMonitorConfigurationError, "does not match requested case scope"
            ):
                monitor.load_registry()

    def test_search_leads_are_deduplicated_and_never_promoted(self):
        with tempfile.TemporaryDirectory() as root:
            monitor = DocketOSINTMonitor(
                case_id="CASE-TEST",
                queries=["first", "second"],
                output_dir=root,
            )

            def fake_search(query, limit=3):
                return [
                    {
                        "query": query,
                        "title": "Public result",
                        "url": "https://example.invalid/result",
                        "snippet": "2030-01-02 appears in an unverified snippet",
                        "observed_at": "2030-01-01T00:00:00+00:00",
                        "verification_status": "unverified_source",
                        "promoted_to_docket": False,
                    }
                ]

            monitor.search_ddg = fake_search
            registry = monitor.run_monitor()

        self.assertEqual(len(registry["osint_findings"]), 1)
        self.assertEqual(registry["docket_milestones"], [])
        self.assertEqual(
            registry["osint_findings"][0]["verification_status"],
            "unverified_source",
        )
        self.assertFalse(registry["osint_findings"][0]["promoted_to_docket"])

    def test_existing_verified_milestones_are_preserved_byte_for_byte(self):
        milestone = {
            "date": "2030-02-03",
            "event": "Verified external workflow event",
            "status": "VERIFIED_RECORD",
        }
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "DOCKET_MONITOR.json"
            path.write_text(
                json.dumps(
                    {
                        "case_id": "CASE-TEST",
                        "docket_milestones": [milestone],
                        "osint_findings": [],
                    }
                ),
                encoding="utf-8",
            )
            monitor = DocketOSINTMonitor(case_id="CASE-TEST", output_dir=root)
            monitor.search_ddg = lambda query, limit=3: [
                {
                    "query": query,
                    "title": "Lead with date",
                    "url": "https://example.invalid/lead",
                    "snippet": "2040-04-05 is only snippet text",
                    "observed_at": "2040-04-01T00:00:00+00:00",
                    "verification_status": "unverified_source",
                    "promoted_to_docket": False,
                }
            ]
            registry = monitor.run_monitor()

        self.assertEqual(registry["docket_milestones"], [milestone])

    def test_memory_write_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as root, patch.object(
            docket_monitor, "MEMORY_SUPPORT", True
        ), patch.object(docket_monitor, "store_memory", create=True) as store_memory:
            monitor = DocketOSINTMonitor(case_id="CASE-TEST", output_dir=root)
            monitor.search_ddg = lambda query, limit=3: [
                {
                    "query": query,
                    "title": "Lead",
                    "url": "https://example.invalid/lead",
                    "snippet": "unverified",
                    "observed_at": "2040-04-01T00:00:00+00:00",
                    "verification_status": "unverified_source",
                    "promoted_to_docket": False,
                }
            ]
            registry = monitor.run_monitor()

        store_memory.assert_not_called()
        self.assertEqual(registry["memory_leads_written"], 0)

    def test_report_does_not_claim_live_sync_or_zero_contradictions(self):
        with tempfile.TemporaryDirectory() as root:
            monitor = DocketOSINTMonitor(case_id="CASE-TEST", output_dir=root)
            registry = monitor._empty_registry()
            registry["last_updated"] = "2040-01-01T00:00:00+00:00"
            monitor.generate_markdown_report(registry)
            report = monitor.md_path.read_text(encoding="utf-8")

        lowered = report.lower()
        self.assertIn("leads, not court-record facts", lowered)
        self.assertNotIn("zero contradictions", lowered)
        self.assertNotIn("synchronized dynamically", lowered)
        self.assertNotIn("live monitoring", lowered)


if __name__ == "__main__":
    unittest.main()
