"""Exact-code recovery independent of meaning scores, with authorization/filter checks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omnifind.core import Index, is_identifier_query
from tests.test_core import StorageEmbedder


class IdentifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "corpus"
        self.root.mkdir()
        self.index = Index(self.base / "data/index.sqlite", StorageEmbedder())
        self.root_id = self.index.add_root(self.root)
        for name, text in {"correct.txt": "Fictional invoice QXZ-471. Repairs were completed.",
                           "prefix.txt": "Fictional invoice QXZ-4710.",
                           "punctuation.txt": "Fictional invoice QXZ.471.",
                           "extended.md": "Fictional identifier PRE-QXZ-471-ALT."}.items():
            (self.root / name).write_text(text)
        self.index.refresh(self.root_id)

    def tearDown(self):
        self.index.close()
        self.temp.cleanup()

    def test_exact_literal_is_not_rejected_by_semantic_gate(self):
        with patch.object(self.index.embedder, "encode", side_effect=AssertionError("No meaning scoring for a code")):
            response = self.index.search_response("qxz-471")
            self.assertEqual(response["status"], "exact-identifier-matches")
            self.assertEqual([Path(r["path"]).name for r in response["results"]], ["correct.txt"])
            self.assertEqual(response["results"][0]["match_basis"], "exact-identifier")
            self.assertIsNone(response["results"][0]["similarity"])

    def test_missing_model_and_absent_identifier_have_no_fuzzy_fallback(self):
        self.index.embedder = None
        self.assertEqual(len(self.index.search_response("QXZ-471")["results"]), 1)
        self.assertEqual(self.index.search_response("QXZ-999", show_weak=True)["results"], [])

    def test_type_root_staleness_and_revocation_still_apply(self):
        self.assertEqual(self.index.search_response("QXZ-471", suffix="md")["results"], [])
        other_root = self.base / "other"
        other_root.mkdir()
        other_id = self.index.add_root(other_root)
        self.assertEqual(self.index.search_response("QXZ-471", root_id=other_id)["results"], [])
        (self.root / "correct.txt").write_text("Changed invoice QXZ-471 content.")
        self.assertEqual(self.index.search_response("QXZ-471")["results"], [])
        self.index.refresh(self.root_id)
        self.assertEqual(len(self.index.search_response("QXZ-471")["results"]), 1)
        self.index.remove_root(self.root_id)
        self.assertEqual(self.index.search_response("QXZ-471")["results"], [])

    def test_prose_and_plain_numbers_keep_existing_semantic_contract(self):
        for query in ["471", "repairs completed", "find QXZ-471", "QXZ-471 OR anything", '"QXZ-471"']:
            self.assertFalse(is_identifier_query(query))
        for query in ["QXZ-471", "ab42", "ITEM_471", "QXZ.471"]:
            self.assertTrue(is_identifier_query(query))
        with patch.object(self.index.embedder, "encode", side_effect=RuntimeError("Meaning still required")):
            with self.assertRaisesRegex(RuntimeError, "Meaning still required"):
                self.index.search_response("find QXZ-471")


if __name__ == "__main__":
    unittest.main()
