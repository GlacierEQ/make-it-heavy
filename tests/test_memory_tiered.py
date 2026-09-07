# SPDX-License-Identifier: Proprietary
"""Unit tests for TieredMemory — user isolation, tier separation, retrieval scoring,
conflict detection, consolidation, decay, and memory-aware prompt building."""

import os
import tempfile
import time
import unittest

from memory_tiered import TieredMemory, MemoryHit, TIER_WEIGHT_ENTITY


class TestTieredMemory(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.mem = TieredMemory(self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # -- user isolation (critical) ------------------------------------------

    def test_user_isolation(self):
        self.mem.add_turn("alice", "user", "I love Python programming")
        self.mem.add_turn("bob", "user", "I prefer Rust systems")
        alice_hits = self.mem.retrieve("alice", "Python")
        bob_hits = self.mem.retrieve("bob", "Python")
        self.assertTrue(any("Python" in h.text for h in alice_hits))
        for h in bob_hits:
            self.assertNotIn("Python", h.text)

    def test_empty_user_id_rejected(self):
        with self.assertRaises(ValueError):
            self.mem.add_turn("", "user", "hi")
        with self.assertRaises(ValueError):
            self.mem.retrieve("", "anything")
        with self.assertRaises(ValueError):
            self.mem.upsert_entity("", "person", "name", "x")

    # -- short-term ---------------------------------------------------------

    def test_stm_window_eviction(self):
        from memory_tiered import STM_MAX_TURNS
        for i in range(STM_MAX_TURNS + 5):
            self.mem.add_turn("alice", "user", f"message {i}")
        recent = self.mem.get_recent_turns("alice", limit=100)
        self.assertEqual(len(recent), STM_MAX_TURNS)
        self.assertIn(f"message {STM_MAX_TURNS + 4}", recent[0]["text"])

    def test_stm_retrieval_finds_recent_turn(self):
        self.mem.add_turn("alice", "user", "Tell me about quantum entanglement")
        hits = self.mem.retrieve("alice", "quantum")
        self.assertTrue(any("quantum" in h.text for h in hits))
        self.assertTrue(any(h.tier == "stm" for h in hits))

    # -- long-term ----------------------------------------------------------

    def test_ltm_storage_and_retrieval(self):
        self.mem.store_long_term("alice", "Casey prefers dark roast coffee",
                                  turn_id="t1")
        hits = self.mem.retrieve("alice", "coffee")
        self.assertTrue(any(h.tier == "ltm" and "coffee" in h.text for h in hits))

    def test_ltm_recency_decay_ranks_newer_higher(self):
        self.mem.store_long_term("alice", "old: pineapple on pizza",
                                  turn_id="old")
        time.sleep(0.05)
        self.mem.store_long_term("alice", "new: pineapple on pizza",
                                  turn_id="new")
        hits = self.mem.retrieve("alice", "pineapple pizza")
        ltm_hits = [h for h in hits if h.tier == "ltm"]
        self.assertGreaterEqual(len(ltm_hits), 2)
        self.assertTrue(ltm_hits[0].text.startswith("new:"))

    # -- entity memory & conflict detection --------------------------------

    def test_entity_upsert_creates_then_reinforces(self):
        eid, conflict = self.mem.upsert_entity(
            "alice", "person", "name", "Casey", confidence=0.9)
        self.assertIsInstance(eid, int)
        self.assertFalse(conflict)
        eid2, conflict2 = self.mem.upsert_entity(
            "alice", "person", "name", "Casey", confidence=0.95)
        self.assertEqual(eid, eid2)
        self.assertFalse(conflict2)
        ent = self.mem.get_entity("alice", "person", "name")
        self.assertEqual(ent["value"], "Casey")
        self.assertAlmostEqual(ent["confidence"], 0.95, places=2)

    def test_entity_conflict_supersedes(self):
        self.mem.upsert_entity("alice", "person", "city", "Honolulu", confidence=0.9)
        eid, conflict = self.mem.upsert_entity(
            "alice", "person", "city", "Seattle", confidence=0.95)
        self.assertTrue(conflict)
        ent = self.mem.get_entity("alice", "person", "city")
        self.assertEqual(ent["value"], "Seattle")
        s = self.mem.stats("alice")
        self.assertEqual(s["entities_active"], 1)
        self.assertEqual(s["entities_history"], 1)

    def test_entity_conflict_below_threshold_keeps_existing(self):
        self.mem.upsert_entity("alice", "person", "city", "Honolulu", confidence=0.9)
        eid, conflict = self.mem.upsert_entity(
            "alice", "person", "city", "Tokyo", confidence=0.5)
        self.assertFalse(conflict)
        ent = self.mem.get_entity("alice", "person", "city")
        self.assertEqual(ent["value"], "Honolulu")

    def test_entity_retrieval_uses_confidence(self):
        self.mem.upsert_entity("alice", "preference", "language", "Python", confidence=0.9)
        self.mem.upsert_entity("alice", "preference", "language", "Ruby", confidence=0.3)
        # First insert wins because second is below threshold — so Python should remain
        ent = self.mem.get_entity("alice", "preference", "language")
        self.assertEqual(ent["value"], "Python")

    # -- retrieval scoring & ranking ---------------------------------------

    def test_entity_outranks_stm_for_direct_fact(self):
        self.mem.add_turn("alice", "user", "I went hiking yesterday")
        self.mem.upsert_entity("alice", "activity", "favorite", "hiking", confidence=0.95)
        hits = self.mem.retrieve("alice", "hiking")
        tiers = [h.tier for h in hits]
        self.assertIn("entity", tiers)
        entity_hits = [h for h in hits if h.tier == "entity"]
        self.assertGreater(entity_hits[0].score, 0)

    def test_retrieval_limit_respected(self):
        for i in range(20):
            self.mem.add_turn("alice", "user", f"keyword alpha {i}")
        hits = self.mem.retrieve("alice", "alpha", limit=5)
        self.assertLessEqual(len(hits), 5)

    def test_empty_query_returns_empty(self):
        self.mem.add_turn("alice", "user", "hello world")
        self.assertEqual(self.mem.retrieve("alice", ""), [])
        self.assertEqual(self.mem.retrieve("alice", "   "), [])

    # -- memory-aware prompting --------------------------------------------

    def test_build_context_includes_relevant_memories(self):
        self.mem.upsert_entity("alice", "person", "name", "Casey", confidence=0.95)
        self.mem.store_long_term("alice", "Casey lives in Seattle and loves coffee")
        ctx = self.mem.build_context("alice", "Where does Casey live?", token_budget=500)
        self.assertIn("<memory>", ctx)
        self.assertIn("</memory>", ctx)
        self.assertTrue("Seattle" in ctx or "Casey" in ctx)

    def test_build_context_empty_when_no_memories(self):
        ctx = self.mem.build_context("nobody", "anything", token_budget=500)
        self.assertEqual(ctx, "")

    def test_build_context_respects_budget(self):
        for i in range(50):
            self.mem.add_turn("alice", "user", f"alpha message {i} " * 20)
        ctx = self.mem.build_context("alice", "alpha", token_budget=50)
        self.assertLessEqual(len(ctx), 50 * 4 + 20)

    # -- consolidation & decay --------------------------------------------

    def test_consolidate_moves_stm_to_ltm(self):
        from memory_tiered import STM_TTL_SECONDS
        old = time.time() - (STM_TTL_SECONDS / 2 + 10)
        # Backdate two turns
        self.mem.add_turn("alice", "user", "first old message")
        self.mem.add_turn("alice", "user", "second old message")
        with self.mem._conn() as conn:
            conn.execute("UPDATE short_term SET created_at = ?", (old,))
        moved = self.mem.consolidate("alice", summarizer=lambda xs: "summary: " + " | ".join(xs))
        self.assertEqual(moved, 2)
        hits = self.mem.retrieve("alice", "summary")
        self.assertTrue(any(h.tier == "ltm" and "summary" in h.text for h in hits))

    def test_prune_expired(self):
        self.mem.add_turn("alice", "user", "ephemeral")
        with self.mem._conn() as conn:
            conn.execute("UPDATE short_term SET expires_at = 0")
        stm, ltm = self.mem.prune_expired()
        self.assertEqual(stm, 1)
        self.assertEqual(ltm, 0)

    # -- audit lineage ------------------------------------------------------

    def test_audit_log_populated(self):
        self.mem.add_turn("alice", "user", "audit me")
        self.mem.upsert_entity("alice", "person", "x", "y")
        self.mem.retrieve("alice", "audit")
        s = self.mem.stats("alice")
        self.assertGreater(s["audit_events"], 0)


if __name__ == "__main__":
    unittest.main()
