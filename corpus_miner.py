from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
PRAGMA journal_mode=WAL;
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
    context_uuid TEXT NOT NULL REFERENCES conversations(context_uuid),
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
    entry_uuid TEXT NOT NULL REFERENCES entries(entry_uuid),
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
    "family_case": ("1fdv-23-0001009", "fdv-23-0001009", "family court"),
    "kekoa": ("kekoa",),
    "aspen_grove": ("aspen grove",),
    "project_cataclysm": ("project cataclysm", "cataclysm"),
    "helix": ("helix",),
    "cherry": ("cherry", "cherryshanalei"),
    "usaa": ("usaa",),
    "camaro": ("camaro",),
    "jack_the_ripper": ("jack the ripper",),
    "crystallization": ("crystallization", "metamorphosis"),
    "tower_of_babel": ("tower of babel",),
    "stealth": ("stealth",),
    "microwave": ("microwave",),
}

SECRET_PATTERNS = {
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "openai_like_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private_key_header": re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _conversation_member(zf: zipfile.ZipFile) -> str:
    candidates = [n for n in zf.namelist() if n.lower().endswith(".json") and "conversation" in n.lower()]
    if not candidates:
        candidates = [n for n in zf.namelist() if n.lower().endswith(".json")]
    if not candidates:
        raise ValueError("archive contains no JSON corpus")
    return sorted(candidates)[0]


def load_conversations(source: str | Path) -> tuple[str, list[dict[str, Any]]]:
    source = Path(source)
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            member = _conversation_member(zf)
            with zf.open(member) as fh:
                payload = json.load(fh)
            source_name = f"{source.name}:{member}"
    else:
        with source.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        source_name = source.name

    conversations = payload.get("conversations") if isinstance(payload, dict) else payload
    if not isinstance(conversations, list):
        raise ValueError("expected a conversation list or {'conversations': [...]} payload")
    return source_name, conversations


def init_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def _status(entry: dict[str, Any], key: str) -> str | None:
    value = entry.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for candidate in ("status", "state"):
            if isinstance(value.get(candidate), str):
                return value[candidate]
    return None


def ingest(source: str | Path, db_path: str | Path) -> dict[str, int]:
    source_name, conversations = load_conversations(source)
    conn = init_db(db_path)
    counts = Counter()
    try:
        for conv in conversations:
            context_uuid = str(conv.get("context_uuid") or "").strip()
            if not context_uuid:
                counts["skipped_conversations"] += 1
                continue
            title = str(conv.get("context_title") or "").strip()
            conn.execute(
                """INSERT OR REPLACE INTO conversations
                (context_uuid, context_title, created_at, updated_at, mode, collection_uuid, source_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
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
            for ordinal, entry in enumerate(conv.get("entries") or []):
                entry_uuid = str(entry.get("entry_uuid") or "").strip()
                if not entry_uuid:
                    counts["skipped_entries"] += 1
                    continue
                query = str(entry.get("query") or "")
                answer = str(entry.get("answer") or "")
                qsha, asha = _sha(query), _sha(answer)
                psha = _sha(f"{qsha}:{asha}")
                conn.execute(
                    """INSERT OR REPLACE INTO entries
                    (entry_uuid, context_uuid, ordinal, query, answer, query_sha256, answer_sha256,
                     pair_sha256, query_status, answer_status, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry_uuid,
                        context_uuid,
                        ordinal,
                        query,
                        answer,
                        qsha,
                        asha,
                        psha,
                        _status(entry, "query_status"),
                        _status(entry, "answer_status"),
                        json.dumps(entry, ensure_ascii=False, sort_keys=True),
                    ),
                )
                conn.execute("DELETE FROM entries_fts WHERE entry_uuid = ?", (entry_uuid,))
                conn.execute(
                    "INSERT INTO entries_fts(entry_uuid, context_uuid, title, query, answer) VALUES (?, ?, ?, ?, ?)",
                    (entry_uuid, context_uuid, title, query, answer),
                )
                counts["entries"] += 1
        conn.commit()
    finally:
        conn.close()
    return dict(counts)


def classify(db_path: str | Path, vectors: dict[str, Iterable[str]] | None = None) -> dict[str, int]:
    vectors = vectors or DEFAULT_VECTORS
    conn = sqlite3.connect(db_path)
    totals: dict[str, int] = {}
    try:
        conn.execute("DELETE FROM corpus_tags")
        rows = conn.execute("SELECT entry_uuid, query, answer FROM entries")
        for entry_uuid, query, answer in rows:
            haystack = f"{query}\n{answer}".lower()
            for tag, needles in vectors.items():
                hits = sum(haystack.count(str(needle).lower()) for needle in needles)
                if hits:
                    conn.execute(
                        "INSERT OR REPLACE INTO corpus_tags(entry_uuid, tag, hits) VALUES (?, ?, ?)",
                        (entry_uuid, tag, hits),
                    )
                    totals[tag] = totals.get(tag, 0) + 1
        conn.commit()
    finally:
        conn.close()
    return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))


