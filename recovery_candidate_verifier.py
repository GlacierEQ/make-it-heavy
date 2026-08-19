from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
MAX_CANDIDATES = 100


class VerificationError(RuntimeError):
    """Raised when live candidate verification cannot preserve attribution."""


class GitHubReader(Protocol):
    def get_json(self, path: str) -> Mapping[str, Any]: ...


class GitHubAPI:
    """Small read-only GitHub REST client for recovery-state verification."""

    def __init__(self, token: str | None = None, *, api_url: str = "https://api.github.com") -> None:
        self.token = (token or "").strip()
        self.api_url = api_url.rstrip("/")

    def get_json(self, path: str) -> Mapping[str, Any]:
        url = f"{self.api_url}/{path.lstrip('/')}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "GlacierEQ-Recovery-Candidate-Verifier/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise VerificationError(f"GitHub GET {path} failed with HTTP {exc.code}: {body[:240]}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise VerificationError(f"GitHub GET {path} failed: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise VerificationError(f"GitHub GET {path} returned a non-object payload")
        return payload


@dataclass(frozen=True)
class RepositoryVerification:
    repository: str
    default_branch: str
    default_head_sha: str
    donor_sha: str | None
    donor_relation: str
    pull_request: int | None
    pull_request_state: str | None
    pull_request_merged: bool | None
    classification: str
    reason: str


@dataclass(frozen=True)
class VerifiedCandidate:
    source_score: float
    entry_uuid: str
    evidence_sha256: str
    repositories: tuple[RepositoryVerification, ...]
    classification: str
    executable_now: bool


def _repo_path(repository: str, suffix: str = "") -> str:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise VerificationError(f"invalid repository identity: {repository!r}")
    return f"repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}{suffix}"


def _load_candidates(path: str | Path) -> list[Mapping[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema") != "APEX_RECOVERY_CANDIDATE_RANKING_V1":
        raise VerificationError("input is not an APEX_RECOVERY_CANDIDATE_RANKING_V1 report")
    rows = payload.get("candidates")
    if not isinstance(rows, list):
        raise VerificationError("ranking report candidates must be a list")
    return [row for row in rows if isinstance(row, Mapping)][:MAX_CANDIDATES]


def _full_donor_shas(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    raw = candidate.get("commit_shas", ())
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(str(value).lower() for value in raw if FULL_SHA_RE.fullmatch(str(value)))


def _pull_requests(candidate: Mapping[str, Any]) -> tuple[int, ...]:
    raw = candidate.get("pull_requests", ())
    if not isinstance(raw, (list, tuple)):
        return ()
    values: list[int] = []
    for value in raw:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            values.append(parsed)
    return tuple(sorted(set(values)))


def _compare_relation(client: GitHubReader, repository: str, donor_sha: str, default_branch: str) -> str:
    suffix = f"/compare/{urllib.parse.quote(donor_sha, safe='')}...{urllib.parse.quote(default_branch, safe='')}"
    try:
        comparison = client.get_json(_repo_path(repository, suffix))
    except VerificationError as exc:
        if "HTTP 404" in str(exc) or "HTTP 422" in str(exc):
            return "DONOR_UNRESOLVED"
        raise
    status = str(comparison.get("status") or "").lower()
    ahead_by = int(comparison.get("ahead_by") or 0)
    behind_by = int(comparison.get("behind_by") or 0)
    if status == "identical":
        return "DEFAULT_AT_DONOR"
    if status == "ahead" and ahead_by >= 0:
        return "DONOR_IN_DEFAULT_HISTORY"
    if status == "behind" and behind_by > 0:
        return "DEFAULT_BEHIND_DONOR"
    if status == "diverged":
        return "DIVERGED_FROM_DEFAULT"
    return "UNKNOWN_RELATION"


def _pr_state(client: GitHubReader, repository: str, pr_number: int | None) -> tuple[str | None, bool | None]:
    if pr_number is None:
        return None, None
    try:
        payload = client.get_json(_repo_path(repository, f"/pulls/{pr_number}"))
    except VerificationError as exc:
        if "HTTP 404" in str(exc):
            return "NOT_FOUND", False
        raise
    state = str(payload.get("state") or "UNKNOWN").upper()
    merged = payload.get("merged")
    return state, bool(merged) if isinstance(merged, bool) else None


def verify_repository_candidate(
    client: GitHubReader,
    repository: str,
    *,
    donor_sha: str | None,
    pr_number: int | None,
) -> RepositoryVerification:
    repo = client.get_json(_repo_path(repository))
    default_branch = str(repo.get("default_branch") or "").strip()
    if not default_branch:
        raise VerificationError(f"{repository} did not expose a default branch")
    default = client.get_json(_repo_path(repository, f"/commits/{urllib.parse.quote(default_branch, safe='')}"))
    default_head_sha = str(default.get("sha") or "").lower()
    if not FULL_SHA_RE.fullmatch(default_head_sha):
        raise VerificationError(f"{repository} returned an invalid default-branch head SHA")

    donor_relation = "NO_DONOR_SHA"
    if donor_sha:
        donor_relation = _compare_relation(client, repository, donor_sha, default_branch)
    pr_state, pr_merged = _pr_state(client, repository, pr_number)

    if pr_merged is True or donor_relation in {"DEFAULT_AT_DONOR", "DONOR_IN_DEFAULT_HISTORY"}:
        classification = "ALREADY_RESTORED"
        reason = "donor lineage is already reachable from the default branch or the referenced PR is merged"
    elif pr_state == "OPEN" and donor_relation in {"DEFAULT_BEHIND_DONOR", "DIVERGED_FROM_DEFAULT", "UNKNOWN_RELATION"}:
        classification = "STILL_STRANDED"
        reason = "referenced PR remains open and donor lineage is not in default-branch history"
    elif donor_relation == "DONOR_UNRESOLVED":
        classification = "DONOR_MISSING"
        reason = "the attributed donor SHA is not resolvable in the repository"
    elif pr_state == "CLOSED" and pr_merged is False:
        classification = "SUPERSEDED_OR_ABANDONED"
        reason = "referenced PR is closed without merge and donor lineage is not established in default history"
    elif donor_relation in {"DEFAULT_BEHIND_DONOR", "DIVERGED_FROM_DEFAULT"}:
        classification = "CURRENTLY_MISSING"
        reason = "donor lineage exists but is not reachable from the current default branch"
    else:
        classification = "REVERIFY_MANUALLY"
        reason = "available GitHub lineage evidence is insufficient for automatic restoration status"

    return RepositoryVerification(
        repository=repository,
        default_branch=default_branch,
        default_head_sha=default_head_sha,
        donor_sha=donor_sha,
        donor_relation=donor_relation,
        pull_request=pr_number,
        pull_request_state=pr_state,
        pull_request_merged=pr_merged,
        classification=classification,
        reason=reason,
    )


def verify_candidate(client: GitHubReader, candidate: Mapping[str, Any]) -> VerifiedCandidate:
    repositories_raw = candidate.get("repositories", ())
    repositories = tuple(sorted({str(value) for value in repositories_raw if str(value).strip()})) if isinstance(repositories_raw, (list, tuple)) else ()
    donor_shas = _full_donor_shas(candidate)
    prs = _pull_requests(candidate)
    evidence_sha256 = str(candidate.get("evidence_sha256") or "")
    entry_uuid = str(candidate.get("entry_uuid") or "")
    source_score = float(candidate.get("score") or 0.0)

    verified: list[RepositoryVerification] = []
    for index, repository in enumerate(repositories):
        donor_sha = donor_shas[index] if index < len(donor_shas) else (donor_shas[0] if len(donor_shas) == 1 else None)
        pr_number = prs[index] if index < len(prs) else (prs[0] if len(prs) == 1 else None)
        verified.append(
            verify_repository_candidate(
                client,
                repository,
                donor_sha=donor_sha,
                pr_number=pr_number,
            )
        )

    states = {row.classification for row in verified}
    if "STILL_STRANDED" in states:
        classification = "STILL_STRANDED"
    elif "CURRENTLY_MISSING" in states:
        classification = "CURRENTLY_MISSING"
    elif verified and states == {"ALREADY_RESTORED"}:
        classification = "ALREADY_RESTORED"
    elif "DONOR_MISSING" in states:
        classification = "DONOR_MISSING"
    elif "SUPERSEDED_OR_ABANDONED" in states:
        classification = "SUPERSEDED_OR_ABANDONED"
    else:
        classification = "REVERIFY_MANUALLY"

    return VerifiedCandidate(
        source_score=source_score,
        entry_uuid=entry_uuid,
        evidence_sha256=evidence_sha256,
        repositories=tuple(verified),
        classification=classification,
        executable_now=classification in {"STILL_STRANDED", "CURRENTLY_MISSING"},
    )


def verification_report(candidates: Iterable[VerifiedCandidate]) -> dict[str, object]:
    rows = [asdict(candidate) for candidate in candidates]
    executable = [row for row in rows if row["executable_now"]]
    return {
        "schema": "APEX_RECOVERY_CANDIDATE_VERIFICATION_V1",
        "candidate_count": len(rows),
        "executable_candidate_count": len(executable),
        "candidates": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify ranked recovery candidates against current GitHub lineage before mutation."
    )
    parser.add_argument("--ranking", required=True)
    parser.add_argument("--output")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--api-url", default="https://api.github.com")
    args = parser.parse_args(argv)

    client = GitHubAPI(os.environ.get(args.token_env), api_url=args.api_url)
    verified = [verify_candidate(client, candidate) for candidate in _load_candidates(args.ranking)]
    verified.sort(key=lambda row: (not row.executable_now, -row.source_score, row.entry_uuid))
    report = verification_report(verified)
    encoded = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
