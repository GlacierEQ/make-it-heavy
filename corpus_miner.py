from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS conversations (
    context_uuid TEXT PRIMARY KEY,
    context_title TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    mode TEXT,
    collection_uuid TEXT,
    source_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    entry_uuid TEXT PRIMARY KEY,
    context_uuid TEXT NOT NULL REFERENCES conversations(context_uuid) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    answer TEXT NOT NULL DEFAULT '',
    query_sha256 TEXT NOT NULL,
    answer_sha256 TEXT NOT NULL,
    pair_sha256 TEXT NOT NULL,
    query_status TEXT,
    answer_status TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_context ON entries(context_uuid, ordinal);
CREATE INDEX IF NOT EXISTS idx_entries_pair_sha ON entries(pair_sha256);
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    entry_uuid UNINDEXED,
    context_uuid UNINDEXED,
    title,
    query,
    answer,
    tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS corpus_tags (
    entry_uuid TEXT NOT NULL REFERENCES entries(entry_uuid) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    hits INTEGER NOT NULL,
    PRIMARY KEY (entry_uuid, tag)
);
"""

DEFAULT_VECTORS: dict[str, tuple[str, ...]] = {
    "github": ("github", "repository", "repo", "pull request", "commit"),
    "notion": ("notion",),
    "supabase": ("supabase", "postgres", "postgresql"),
    "supermemory": ("supermemory",),
    "helix": ("helix",),
    "aspen_grove": ("aspen grove",),
    "project_cataclysm": ("project cataclysm", "cataclysm"),
    "tower_of_babel": ("tower of babel",),
}

SECRET_PATTERNS = {
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "openai_like_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private_key_header": re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
}

MAX_SEARCH_RESULTS = 200


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _conversation_member(zf: zipfile.ZipFile) -> str:
    json_members = [name for name in zf.namelist() if name.lower().endswith(".json")]
    preferred = [name for name in json_members if "conversation" in name.lower()]
    candidates = preferred or json_members
    if not candidates:
        raise ValueError("archive contains no JSON corpus")
    return sorted(candidates)[0]


def load_conversations(source: str | Path) -> tuple[str, list[dict[str, Any]]]:
    source_path = Path(source)
    if source_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(source_path) as archive:
            member = _conversation_member(archive)
            with archive.open(member) as stream:
                payload = json.load(stream)
            source_name = f"{source_path.name}:{member}"
    else:
        with source_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        source_name = source_path.name

    conversations = payload.get("conversations") if isinstance(payload, dict) else payload
    if not isinstance(conversations, list):
        raise ValueError("expected a conversation list or {'conversations': [...]} payload")
    return source_name, [row for row in conversations if isinstance(row, dict)]


def init_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _status(entry: Mapping[str, Any], key: str) -> str | None:
    value = entry.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for candidate in ("status", "state"):
            nested = value.get(candidate)
            if isinstance(nested, str):
                return nested
    return None


def _reconcile_source_snapshot(
    conn: sqlite3.Connection,
    source_name: str,
    live_contexts: set[str],
) -> None:
    prior_contexts = {
        str(row["context_uuid"])
        for row in conn.execute(
            "SELECT context_uuid FROM conversations WHERE source_name = ?",
            (source_name,),
        )
    }
    stale_contexts = sorted(prior_contexts - live_contexts)
    for context_uuid in stale_contexts:
        stale_entry_ids = [
            str(row["entry_uuid"])
            for row in conn.execute(
                "SELECT entry_uuid FROM entries WHERE context_uuid = ?",
                (context_uuid,),
            )
        ]
        for entry_uuid in stale_entry_ids:
            conn.execute("DELETE FROM entries_fts WHERE entry_uuid = ?", (entry_uuid,))
        conn.execute("DELETE FROM conversations WHERE context_uuid = ?", (context_uuid,))


def ingest(source: str | Path, db_path: str | Path) -> dict[str, int]:
    source_name, conversations = load_conversations(source)
    conn = init_db(db_path)
    counts = Counter()
    try:
        live_contexts = {
            str(conv.get("context_uuid") or "").strip()
            for conv in conversations
            if str(conv.get("context_uuid") or "").strip()
        }
        with conn:
            _reconcile_source_snapshot(conn, source_name, live_contexts)
            for conv in conversations:
                context_uuid = str(conv.get("context_uuid") or "").strip()
                if not context_uuid:
                    counts["skipped_conversations"] += 1
                    continue
                title = str(conv.get("context_title") or "").strip()
                existing_context = conn.execute(
                    "SELECT source_name FROM conversations WHERE context_uuid = ?",
                    (context_uuid,),
                ).fetchone()
                if (
                    existing_context is not None
                    and str(existing_context["source_name"]) != source_name
                ):
                    raise ValueError(
                        f"context_uuid collision across sources: {context_uuid}"
                    )
                conn.execute(
                    """INSERT INTO conversations
                    (context_uuid, context_title, created_at, updated_at, mode, collection_uuid, source_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(context_uuid) DO UPDATE SET
                        context_title = excluded.context_title,
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at,
                        mode = excluded.mode,
                        collection_uuid = excluded.collection_uuid,
                        source_name = excluded.source_name""",
                    (
                        context_uuid,
                        title,
                        conv.get("created_at"),
                        conv.get("updated_at"),
                        conv.get("mode"),
                        conv.get("collection_uuid"),
                        source_name,
                    ),
                )
                counts["conversations"] += 1

                live_entry_ids: set[str] = set()
                for ordinal, entry in enumerate(conv.get("entries") or []):
                    if not isinstance(entry, dict):
                        counts["skipped_entries"] += 1
                        continue
                    entry_uuid = str(entry.get("entry_uuid") or "").strip()
                    if not entry_uuid:
                        counts["skipped_entries"] += 1
                        continue
                    live_entry_ids.add(entry_uuid)
                    query = str(entry.get("query") or "")
                    answer = str(entry.get("answer") or "")
                    qsha, asha = _sha(query), _sha(answer)
                    pair_sha = _sha(f"{qsha}:{asha}")
                    existing_entry = conn.execute(
                        "SELECT context_uuid FROM entries WHERE entry_uuid = ?",
                        (entry_uuid,),
                    ).fetchone()
                    if (
                        existing_entry is not None
                        and str(existing_entry["context_uuid"]) != context_uuid
                    ):
                        raise ValueError(
                            f"entry_uuid collision across conversations: {entry_uuid}"
                        )
                    conn.execute(
                        """INSERT INTO entries
                        (entry_uuid, context_uuid, ordinal, query, answer, query_sha256, answer_sha256,
                         pair_sha256, query_status, answer_status, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(entry_uuid) DO UPDATE SET
                            ordinal = excluded.ordinal,
                            query = excluded.query,
                            answer = excluded.answer,
                            query_sha256 = excluded.query_sha256,
                            answer_sha256 = excluded.answer_sha256,
                            pair_sha256 = excluded.pair_sha256,
                            query_status = excluded.query_status,
                            answer_status = excluded.answer_status,
                            raw_json = excluded.raw_json""",
                        (
                            entry_uuid,
                            context_uuid,
                            ordinal,
                            query,
                            answer,
                            qsha,
                            asha,
                            pair_sha,
                            _status(entry, "query_status"),
                            _status(entry, "answer_status"),
                            json.dumps(entry, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                    conn.execute(
                        "DELETE FROM entries_fts WHERE entry_uuid = ?",
                        (entry_uuid,),
                    )
                    conn.execute(
                        "INSERT INTO entries_fts(entry_uuid, context_uuid, title, query, answer) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (entry_uuid, context_uuid, title, query, answer),
                    )
                    counts["entries"] += 1

                stale_entries = [
                    str(row["entry_uuid"])
                    for row in conn.execute(
                        "SELECT entry_uuid FROM entries WHERE context_uuid = ?",
                        (context_uuid,),
                    )
                    if str(row["entry_uuid"]) not in live_entry_ids
                ]
                for entry_uuid in stale_entries:
                    conn.execute(
                        "DELETE FROM entries_fts WHERE entry_uuid = ?",
                        (entry_uuid,),
                    )
                    conn.execute("DELETE FROM entries WHERE entry_uuid = ?", (entry_uuid,))
                    counts["removed_stale_entries"] += 1
        return dict(counts)
    finally:
        conn.close()


def classify(
    db_path: str | Path,
    vectors: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, int]:
    active_vectors = DEFAULT_VECTORS if vectors is None else dict(vectors)
    conn = init_db(db_path)
    totals: dict[str, int] = {}
    try:
        with conn:
            conn.execute("DELETE FROM corpus_tags")
            for row in conn.execute("SELECT entry_uuid, query, answer FROM entries"):
                haystack = f"{row['query']}\n{row['answer']}".lower()
                for tag, needles in active_vectors.items():
                    normalized_needles = [
                        str(needle).strip().lower()
                        for needle in needles
                        if str(needle).strip()
                    ]
                    hits = sum(haystack.count(needle) for needle in normalized_needles)
                    if not hits:
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO corpus_tags(entry_uuid, tag, hits) "
                        "VALUES (?, ?, ?)",
                        (row["entry_uuid"], str(tag), hits),
                    )
                    totals[str(tag)] = totals.get(str(tag), 0) + 1
        return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))
    finally:
        conn.close()


def secret_inventory(db_path: str | Path) -> dict[str, dict[str, int]]:
    conn = init_db(db_path)
    out: dict[str, dict[str, int]] = {}
    try:
        rows = list(conn.execute("SELECT query, answer FROM entries"))
        for label, pattern in SECRET_PATTERNS.items():
            occurrence_count = 0
            entry_count = 0
            unique_hashes: set[str] = set()
            for row in rows:
                matches = pattern.findall(f"{row['query']}\n{row['answer']}")
                if not matches:
                    continue
                entry_count += 1
                occurrence_count += len(matches)
                unique_hashes.update(_sha(match) for match in matches)
            out[label] = {
                "occurrences": occurrence_count,
                "entries": entry_count,
                "distinct_sha256": len(unique_hashes),
            }
        return out
    finally:
        conn.close()


def summarize(db_path: str | Path) -> dict[str, Any]:
    conn = init_db(db_path)
    try:
        duplicate_pairs = conn.execute(
            "SELECT COALESCE(SUM(n - 1), 0) FROM "
            "(SELECT COUNT(*) AS n FROM entries GROUP BY pair_sha256 HAVING n > 1)"
        ).fetchone()[0]
        return {
            "conversations": conn.execute(
                "SELECT COUNT(*) FROM conversations"
            ).fetchone()[0],
            "entries": conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0],
            "duplicate_pair_excess": duplicate_pairs,
            "empty_queries": conn.execute(
                "SELECT COUNT(*) FROM entries WHERE query = ''"
            ).fetchone()[0],
            "empty_answers": conn.execute(
                "SELECT COUNT(*) FROM entries WHERE answer = ''"
            ).fetchone()[0],
            "tagged_entries": dict(
                conn.execute(
                    "SELECT tag, COUNT(*) FROM corpus_tags "
                    "GROUP BY tag ORDER BY COUNT(*) DESC"
                )
            ),
            "secret_inventory": secret_inventory(db_path),
        }
    finally:
        conn.close()


def search(db_path: str | Path, query: str, limit: int = 20) -> list[dict[str, Any]]:
    normalized_query = str(query).strip()
    if not normalized_query:
        raise ValueError("search query must not be empty")
    bounded_limit = min(MAX_SEARCH_RESULTS, max(1, int(limit)))
    conn = init_db(db_path)
    try:
        rows = conn.execute(
            """SELECT e.entry_uuid, e.context_uuid, c.context_title, e.ordinal,
                      snippet(entries_fts, 3, '[', ']', ' … ', 24) AS query_snippet,
                      snippet(entries_fts, 4, '[', ']', ' … ', 36) AS answer_snippet
               FROM entries_fts
               JOIN entries e USING(entry_uuid)
               JOIN conversations c ON c.context_uuid = e.context_uuid
               WHERE entries_fts MATCH ?
               ORDER BY bm25(entries_fts), e.context_uuid, e.ordinal
               LIMIT ?""",
            (normalized_query, bounded_limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mine conversation exports into a provenance-preserving SQLite corpus."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_parser = sub.add_parser("ingest")
    ingest_parser.add_argument("source")
    ingest_parser.add_argument("--db", default="corpus.db")
    classify_parser = sub.add_parser("classify")
    classify_parser.add_argument("--db", default="corpus.db")
    summary_parser = sub.add_parser("summary")
    summary_parser.add_argument("--db", default="corpus.db")
    search_parser = sub.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--db", default="corpus.db")
    search_parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)

    if args.command == "ingest":
        result = ingest(args.source, args.db)
    elif args.command == "classify":
        result = classify(args.db)
    elif args.command == "summary":
        result = summarize(args.db)
    else:
        result = search(args.db, args.query, args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