def secret_inventory(db_path: str | Path) -> dict[str, dict[str, int]]:
    conn = sqlite3.connect(db_path)
    out: dict[str, dict[str, int]] = {}
    try:
        for label, pattern in SECRET_PATTERNS.items():
            occurrence_count = 0
            entry_count = 0
            unique_hashes: set[str] = set()
            for entry_uuid, query, answer in conn.execute("SELECT entry_uuid, query, answer FROM entries"):
                matches = pattern.findall(f"{query}\n{answer}")
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
    finally:
        conn.close()
    return out


def summarize(db_path: str | Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        conversations = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        entries = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        duplicate_pairs = conn.execute(
            "SELECT COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) AS n FROM entries GROUP BY pair_sha256 HAVING n > 1)"
        ).fetchone()[0]
        empty_queries = conn.execute("SELECT COUNT(*) FROM entries WHERE query = ''").fetchone()[0]
        empty_answers = conn.execute("SELECT COUNT(*) FROM entries WHERE answer = ''").fetchone()[0]
        tag_counts = dict(conn.execute("SELECT tag, COUNT(*) FROM corpus_tags GROUP BY tag ORDER BY COUNT(*) DESC"))
        return {
            "conversations": conversations,
            "entries": entries,
            "duplicate_pair_excess": duplicate_pairs,
            "empty_queries": empty_queries,
            "empty_answers": empty_answers,
            "tagged_entries": tag_counts,
            "secret_inventory": secret_inventory(db_path),
        }
    finally:
        conn.close()


def search(db_path: str | Path, query: str, limit: int = 20) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT e.entry_uuid, e.context_uuid, c.context_title, e.ordinal,
                      snippet(entries_fts, 3, '[', ']', ' … ', 24) AS query_snippet,
                      snippet(entries_fts, 4, '[', ']', ' … ', 36) AS answer_snippet
               FROM entries_fts
               JOIN entries e USING(entry_uuid)
               JOIN conversations c ON c.context_uuid = e.context_uuid
               WHERE entries_fts MATCH ?
               LIMIT ?""",
            (query, max(1, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine a conversation export into a provenance-preserving SQLite corpus.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("source")
    p_ingest.add_argument("--db", default="corpus.db")

    p_classify = sub.add_parser("classify")
    p_classify.add_argument("--db", default="corpus.db")

    p_summary = sub.add_parser("summary")
    p_summary.add_argument("--db", default="corpus.db")

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--db", default="corpus.db")
    p_search.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    if args.command == "ingest":
        print(json.dumps(ingest(args.source, args.db), indent=2, sort_keys=True))
    elif args.command == "classify":
        print(json.dumps(classify(args.db), indent=2, sort_keys=True))
    elif args.command == "summary":
        print(json.dumps(summarize(args.db), indent=2, sort_keys=True))
    elif args.command == "search":
        print(json.dumps(search(args.db, args.query, args.limit), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
