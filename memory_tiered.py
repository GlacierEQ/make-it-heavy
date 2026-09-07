# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""Tiered memory architecture for chatbots/assistants.

Three tiers, all user-scoped:
  - ShortTermMemory: last N turns per user (volatile, session-scoped)
  - LongTermMemory:  consolidated memories (FTS5 + recency decay)
  - EntityMemory:    typed facts about people/projects/preferences (deduped, conflict-tracked)

Retrieval combines BM25 (FTS5) + tier weight + exponential recency decay.
Every read/write is logged to memory_audit for lineage.
"""

import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---- Tunables (single source of truth) --------------------------------------

STM_MAX_TURNS = 20                 # short-term window per user
STM_TTL_SECONDS = 24 * 3600        # short-term TTL
LTM_TTL_SECONDS = 90 * 24 * 3600   # long-term TTL
LTM_ACCESS_REFRESH = True          # touch last_accessed on read
RECENCY_HALF_LIFE_DAYS = 30.0      # recency decay constant

TIER_WEIGHT_STM = 0.3
TIER_WEIGHT_LTM = 1.0
TIER_WEIGHT_ENTITY = 1.5

ENTITY_DEFAULT_CONFIDENCE = 0.5
ENTITY_CONFLICT_THRESHOLD = 0.2    # new fact must beat existing by this much

# Conservative FTS5 stopword set (matches SQLite's default behaviour for common words).
_FTS5_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "this", "to", "was", "were", "will", "with", "do", "does", "did",
    "what", "where", "when", "who", "which", "how", "i", "you", "we",
    "they", "he", "she", "my", "your", "our", "their", "me", "us", "them",
})


# ---- Result types -----------------------------------------------------------

@dataclass
class MemoryHit:
    tier: str           # "stm" | "ltm" | "entity"
    score: float
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    entity_type: Optional[str] = None
    entity_key: Optional[str] = None
    confidence: float = 0.0
    age_days: float = 0.0

    def to_prompt_snippet(self) -> str:
        if self.tier == "entity":
            return f"[{self.entity_type}:{self.entity_key}] {self.text} (conf={self.confidence:.2f})"
        return f"[{self.tier} age={self.age_days:.1f}d] {self.text}"


# ---- Core -------------------------------------------------------------------

class TieredMemory:
    """Per-user isolated, tiered, FTS5-indexed memory store."""

    def __init__(self, db_path: str = ".tiered_memory.db", tiered_config: Optional[dict] = None):
        self.db_path = db_path
        cfg = tiered_config or {}
        # Config-driven windows/TTLs; defaults mirror the module constants so
        # existing behaviour is preserved when no config is supplied.
        self.stm_max_turns = int(cfg.get("stm_max_turns", STM_MAX_TURNS))
        self.stm_ttl_seconds = int(cfg.get("stm_ttl_seconds", STM_TTL_SECONDS))
        self.ltm_ttl_seconds = int(cfg.get("ltm_ttl_seconds", LTM_TTL_SECONDS))
        self.recency_half_life_days = float(
            cfg.get("recency_half_life_days", RECENCY_HALF_LIFE_DAYS)
        )
        self._init_db()

    # -- connection management ------------------------------------------------

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS short_term (
                    id INTEGER PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_stm_user_time
                    ON short_term(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS long_term (
                    id INTEGER PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source_tier TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    access_count INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_ltm_user_time
                    ON long_term(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source_turn_id TEXT NOT NULL,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    superseded_at REAL,
                    superseded_by INTEGER,
                    UNIQUE(user_id, entity_type, entity_key, last_seen)
                );
                CREATE INDEX IF NOT EXISTS idx_entities_user
                    ON entities(user_id, entity_type, entity_key);
                CREATE INDEX IF NOT EXISTS idx_entities_active
                    ON entities(user_id, superseded_at);

                CREATE TABLE IF NOT EXISTS entity_history (
                    id INTEGER PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT NOT NULL,
                    old_confidence REAL,
                    new_confidence REAL NOT NULL,
                    changed_at REAL NOT NULL,
                    source_turn_id TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_audit (
                    id INTEGER PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    op TEXT NOT NULL,
                    tier TEXT,
                    target_id INTEGER,
                    details TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_user_time
                    ON memory_audit(user_id, created_at DESC);

                -- FTS5 virtual tables (contentless mirror pattern)
                CREATE VIRTUAL TABLE IF NOT EXISTS stm_fts USING fts5(
                    text, content='short_term', content_rowid='id'
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS ltm_fts USING fts5(
                    text, content='long_term', content_rowid='id'
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS entity_fts USING fts5(
                    value, content='entities', content_rowid='id'
                );
            """)

    # -- audit ----------------------------------------------------------------

    def _audit(self, conn, user_id: str, op: str, tier: Optional[str],
               target_id: Optional[int], details: Optional[Dict[str, Any]] = None):
        conn.execute(
            "INSERT INTO memory_audit (user_id, op, tier, target_id, details, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, op, tier, target_id,
             json.dumps(details) if details else None, time.time())
        )

    # -- Short-term -----------------------------------------------------------

    def add_turn(self, user_id: str, role: str, text: str,
                  turn_id: Optional[str] = None,
                  ttl_seconds: Optional[int] = None) -> str:
        """Append a conversation turn to short-term memory. Evicts oldest beyond STM_MAX_TURNS."""
        if not user_id:
            raise ValueError("user_id is required for memory isolation")
        if ttl_seconds is None:
            ttl_seconds = self.stm_ttl_seconds
        turn_id = turn_id or str(uuid.uuid4())
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO short_term (user_id, turn_id, role, text, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, turn_id, role, text, now, now + ttl_seconds)
            )
            conn.execute(
                "INSERT INTO stm_fts (rowid, text) VALUES (last_insert_rowid(), ?)",
                (text,)
            )
            # Enforce window
            conn.execute("""
                DELETE FROM short_term
                WHERE id IN (
                    SELECT id FROM short_term
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET ?
                )
            """, (user_id, self.stm_max_turns))
            self._audit(conn, user_id, "stm_add", "stm", None,
                        {"turn_id": turn_id, "role": role, "len": len(text)})
        return turn_id

    def get_recent_turns(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM short_term WHERE user_id = ? AND expires_at > ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, time.time(), limit)
            ).fetchall()
            self._audit(conn, user_id, "stm_read", "stm", None, {"limit": limit})
            return [dict(r) for r in rows]

    # -- Long-term ------------------------------------------------------------

    def store_long_term(self, user_id: str, text: str,
                         source_tier: str = "consolidated",
                         turn_id: Optional[str] = None,
                         ttl_seconds: Optional[int] = None) -> int:
        if not user_id:
            raise ValueError("user_id is required for memory isolation")
        if ttl_seconds is None:
            ttl_seconds = self.ltm_ttl_seconds
        turn_id = turn_id or str(uuid.uuid4())
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO long_term (user_id, turn_id, text, source_tier, created_at, "
                "last_accessed, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, turn_id, text, source_tier, now, now, now + ttl_seconds)
            )
            row_id = cur.lastrowid
            conn.execute("INSERT INTO ltm_fts (rowid, text) VALUES (?, ?)", (row_id, text))
            self._audit(conn, user_id, "ltm_add", "ltm", row_id,
                        {"source": source_tier, "len": len(text)})
            return row_id

    def touch_long_term(self, conn, ltm_id: int):
        if not LTM_ACCESS_REFRESH:
            return
        conn.execute(
            "UPDATE long_term SET last_accessed = ?, access_count = access_count + 1 "
            "WHERE id = ?",
            (time.time(), ltm_id)
        )

    # -- Entity memory (typed facts with conflict handling) ------------------

    def upsert_entity(self, user_id: str, entity_type: str, entity_key: str,
                      value: str, confidence: float = ENTITY_DEFAULT_CONFIDENCE,
                      turn_id: Optional[str] = None) -> Tuple[int, bool]:
        """Insert or update an entity. Returns (id, conflict_detected).

        If the new confidence beats the existing by ENTITY_CONFLICT_THRESHOLD,
        the prior fact is moved to entity_history and marked superseded.
        """
        if not user_id:
            raise ValueError("user_id is required for memory isolation")
        turn_id = turn_id or str(uuid.uuid4())
        now = time.time()
        conflict = False
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id, value, confidence FROM entities "
                "WHERE user_id = ? AND entity_type = ? AND entity_key = ? "
                "AND superseded_at IS NULL ORDER BY last_seen DESC LIMIT 1",
                (user_id, entity_type, entity_key)
            ).fetchone()
            if existing and existing["value"] == value:
                # Same fact, just reinforce
                conn.execute(
                    "UPDATE entities SET last_seen = ?, confidence = MAX(confidence, ?) "
                    "WHERE id = ?",
                    (now, confidence, existing["id"])
                )
                new_id = existing["id"]
            else:
                new_id = None
                # A different value is a conflict by definition. Replace iff the
                # new evidence is at least as strong as the old.
                should_replace = True
                if existing and confidence < existing["confidence"] - ENTITY_CONFLICT_THRESHOLD:
                    should_replace = False
                if existing and should_replace:
                    conflict = True
                    conn.execute(
                        "UPDATE entities SET superseded_at = ?, superseded_by = NULL "
                        "WHERE id = ?",
                        (now, existing["id"])
                    )
                    conn.execute(
                        "INSERT INTO entity_history (user_id, entity_type, entity_key, "
                        "old_value, new_value, old_confidence, new_confidence, "
                        "changed_at, source_turn_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (user_id, entity_type, entity_key, existing["value"],
                         value, existing["confidence"], confidence, now, turn_id)
                    )
                if should_replace:
                    cur = conn.execute(
                        "INSERT INTO entities (user_id, entity_type, entity_key, value, "
                        "confidence, source_turn_id, first_seen, last_seen) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (user_id, entity_type, entity_key, value, confidence,
                         turn_id, now, now)
                    )
                    new_id = cur.lastrowid
                    conn.execute("INSERT INTO entity_fts (rowid, value) VALUES (?, ?)",
                                 (new_id, value))
            self._audit(conn, user_id, "entity_upsert", "entity", new_id,
                        {"type": entity_type, "key": entity_key,
                         "conflict": conflict, "conf": confidence})
        return new_id, conflict

    def get_entity(self, user_id: str, entity_type: str, entity_key: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM entities WHERE user_id = ? AND entity_type = ? "
                "AND entity_key = ? AND superseded_at IS NULL ORDER BY last_seen DESC LIMIT 1",
                (user_id, entity_type, entity_key)
            ).fetchone()
            if row:
                self._audit(conn, user_id, "entity_read", "entity", row["id"], None)
            return dict(row) if row else None

    # -- Retrieval (the actual intelligence) ---------------------------------

    def retrieve(self, user_id: str, query: str, limit: int = 8,
                 tiers: Iterable[str] = ("stm", "ltm", "entity")) -> List[MemoryHit]:
        """Score-relevant retrieval across tiers, isolated to user_id."""
        if not user_id:
            raise ValueError("user_id is required for memory isolation")
        if not query.strip():
            return []
        hits: List[MemoryHit] = []
        now = time.time()
        # FTS5 prefix-match each token so "pineapple pizza" matches "pineapple on pizza".
        # Strip FTS5 operators/punctuation to avoid syntax errors and Python ?-marker collisions.
        import re
        raw = re.findall(r"[A-Za-z0-9_]+", query)
        tokens = [t for t in raw if t.lower() not in _FTS5_STOPWORDS and len(t) > 1]
        if not tokens:
            return []
        fts_query = " ".join(f"{t}*" for t in tokens)
        with self._conn() as conn:
            self._audit(conn, user_id, "retrieve", None, None, {"q": query, "limit": limit})

            if "stm" in tiers:
                rows = conn.execute("""
                    SELECT s.id, s.text, s.created_at,
                           bm25(stm_fts) AS rank
                    FROM stm_fts
                    JOIN short_term s ON s.id = stm_fts.rowid
                    WHERE stm_fts MATCH ? AND s.user_id = ? AND s.expires_at > ?
                    ORDER BY rank LIMIT ?
                """, (fts_query, user_id, now, limit)).fetchall()
                for r in rows:
                    age_days = (now - r["created_at"]) / 86400.0
                    score = _score(-r["rank"], TIER_WEIGHT_STM, age_days, self.recency_half_life_days)
                    hits.append(MemoryHit(
                        tier="stm", score=score, text=r["text"],
                        metadata={"id": r["id"]}, age_days=age_days
                    ))

            if "ltm" in tiers:
                rows = conn.execute("""
                    SELECT l.id, l.text, l.created_at,
                           bm25(ltm_fts) AS rank
                    FROM ltm_fts
                    JOIN long_term l ON l.id = ltm_fts.rowid
                    WHERE ltm_fts MATCH ? AND l.user_id = ? AND l.expires_at > ?
                    ORDER BY rank LIMIT ?
                """, (fts_query, user_id, now, limit)).fetchall()
                for r in rows:
                    age_days = (now - r["created_at"]) / 86400.0
                    score = _score(-r["rank"], TIER_WEIGHT_LTM, age_days, self.recency_half_life_days)
                    hits.append(MemoryHit(
                        tier="ltm", score=score, text=r["text"],
                        metadata={"id": r["id"]}, age_days=age_days
                    ))
                    self.touch_long_term(conn, r["id"])

            if "entity" in tiers:
                rows = conn.execute("""
                    SELECT e.id, e.entity_type, e.entity_key, e.value, e.confidence,
                           e.last_seen,
                           bm25(entity_fts) AS rank
                    FROM entity_fts
                    JOIN entities e ON e.id = entity_fts.rowid
                    WHERE entity_fts MATCH ? AND e.user_id = ? AND e.superseded_at IS NULL
                    ORDER BY rank LIMIT ?
                """, (fts_query, user_id, limit)).fetchall()
                for r in rows:
                    age_days = (now - r["last_seen"]) / 86400.0
                    base = _score(-r["rank"], TIER_WEIGHT_ENTITY, age_days, self.recency_half_life_days)
                    score = base * r["confidence"]
                    hits.append(MemoryHit(
                        tier="entity", score=score, text=r["value"],
                        entity_type=r["entity_type"],
                        entity_key=r["entity_key"],
                        confidence=r["confidence"],
                        metadata={"id": r["id"]},
                        age_days=age_days
                    ))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    # -- Memory-aware prompt construction ------------------------------------

    def build_context(self, user_id: str, query: str,
                      token_budget: int = 2000,
                      chars_per_token: float = 4.0) -> str:
        """Return a memory block ready to inject into the system prompt.

        Falls back to recent turns when no scored hits exist.
        """
        char_budget = int(token_budget * chars_per_token)
        hits = self.retrieve(user_id, query, limit=12)
        if not hits:
            hits = [MemoryHit(
                tier="stm", score=0.0, text=f"{t['role']}: {t['text']}",
                metadata={"id": t["id"]},
                age_days=(time.time() - t["created_at"]) / 86400.0
            ) for t in self.get_recent_turns(user_id, limit=5)]
            if not hits:
                return ""
        lines = ["<memory>"]
        used = len(lines[0]) + 1
        for h in hits:
            snippet = h.to_prompt_snippet()
            if used + len(snippet) + 1 > char_budget:
                break
            lines.append(snippet)
            used += len(snippet) + 1
        lines.append("</memory>")
        return "\n".join(lines)

    # -- Consolidation & decay ----------------------------------------------

    def consolidate(self, user_id: str, summarizer) -> int:
        """Move old STM into LTM via summarizer(texts) -> str. Returns count consolidated.

        summarizer: callable(list[str]) -> str
        """
        with self._conn() as conn:
            cutoff = time.time() - (self.stm_ttl_seconds / 2)
            rows = conn.execute(
                "SELECT id, text, role FROM short_term "
                "WHERE user_id = ? AND created_at < ? ORDER BY created_at",
                (user_id, cutoff)
            ).fetchall()
            if not rows:
                return 0
            texts = [f"{r['role']}: {r['text']}" for r in rows]
            summary = summarizer(texts) or ""
            if summary.strip():
                self.store_long_term(user_id, summary, source_tier="stm_summary")
            for r in rows:
                conn.execute("DELETE FROM short_term WHERE id = ?", (r["id"],))
                conn.execute("DELETE FROM stm_fts WHERE rowid = ?", (r["id"],))
            self._audit(conn, user_id, "consolidate", "stm->ltm", None,
                        {"moved": len(rows), "summary_len": len(summary)})
            return len(rows)

    def prune_expired(self) -> Tuple[int, int]:
        """Remove expired STM/LTM. Returns (stm_pruned, ltm_pruned)."""
        now = time.time()
        with self._conn() as conn:
            stm_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM short_term WHERE expires_at <= ?", (now,)).fetchall()]
            for sid in stm_ids:
                conn.execute("DELETE FROM stm_fts WHERE rowid = ?", (sid,))
            conn.execute("DELETE FROM short_term WHERE expires_at <= ?", (now,))

            ltm_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM long_term WHERE expires_at <= ?", (now,)).fetchall()]
            for lid in ltm_ids:
                conn.execute("DELETE FROM ltm_fts WHERE rowid = ?", (lid,))
            conn.execute("DELETE FROM long_term WHERE expires_at <= ?", (now,))
        return len(stm_ids), len(ltm_ids)

    # -- Stats / introspection ----------------------------------------------

    def stats(self, user_id: Optional[str] = None) -> Dict[str, int]:
        where = "WHERE user_id = ?" if user_id else ""
        params: Tuple[Any, ...] = (user_id,) if user_id else ()
        with self._conn() as conn:
            return {
                "stm": conn.execute(f"SELECT COUNT(*) c FROM short_term {where}", params).fetchone()["c"],
                "ltm": conn.execute(f"SELECT COUNT(*) c FROM long_term {where}", params).fetchone()["c"],
                "entities_active": conn.execute(
                    f"SELECT COUNT(*) c FROM entities {where} "
                    + ("AND superseded_at IS NULL" if user_id else "WHERE superseded_at IS NULL"),
                    params if user_id else ()
                ).fetchone()["c"],
                "entities_history": conn.execute(
                    f"SELECT COUNT(*) c FROM entity_history {where}", params
                ).fetchone()["c"],
                "audit_events": conn.execute(
                    f"SELECT COUNT(*) c FROM memory_audit {where}", params
                ).fetchone()["c"],
            }


# ---- Scoring helpers --------------------------------------------------------

def _score(bm25_contrib: float, tier_weight: float, age_days: float,
           recency_half_life_days: float = RECENCY_HALF_LIFE_DAYS) -> float:
    """Combined retrieval score: BM25 contribution * tier weight * recency decay."""
    recency = math.exp(-age_days / recency_half_life_days * math.log(2))
    return max(0.0, bm25_contrib) * tier_weight * recency
