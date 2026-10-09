import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from omnifind.core import Index, ScopeError


class StorageEmbedder:
    """Deterministic fixture for lifecycle tests only; not evidence of local AI."""
    identity = "test-fixture-v1"

    def chunks(self, text):
        for start in range(0, len(text), 80):
            yield text[start:start + 80], start, min(start + 80, len(text))

    def encode(self, texts):
        return (np.ones((len(texts), 3)) / np.sqrt(3)).astype("<f4")


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.root = self.directory / "corpus"
        self.root.mkdir()
        self.database = self.directory / "data" / "index.sqlite"
        self.model = StorageEmbedder()
        self.index = Index(self.database, self.model)
        self.root_id = self.index.add_root(self.root)

    def tearDown(self):
        self.index.close()
        self.temporary.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_restart_refresh_delete_and_revocation(self):
        source = self.write("random.txt", "Security deposit returned in thirty days.")
        self.index.refresh(self.root_id)
        self.assertEqual(self.index.search("deposit", "lexical")[0]["text"], source.read_text())
        self.index.close()
        self.index = Index(self.database, self.model)
        self.assertEqual(len(self.index.search("deposit", "lexical")), 1)
        source.write_text("Updated receipt INV-2048", encoding="utf-8")
        self.assertEqual(self.index.coverage()["stale"], 1)
        self.assertEqual(self.index.search("deposit", "lexical"), [])
        with self.assertRaises(ScopeError):
            self.index.source_path(1)
        self.index.refresh(self.root_id)
        self.assertEqual(self.index.search("deposit", "lexical"), [])
        self.assertEqual(len(self.index.search('"INV-2048"', "lexical")), 1)
        self.index.remove_root(self.root_id)
        self.assertTrue(source.exists())
        self.assertEqual(self.index.search("receipt", "lexical"), [])
        self.assertEqual(self.index.db.execute("SELECT count(*) FROM chunks").fetchone()[0], 0)
        self.assertEqual(self.index.db.execute("SELECT count(*) FROM chunk_fts").fetchone()[0], 0)
        self.index.close()
        self.index = Index(self.database, self.model)
        self.assertEqual(self.index.search("receipt", "lexical"), [])

    def test_failures_and_deleted_files_do_not_stop_refresh(self):
        good = self.write("good.txt", "deposit conditions")
        self.write("unsupported.csv", "not supported")
        self.write("broken.pdf", "invalid PDF")
        counts = self.index.refresh(self.root_id)
        self.assertEqual(counts, {"searchable": 1, "failed": 1, "unsupported": 1, "pending": 0, "discovered": 3})
        good.unlink()
        self.index.refresh(self.root_id)
        self.assertEqual(self.index.search("deposit", "lexical"), [])

    def test_filters_grouping_and_fts_syntax(self):
        for number in range(55):
            self.write(f"distractor_{number}.txt", "charger " * 30)
        target = self.write("target.md", "charger " * 120)
        self.index.refresh(self.root_id)
        result = self.index.search("charger", "semantic", suffix="md")
        self.assertEqual([Path(r["path"]).name for r in result], [target.name])
        result = self.index.search("charger", "lexical", suffix="md")
        self.assertEqual(len(result), 1)
        self.assertIsInstance(self.index.search('" OR * NEAR(a) --', "lexical"), list)
        self.assertEqual(self.index.search("", "hybrid"), [])

    def test_root_boundary_overlap_and_model_identity(self):
        nested = self.root / "nested"
        nested.mkdir()
        with self.assertRaises(ScopeError):
            self.index.add_root(nested)
        outside = self.directory / "outside.txt"
        outside.write_text("private")
        with self.assertRaises(ScopeError):
            self.index.authorize(self.root_id, outside)
        self.write("file.txt", "deposit")
        self.index.refresh(self.root_id)
        self.model.identity = "incompatible"
        with self.assertRaisesRegex(ValueError, "model-mismatch"):
            self.index.search("deposit", "semantic")

    def test_failed_revision_keeps_committed_chunks_inert(self):
        source = self.write("file.txt", "original deposit conditions")
        self.index.refresh(self.root_id)
        old_chunks = self.index.db.execute("SELECT text FROM chunks").fetchall()
        source.write_text("replacement receipt", encoding="utf-8")
        with patch.object(self.model, "encode", side_effect=RuntimeError("failure")):
            self.index.refresh(self.root_id)
        self.assertEqual(self.index.search("deposit", "lexical"), [])
        self.assertEqual([r[0] for r in self.index.db.execute("SELECT text FROM chunks")], [r[0] for r in old_chunks])
        self.index.refresh(self.root_id)
        self.assertEqual(len(self.index.search("receipt", "lexical")), 1)

    def test_transaction_fault_does_not_publish_partial_revision(self):
        source = self.write("file.txt", "original deposit conditions")
        self.index.refresh(self.root_id)
        source.write_text("replacement receipt", encoding="utf-8")
        self.index.db.execute("""CREATE TRIGGER fail_new_chunk BEFORE INSERT ON chunks BEGIN
            SELECT RAISE(ABORT, 'injected transaction failure'); END""")
        self.index.db.commit()
        self.index.refresh(self.root_id)
        self.assertEqual(self.index.db.execute("SELECT text FROM chunks").fetchone()[0], "original deposit conditions")
        self.assertEqual(self.index.db.execute("SELECT content FROM chunk_fts").fetchone()[0], "original deposit conditions")
        self.assertEqual(self.index.search("deposit", "lexical"), [])
        self.index.db.execute("DROP TRIGGER fail_new_chunk")
        self.index.db.commit()
        self.index.refresh(self.root_id)
        self.assertEqual(len(self.index.search("receipt", "lexical")), 1)

    def test_revocation_during_embedding_prevents_commit(self):
        source = self.write("file.txt", "deposit conditions")
        second = Index(self.database)
        original = self.model.encode
        def revoke(texts):
            second.remove_root(self.root_id)
            return original(texts)
        try:
            with patch.object(self.model, "encode", side_effect=revoke):
                with self.assertRaises(ScopeError):
                    self.index.refresh(self.root_id)
            self.assertEqual(self.index.db.execute("SELECT count(*) FROM chunks").fetchone()[0], 0)
            self.assertTrue(source.exists())
        finally:
            second.close()

    def test_lexical_recovery_without_model(self):
        self.write("file.txt", "Unicode café deposit REF-22")
        self.index.refresh(self.root_id)
        self.index.close()
        self.index = Index(self.database)
        self.assertEqual(len(self.index.search("café REF-22", "lexical")), 1)
        with self.assertRaisesRegex(ValueError, "semantic-model-unavailable"):
            self.index.search("deposit", "hybrid")

    def test_revocation_during_query_prevents_results(self):
        self.write("file.txt", "deposit conditions")
        self.index.refresh(self.root_id)
        second = Index(self.database)
        original = self.model.encode
        def revoke(texts):
            second.remove_root(self.root_id)
            return original(texts)
        try:
            with patch.object(self.model, "encode", side_effect=revoke):
                self.assertEqual(self.index.search("deposit", "semantic"), [])
        finally:
            second.close()

    def test_exact_identifiers_and_quoted_phrases(self):
        self.write("one.txt", "Receipt INV-2048 security deposit")
        self.write("two.txt", "Receipt INV-2049 deposit security")
        self.index.refresh(self.root_id)
        self.assertEqual(len(self.index.search("INV-2048", "lexical")), 1)
        self.assertEqual(len(self.index.search('"security deposit"', "lexical")), 1)

    def test_link_escape_is_rejected(self):
        import os
        outside = self.directory / "outside.txt"
        outside.write_text("outside secret")
        link = self.root / "link.txt"
        try:
            os.symlink(outside, link)
        except OSError:
            self.skipTest("Host does not permit symbolic link creation")
        with self.assertRaises(ScopeError):
            self.index.authorize(self.root_id, link)
        counts = self.index.refresh(self.root_id)
        self.assertEqual(counts["searchable"], 0)

    def test_cancel_preserves_committed_index(self):
        import threading
        from omnifind.core import WorkCancelled
        self.write("file.txt", "deposit conditions")
        self.index.refresh(self.root_id)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(WorkCancelled):
            self.index.refresh(self.root_id, cancel=cancel)
        self.assertEqual(len(self.index.search("deposit", "lexical")), 1)

    def test_old_evidence_revision_cannot_open_updated_file(self):
        source = self.write("file.txt", "original deposit conditions")
        self.index.refresh(self.root_id)
        old = self.index.search("deposit", "lexical")[0]
        source.write_text("updated receipt", encoding="utf-8")
        self.index.refresh(self.root_id)
        with self.assertRaises(ScopeError):
            self.index.source_path(old["file_id"], old["revision"])

    def test_weak_match_recovery_and_missing_calibration(self):
        import json
        self.write("file.txt", "deposit conditions")
        self.index.refresh(self.root_id)
        policy = self.directory / "policy.json"
        policy.write_text(json.dumps({"models": {self.model.identity: {"minimum_similarity": 0.5}}}))
        with patch.object(self.model, "encode", return_value=-self.model.encode(["query"])):
            response = self.index.search_response("unknown", policy_path=policy)
            self.assertEqual(response["status"], "no-strong-match")
            self.assertEqual(response["results"], [])
            revealed = self.index.search_response("unknown", show_weak=True, policy_path=policy)
            self.assertEqual(len(revealed["results"]), 1)
            self.assertTrue(revealed["results"][0]["weak_match"])
        self.assertEqual(self.index.search_response("deposit", policy_path=self.directory / "missing")["status"], "uncalibrated-candidates")


if __name__ == "__main__":
    unittest.main()
