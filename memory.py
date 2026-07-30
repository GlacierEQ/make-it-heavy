# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""Persistent SQLite-backed swarm memory for Make-It-Heavy.

Agents recall past missions, cache LLM responses, and log telemetry.
"""

import sqlite3
import json
import hashlib
import time
import logging
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class SwarmMemory:
    """SQLite-backed persistent memory for agent context, task history, and cached results."""

    def __init__(self, db_path: str = ".swarm_memory.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS missions (
                    id INTEGER PRIMARY KEY,
                    mission_hash TEXT UNIQUE,
                    query TEXT,
                    status TEXT,
                    result TEXT,
                    created_at REAL,
                    completed_at REAL
                );
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY,
                    mission_id INTEGER,
                    agent_role TEXT,
                    model TEXT,
                    response TEXT,
                    execution_time REAL,
                    created_at REAL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id)
                );
                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY,
                    mission_id INTEGER,
                    agent_role TEXT,
                    tool_name TEXT,
                    arguments TEXT,
                    result TEXT,
                    latency_ms REAL,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    expires_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_missions_hash ON missions(mission_hash);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_mission ON agent_runs(mission_id);
            """)

    def hash_query(self, query: str) -> str:
        return hashlib.sha256(query.encode()).hexdigest()[:32]

    def start_mission(self, query: str) -> int:
        h = self.hash_query(query)
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT OR REPLACE INTO missions (mission_hash, query, status, created_at) VALUES (?, ?, ?, ?)",
                (h, query, "running", time.time())
            )
            return cur.lastrowid

    def complete_mission(self, mission_id: int, result: str, status: str = "completed"):
        with self._conn() as conn:
            conn.execute(
                "UPDATE missions SET status = ?, result = ?, completed_at = ? WHERE id = ?",
                (status, result, time.time(), mission_id)
            )

    def log_agent_run(self, mission_id: int, role: str, model: str, response: str, execution_time: float):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agent_runs (mission_id, agent_role, model, response, execution_time, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (mission_id, role, model, response, execution_time, time.time())
            )

    def log_tool_call(self, mission_id: int, role: str, tool_name: str, arguments: dict, result: Any, latency_ms: float):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tool_calls (mission_id, agent_role, tool_name, arguments, result, latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mission_id, role, tool_name, json.dumps(arguments), json.dumps(result), latency_ms, time.time())
            )

    def get_similar_missions(self, query: str, limit: int = 3) -> List[Dict]:
        """Simple keyword overlap similarity. Replace with embeddings in production."""
        h = self.hash_query(query)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM missions WHERE mission_hash != ? AND status = 'completed' ORDER BY completed_at DESC LIMIT ?",
                (h, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_cache(self, key: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM cache WHERE key = ? AND expires_at > ?", (key, time.time())).fetchone()
            return row["value"] if row else None

    def set_cache(self, key: str, value: str, ttl_seconds: int = 3600):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, value, time.time() + ttl_seconds)
            )

    def get_stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            missions = conn.execute("SELECT COUNT(*) as c FROM missions").fetchone()["c"]
            agents = conn.execute("SELECT COUNT(*) as c FROM agent_runs").fetchone()["c"]
            tools = conn.execute("SELECT COUNT(*) as c FROM tool_calls").fetchone()["c"]
            avg_time = conn.execute("SELECT AVG(execution_time) as a FROM agent_runs").fetchone()["a"] or 0
            return {
                "total_missions": missions,
                "total_agent_runs": agents,
                "total_tool_calls": tools,
                "avg_agent_execution_time": round(avg_time, 2),
            }
