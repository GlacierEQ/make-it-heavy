from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from corpus_miner import init_db

MAX_CANDIDATES = 100

RECOVERY_SIGNALS = {
    "deleted": 8.0,
    "removed": 6.0,
    "lost": 7.0,
    "stranded": 8.0,
    "restore": 5.0,
    "restoration": 5.0,
    "recovery": 5.0,
    "regression": 6.0,
    "clipped": 8.0,
    "missing": 5.0,
    "revert": 3.0,
}
EXECUTABLE_SIGNALS = {
    "runtime": 5.0,
    "feature": 4.0,
    "function": 3.0,
    "workflow": 3.0,
    "api": 4.0,
    "cli": 4.0,
    "deploy": 5.0,
    "application": 6.0,
    "recruiter": 6.0,
    "resume": 5.0,
    "job": 5.0,
    "ats": 6.0,
}
PROOF_SIGNALS = {
    "commit": 3.0,
    "sha": 3.0,
    "pull request": 2.0,
    "pr #": 2.0,
    "test": 2.0,
    "passed": 2.0,
    "branch": 2.0,
}
BLOCKER_SIGNALS = {
    "blocked": -2.0,
    "failed": -1.0,
    "broken": -1.0,
}

REPO_RE = re.compile(r"\b(?:github\.com/)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b")
SHA_RE = re.compile(r"\b[0-9a-fA-F]{7,40}\b")
PR_RE = re.compile(r"\b(?:PR|pull request)\s*#?(\d+)\b", re.IGNORECASE)
SECRET_RE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _score_terms(text: str, weighted_terms: dict[str, float]) -> tuple[float, list[str]]:
    lowered = _normalized(text)
    score = 0.0
    hits: list[str] = []
    for term, weight in weighted_terms.items():
        count = lowered.count(term)
        if count:
            score += weight * min(count, 3)
            hits.append(term)
    return score, hits


def _safe_excerpt(text: str, limit: int = 480) -> str:
    redacted = SECRET_RE.sub("[REDACTED_SECRET]", " ".join(text.split()))
    return redacted[:limit]


@dataclass(frozen=True)
class RecoveryCandidate:
    score: float
    entry_uuid: str
    context_uuid: str
    context_title: str
    ordinal: int
    source_name: str
    repositories: tuple[str, ...]
    commit_shas: tuple[str, ...]
    pull_requests: tuple[int, ...]
    recovery_signals: tuple[str, ...]
    executable_signals: tuple[str, ...]
    proof_signals: tuple[str, ...]
    blocker_signals: tuple[str, ...]
    evidence_sha256: str
    excerpt: str


def _candidate_from_row(row: sqlite3.Row) -> RecoveryCandidate | None:
    text = f"{row['context_title']}\n{row['query']}\n{row['answer']}"
    recovery_score, recovery_hits = _score_terms(text, RECOVERY_SIGNALS)
    executable_score, executable_hits = _score_terms(text, EXECUTABLE_SIGNALS)
    proof_score, proof_hits = _score_terms(text, PROOF_SIGNALS)
    blocker_score, blocker_hits = _score_terms(text, BLOCKER_SIGNALS)

    if recovery_score <= 0 or executable_score <= 0:
        return None

    repositories = tuple(sorted(set(REPO_RE.findall(text))))
    commits = tuple(sorted(set(match.lower() for match in SHA_RE.findall(text))))
    prs = tuple(sorted({int(value) for value in PR_RE.findall(text)}))

    provenance_bonus = min(8.0, len(repositories) * 2.0 + len(commits) * 1.5 + len(prs))
    score = recovery_score + executable_score + proof_score + blocker_score + provenance_bonus

    return RecoveryCandidate(
        score=round(score, 2),
        entry_uuid=str(row["entry_uuid"]),
        context_uuid=str(row["context_uuid"]),
        context_title=str(row["context_title"]),
        ordinal=int(row["ordinal"]),
        source_name=str(row["source_name"]),
        repositories=repositories,
        commit_shas=commits,
        pull_requests=prs,
        recovery_signals=tuple(sorted(recovery_hits)),
        executable_signals=tuple(sorted(executable_hits)),
        proof_signals=tuple(sorted(proof_hits)),
        blocker_signals=tuple(sorted(blocker_hits)),
        evidence_sha256=_sha(text),
        excerpt=_safe_excerpt(text),
    )


def rank_recovery_candidates(
    db_path: str | Path,
    *,
    limit: int = 20,
    require_repository: bool = False,
) -> list[RecoveryCandidate]:
    bounded_limit = min(MAX_CANDIDATES, max(1, int(limit)))
    conn = init_db(db_path)
    try:
        rows = conn.execute(
            """SELECT e.entry_uuid, e.context_uuid, e.ordinal, e.query, e.answer,
                      c.context_title, c.source_name
               FROM entries e
               JOIN conversations c ON c.context_uuid = e.context_uuid"""
        ).fetchall()
    finally:
        conn.close()

    candidates = [candidate for row in rows if (candidate := _candidate_from_row(row))]
    if require_repository:
        candidates = [candidate for candidate in candidates if candidate.repositories]
    candidates.sort(key=lambda item: (-item.score, item.context_uuid, item.ordinal, item.entry_uuid))
    return candidates[:bounded_limit]


def candidate_report(candidates: Iterable[RecoveryCandidate]) -> dict[str, object]:
    rows = [asdict(candidate) for candidate in candidates]
    return {
        "schema": "APEX_RECOVERY_CANDIDATE_RANKING_V1",
        "candidate_count": len(rows),
        "candidates": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rank executable stranded/restoration candidates from the provenance corpus "
            "without exposing raw secrets."
        )
    )
    parser.add_argument("--db", default="corpus.db")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--require-repository", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    report = candidate_report(
        rank_recovery_candidates(
            args.db,
            limit=args.limit,
            require_repository=args.require_repository,
        )
    )
    encoded = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
