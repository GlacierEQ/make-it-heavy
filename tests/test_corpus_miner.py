import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from corpus_miner import classify, ingest, search, summarize


class CorpusMinerTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        payload = {
            "conversations": [
                {
                    "context_uuid": "ctx-1",
                    "context_title": "Stealth microwave architecture",
                    "created_at": "2026-08-12T00:00:00Z",
                    "updated_at": "2026-08-12T00:01:00Z",
                    "mode": "COPILOT",
                    "collection_uuid": None,
                    "entries": [
                        {
                            "entry_uuid": "e-1",
                            "query": "Connect stealth and microwave to GitHub",
                            "answer": "Use the repository as the provenance layer.",
                        },
                        {
                            "entry_uuid": "e-2",
                            "query": "Remember Kekoa case context",
                            "answer": "Preserve 1FDV-23-0001009 provenance.",
                        },
                    ],
                }
            ]
        }
        archive = root / "export.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("conversations-test.json", json.dumps(payload))
        return archive

    def test_ingest_classify_summary_and_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._fixture(root)
            db = root / "corpus.db"

            counts = ingest(archive, db)
            self.assertEqual(counts["conversations"], 1)
            self.assertEqual(counts["entries"], 2)

            tags = classify(db)
            self.assertEqual(tags["stealth"], 1)
            self.assertEqual(tags["microwave"], 1)
            self.assertEqual(tags["family_case"], 1)
            self.assertEqual(tags["kekoa"], 1)

            summary = summarize(db)
            self.assertEqual(summary["conversations"], 1)
            self.assertEqual(summary["entries"], 2)
            self.assertEqual(summary["duplicate_pair_excess"], 0)

            hits = search(db, "stealth", limit=5)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["entry_uuid"], "e-1")


if __name__ == "__main__":
    unittest.main()
