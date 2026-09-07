# SPDX-License-Identifier: Proprietary
"""Tests for the TieredMemory <-> mermicorn_token_saver bridge.

These tests use a tmp token-saver cache so the live /root/.token_saver
store is never touched. The TieredMemory uses its own tmp db.

If ``mermicorn_token_saver`` is not on the import path, only the
dependency-error test runs and the rest skip — this matches the
"gracefully handle optional token_saver dependency" pattern from
commit ``c51dcee``.
"""
import os
import sys
import tempfile
import unittest

TOKEN_SAVER_SRC = "/root/projects/mermicorn/token-saver/src"
if os.path.isdir(TOKEN_SAVER_SRC) and TOKEN_SAVER_SRC not in sys.path:
    sys.path.insert(0, TOKEN_SAVER_SRC)

try:
    import mermicorn_token_saver  # noqa: F401
    _TOKEN_SAVER_AVAILABLE = True
except ImportError:
    _TOKEN_SAVER_AVAILABLE = False

from memory_tiered import TieredMemory  # noqa: E402
from token_saver_bridge import (  # noqa: E402
    BridgeDependencyError,
    compress_session,
)


def _seed(mem: TieredMemory, user_id: str, n: int) -> None:
    body = (
        "The tokenizer estimates ~3.7 chars per token on prose and ~3.2 on code. "
        "Compaction strategies must never inflate a payload. The summarize strategy "
        "keeps lead, tail, and high-signal sentences. The semantic_dedup strategy "
        "collapses near-duplicate lines. The delta_encode strategy keeps turn 1 verbatim "
        "and later turns as diffs. The lossless strategy only does structural passes. "
    )
    for i in range(n):
        mem.add_turn(user_id, "user", f"turn-{i}: {body}", turn_id=f"t{i}")


@unittest.skipUnless(_TOKEN_SAVER_AVAILABLE, "mermicorn_token_saver not on import path")
class TestTokenSaverBridge(unittest.TestCase):
    def setUp(self):
        self.tm_fd, self.tm_path = tempfile.mkstemp(suffix=".db")
        self.ts_fd, self.ts_path = tempfile.mkstemp(suffix=".json")
        os.close(self.ts_fd)
        os.unlink(self.ts_path)
        os.environ["TOKEN_SAVER_CACHE"] = self.ts_path
        self.mem = TieredMemory(self.tm_path)

    def tearDown(self):
        os.close(self.tm_fd)
        os.unlink(self.tm_path)
        if os.path.exists(self.ts_path):
            os.unlink(self.ts_path)
        os.environ.pop("TOKEN_SAVER_CACHE", None)

    # -- core behaviour ----------------------------------------------------

    def test_compress_session_writes_a_compacted_ltm_record(self):
        _seed(self.mem, "alice", 5)
        receipt = compress_session(self.mem, "alice", "s1", stm_limit=10)
        self.assertIsNotNone(receipt)
        self.assertGreater(receipt["savings"], 0)
        self.assertIn("text", receipt)

        with self.mem._conn() as conn:
            rows = conn.execute(
                "SELECT text, source_tier FROM long_term WHERE user_id = ?",
                ("alice",),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_tier"], "token_saver_bridge")
        # The LTM record is the receipt text; the receipt itself proves it
        # was shorter than the input.
        ltm_text = rows[0]["text"]
        self.assertEqual(ltm_text, receipt["text"])
        self.assertLess(
            len(ltm_text), 5 * 600,
            f"compacted LTM (len={len(ltm_text)}) should be materially smaller "
            "than the 5 raw STM turns",
        )

    def test_compress_session_returns_none_below_min_turns(self):
        self.mem.add_turn("alice", "user", "single", turn_id="only")
        self.assertIsNone(compress_session(self.mem, "alice", "s1"))

    def test_compress_session_returns_none_for_empty_user(self):
        self.assertIsNone(compress_session(self.mem, "nobody", "s1"))

    def test_bridge_enforces_user_isolation(self):
        _seed(self.mem, "alice", 4)
        _seed(self.mem, "bob", 4)
        receipt_alice = compress_session(self.mem, "alice", "s1", stm_limit=10)
        receipt_bob = compress_session(self.mem, "bob", "s1", stm_limit=10)
        self.assertIsNotNone(receipt_alice)
        self.assertIsNotNone(receipt_bob)
        # Each user's LTM holds only their own record.
        with self.mem._conn() as conn:
            n_alice = conn.execute(
                "SELECT COUNT(*) c FROM long_term WHERE user_id = ?", ("alice",)
            ).fetchone()["c"]
            n_bob = conn.execute(
                "SELECT COUNT(*) c FROM long_term WHERE user_id = ?", ("bob",)
            ).fetchone()["c"]
        self.assertEqual(n_alice, 1)
        self.assertEqual(n_bob, 1)

    # -- guards -------------------------------------------------------------

    def test_empty_user_id_is_hard_error(self):
        with self.assertRaises(ValueError):
            compress_session(self.mem, "")

    def test_whitespace_user_id_is_hard_error(self):
        with self.assertRaises(ValueError):
            compress_session(self.mem, "   ")

    def test_dependency_error_raised_when_token_saver_missing(self):
        import sys
        import token_saver_bridge as bridge_mod

        original = bridge_mod._load_token_saver
        def boom():
            raise BridgeDependencyError("not installed")
        bridge_mod._load_token_saver = boom
        try:
            _seed(self.mem, "alice", 2)
            with self.assertRaises(BridgeDependencyError):
                bridge_mod.compress_session(self.mem, "alice", "s1")
        finally:
            bridge_mod._load_token_saver = original


if __name__ == "__main__":
    unittest.main()
