from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from recovery_candidate_verifier import (
    VerificationError,
    _load_candidates,
    verification_report,
    verify_candidate,
    verify_repository_candidate,
)


DEFAULT_SHA = "d" * 40
DONOR_SHA = "a" * 40


class FakeGitHub:
    def __init__(self, responses: dict[str, Mapping[str, Any] | Exception]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get_json(self, path: str) -> Mapping[str, Any]:
        self.calls.append(path)
        response = self.responses.get(path)
        if isinstance(response, Exception):
            raise response
        if response is None:
            raise AssertionError(f"unexpected GitHub path: {path}")
        return response


def repo_fixture(*, compare_status: str, pr_state: str = "open", merged: bool = False) -> FakeGitHub:
    return FakeGitHub(
        {
            "repos/GlacierEQ/example": {"default_branch": "main"},
            "repos/GlacierEQ/example/commits/main": {"sha": DEFAULT_SHA},
            f"repos/GlacierEQ/example/compare/{DONOR_SHA}...main": {
                "status": compare_status,
                "ahead_by": 4 if compare_status == "ahead" else 0,
                "behind_by": 2 if compare_status == "behind" else 0,
            },
            "repos/GlacierEQ/example/pulls/17": {"state": pr_state, "merged": merged},
        }
    )


class RecoveryCandidateVerifierTests(unittest.TestCase):
    def test_merged_or_ancestor_donor_is_already_restored(self) -> None:
        client = repo_fixture(compare_status="ahead", pr_state="closed", merged=True)
        result = verify_repository_candidate(
            client,
            "GlacierEQ/example",
            donor_sha=DONOR_SHA,
            pr_number=17,
        )
        self.assertEqual(result.classification, "ALREADY_RESTORED")
        self.assertEqual(result.donor_relation, "DONOR_IN_DEFAULT_HISTORY")
        self.assertTrue(result.pull_request_merged)

    def test_open_pr_with_diverged_donor_is_still_stranded_and_executable(self) -> None:
        client = repo_fixture(compare_status="diverged")
        candidate = {
            "score": 91.5,
            "entry_uuid": "entry-1",
            "evidence_sha256": "e" * 64,
            "repositories": ["GlacierEQ/example"],
            "commit_shas": [DONOR_SHA],
            "pull_requests": [17],
        }
        result = verify_candidate(client, candidate)
        self.assertEqual(result.classification, "STILL_STRANDED")
        self.assertTrue(result.executable_now)
        self.assertEqual(result.repositories[0].default_head_sha, DEFAULT_SHA)

    def test_diverged_donor_without_pr_is_currently_missing(self) -> None:
        client = FakeGitHub(
            {
                "repos/GlacierEQ/example": {"default_branch": "main"},
                "repos/GlacierEQ/example/commits/main": {"sha": DEFAULT_SHA},
                f"repos/GlacierEQ/example/compare/{DONOR_SHA}...main": {
                    "status": "diverged",
                    "ahead_by": 2,
                    "behind_by": 3,
                },
            }
        )
        result = verify_repository_candidate(
            client,
            "GlacierEQ/example",
            donor_sha=DONOR_SHA,
            pr_number=None,
        )
        self.assertEqual(result.classification, "CURRENTLY_MISSING")

    def test_missing_donor_fails_closed_without_calling_it_executable(self) -> None:
        client = FakeGitHub(
            {
                "repos/GlacierEQ/example": {"default_branch": "main"},
                "repos/GlacierEQ/example/commits/main": {"sha": DEFAULT_SHA},
                f"repos/GlacierEQ/example/compare/{DONOR_SHA}...main": VerificationError(
                    "GitHub GET compare failed with HTTP 404: missing"
                ),
            }
        )
        candidate = {
            "score": 75,
            "entry_uuid": "entry-missing",
            "evidence_sha256": "f" * 64,
            "repositories": ["GlacierEQ/example"],
            "commit_shas": [DONOR_SHA],
            "pull_requests": [],
        }
        result = verify_candidate(client, candidate)
        self.assertEqual(result.classification, "DONOR_MISSING")
        self.assertFalse(result.executable_now)

    def test_multiple_repositories_do_not_receive_invented_positional_provenance(self) -> None:
        responses = {
            "repos/GlacierEQ/a": {"default_branch": "main"},
            "repos/GlacierEQ/a/commits/main": {"sha": DEFAULT_SHA},
            "repos/GlacierEQ/b": {"default_branch": "main"},
            "repos/GlacierEQ/b/commits/main": {"sha": "c" * 40},
        }
        client = FakeGitHub(responses)
        candidate = {
            "score": 80,
            "entry_uuid": "ambiguous",
            "evidence_sha256": "9" * 64,
            "repositories": ["GlacierEQ/a", "GlacierEQ/b"],
            "commit_shas": ["1" * 40, "2" * 40],
            "pull_requests": [7, 8],
        }
        result = verify_candidate(client, candidate)
        self.assertEqual(result.classification, "REVERIFY_MANUALLY")
        self.assertFalse(result.executable_now)
        self.assertTrue(all(row.donor_sha is None for row in result.repositories))
        self.assertTrue(all(row.pull_request is None for row in result.repositories))

    def test_report_keeps_executable_count_separate_from_historical_candidates(self) -> None:
        stranded = verify_candidate(
            repo_fixture(compare_status="diverged"),
            {
                "score": 90,
                "entry_uuid": "stranded",
                "evidence_sha256": "a" * 64,
                "repositories": ["GlacierEQ/example"],
                "commit_shas": [DONOR_SHA],
                "pull_requests": [17],
            },
        )
        restored = verify_candidate(
            repo_fixture(compare_status="ahead", pr_state="closed", merged=True),
            {
                "score": 88,
                "entry_uuid": "restored",
                "evidence_sha256": "b" * 64,
                "repositories": ["GlacierEQ/example"],
                "commit_shas": [DONOR_SHA],
                "pull_requests": [17],
            },
        )
        report = verification_report([stranded, restored])
        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(report["executable_candidate_count"], 1)

    def test_ranking_loader_rejects_wrong_schema_and_caps_volume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ranking.json"
            path.write_text(json.dumps({"schema": "wrong", "candidates": []}), encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "not an APEX_RECOVERY"):
                _load_candidates(path)

            path.write_text(
                json.dumps(
                    {
                        "schema": "APEX_RECOVERY_CANDIDATE_RANKING_V1",
                        "candidates": [{"entry_uuid": str(index)} for index in range(150)],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(len(_load_candidates(path)), 100)


if __name__ == "__main__":
    unittest.main()
