from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from corpus_miner import ingest
from recovery_candidate_ranker import candidate_report, rank_recovery_candidates


class RecoveryCandidateRankerTests(unittest.TestCase):
    def _build_db(self, root: Path) -> Path:
        payload = [
            {
                "context_uuid": "restore-1",
                "context_title": "Job app restoration",
                "entries": [
                    {
                        "entry_uuid": "e-strong",
                        "query": "Restore deleted recruiter runtime from GlacierEQ/job-app-helix",
                        "answer": (
                            "Stranded application capability was removed. Recover feature from "
                            "commit 725e785453ab01350d7b273c94ddb4dac70501af and PR #253; "
                            "tests passed and ATS workflow was executable."
                        ),
                    },
                    {
                        "entry_uuid": "e-weak",
                        "query": "Restore missing docs in GlacierEQ/job-app-helix",
                        "answer": "README cleanup only; no runtime feature.",
                    },
                ],
            },
            {
                "context_uuid": "restore-2",
                "context_title": "Secret-bearing recovery note",
                "entries": [
                    {
                        "entry_uuid": "e-secret",
                        "query": "Recover lost resume runtime GlacierEQ/job-application",
                        "answer": (
                            "runtime commit abcdef1234567890 with token "
                            "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
                        ),
                    }
                ],
            },
            {
                "context_uuid": "noise",
                "context_title": "General discussion",
                "entries": [
                    {
                        "entry_uuid": "e-noise",
                        "query": "job application feature ideas",
                        "answer": "new runtime maybe later",
                    }
                ],
            },
        ]
        source = root / "export.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        db = root / "corpus.db"
        ingest(source, db)
        return db

    def test_ranks_executable_recovery_above_maintenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = self._build_db(Path(tmp))
            ranked = rank_recovery_candidates(db, limit=10, require_repository=True)
            self.assertGreaterEqual(len(ranked), 2)
            self.assertEqual(ranked[0].entry_uuid, "e-strong")
            self.assertIn("GlacierEQ/job-app-helix", ranked[0].repositories)
            self.assertIn("725e785453ab01350d7b273c94ddb4dac70501af", ranked[0].commit_shas)
            self.assertIn(253, ranked[0].pull_requests)
            self.assertGreater(ranked[0].score, ranked[-1].score)

    def test_requires_both_recovery_and_executable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = self._build_db(Path(tmp))
            ranked = rank_recovery_candidates(db, limit=10)
            ids = {candidate.entry_uuid for candidate in ranked}
            self.assertNotIn("e-noise", ids)

    def test_redacts_secrets_but_preserves_evidence_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = self._build_db(Path(tmp))
            ranked = rank_recovery_candidates(db, limit=10)
            secret = next(candidate for candidate in ranked if candidate.entry_uuid == "e-secret")
            self.assertIn("[REDACTED_SECRET]", secret.excerpt)
            self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz1234567890", secret.excerpt)
            self.assertEqual(len(secret.evidence_sha256), 64)

    def test_limit_is_bounded_and_report_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = self._build_db(Path(tmp))
            ranked = rank_recovery_candidates(db, limit=1000)
            report = candidate_report(ranked)
            self.assertEqual(report["schema"], "APEX_RECOVERY_CANDIDATE_RANKING_V1")
            self.assertEqual(report["candidate_count"], len(ranked))
            self.assertLessEqual(len(ranked), 100)


if __name__ == "__main__":
    unittest.main()
