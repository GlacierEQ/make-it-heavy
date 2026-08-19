import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from corpus_miner import MAX_SEARCH_RESULTS, classify, ingest, search, summarize


class CorpusMinerTests(unittest.TestCase):
    def _write_fixture(self, root: Path, conversations: list[dict]) -> Path:
        archive = root / "export.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "conversations-test.json",
                json.dumps({"conversations": conversations}),
            )
        return archive

    def _conversation(self, entries: list[dict]) -> dict:
        return {
            "context_uuid": "ctx-1",
            "context_title": "Helix GitHub architecture",
            "created_at": "2026-08-12T00:00:00Z",
            "updated_at": "2026-08-12T00:01:00Z",
            "mode": "COPILOT",
            "collection_uuid": None,
            "entries": entries,
        }

    def test_ingest_classify_summary_and_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._write_fixture(
                root,
                [
                    self._conversation(
                        [
                            {
                                "entry_uuid": "e-1",
                                "query": "Connect Helix to GitHub",
                                "answer": "Use the repository lineage.",
                            },
                            {
                                "entry_uuid": "e-2",
                                "query": "Supabase projection",
                                "answer": "Preserve provenance.",
                            },
                        ]
                    )
                ],
            )
            db = root / "corpus.db"
            counts = ingest(archive, db)
            self.assertEqual(counts["conversations"], 1)
            self.assertEqual(counts["entries"], 2)
            tags = classify(db)
            self.assertEqual(tags["helix"], 1)
            self.assertEqual(tags["github"], 1)
            self.assertEqual(tags["supabase"], 1)
            summary = summarize(db)
            self.assertEqual(summary["entries"], 2)
            hits = search(db, "Supabase", limit=5)
            self.assertEqual([hit["entry_uuid"] for hit in hits], ["e-2"])

    def test_reingest_reconciles_removed_entries_and_contexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "corpus.db"
            archive = self._write_fixture(
                root,
                [
                    self._conversation(
                        [
                            {"entry_uuid": "e-1", "query": "Helix", "answer": "one"},
                            {
                                "entry_uuid": "e-2",
                                "query": "obsolete",
                                "answer": "remove me",
                            },
                        ]
                    )
                ],
            )
            ingest(archive, db)
            self._write_fixture(
                root,
                [
                    self._conversation(
                        [
                            {
                                "entry_uuid": "e-1",
                                "query": "Helix updated",
                                "answer": "one",
                            },
                        ]
                    )
                ],
            )
            counts = ingest(archive, db)
            self.assertEqual(counts["removed_stale_entries"], 1)
            self.assertEqual(summarize(db)["entries"], 1)
            self.assertEqual(search(db, "obsolete"), [])

            self._write_fixture(root, [])
            ingest(archive, db)
            self.assertEqual(summarize(db)["conversations"], 0)
            self.assertEqual(summarize(db)["entries"], 0)

    def test_empty_vector_map_stays_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._write_fixture(
                root,
                [
                    self._conversation(
                        [
                            {
                                "entry_uuid": "e-1",
                                "query": "GitHub",
                                "answer": "repo",
                            },
                        ]
                    )
                ],
            )
            db = root / "corpus.db"
            ingest(archive, db)
            self.assertEqual(classify(db, {}), {})
            with sqlite3.connect(db) as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM corpus_tags").fetchone()[0],
                    0,
                )

    def test_search_limit_is_capped_and_empty_query_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = [
                {"entry_uuid": f"e-{i}", "query": "Helix", "answer": f"row {i}"}
                for i in range(MAX_SEARCH_RESULTS + 25)
            ]
            archive = self._write_fixture(root, [self._conversation(entries)])
            db = root / "corpus.db"
            ingest(archive, db)
            self.assertEqual(
                len(search(db, "Helix", limit=10000)),
                MAX_SEARCH_RESULTS,
            )
            with self.assertRaisesRegex(ValueError, "must not be empty"):
                search(db, "   ")

    def test_identifier_collisions_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "corpus.db"
            first = root / "first.json"
            first.write_text(
                json.dumps(
                    {
                        "conversations": [
                            self._conversation(
                                [
                                    {
                                        "entry_uuid": "e-1",
                                        "query": "Helix",
                                        "answer": "one",
                                    }
                                ]
                            )
                        ]
                    }
                ),
                encoding="utf-8",
            )
            ingest(first, db)
            second = root / "second.json"
            second.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "collision across sources"):
                ingest(second, db)


if __name__ == "__main__":
    unittest.main()
