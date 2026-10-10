import tempfile
import unittest
from pathlib import Path

from omnifind.core import Index, ScopeError
from omnifind.issues import issue_copy
from tests.test_core import StorageEmbedder


class IssueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "corpus"
        self.root.mkdir()
        self.database = Path(self.temp.name) / "data/index.sqlite"
        self.index = Index(self.database, StorageEmbedder())
        self.root_id = self.index.add_root(self.root)

    def tearDown(self):
        self.index.close()
        self.temp.cleanup()

    def test_issues_persist_without_model_and_clear_on_removal(self):
        (self.root / "unsupported.csv").write_text("synthetic unsupported data")
        (self.root / "broken.png").write_bytes(b"not an image")
        self.index.refresh(self.root_id)
        self.index.close()
        self.index = Index(self.database)
        issues = self.index.file_issues(self.root_id)["items"]
        self.assertEqual({r["state"] for r in issues}, {"failed", "unsupported"})
        self.assertEqual(next(r for r in issues if r["state"] == "failed")["error"], "image-unreadable")
        self.index.remove_root(self.root_id)
        self.assertEqual(self.index.file_issues()["items"], [])
        with self.assertRaises(ScopeError):
            self.index.file_issues(self.root_id)
        self.assertTrue((self.root / "broken.png").exists())

    def test_freshness_and_recovery_share_coverage_states(self):
        changed, missing = self.root / "changed.txt", self.root / "missing.txt"
        changed.write_text("before")
        missing.write_text("original")
        self.index.refresh(self.root_id)
        self.assertEqual(self.index.file_issues()["items"], [])
        changed.write_text("after, larger content")
        missing.unlink()
        states = {r["state"] for r in self.index.file_issues()["items"]}
        self.assertEqual(states, {"stale", "missing"})
        self.assertEqual(self.index.coverage()["stale"], 1)
        self.assertEqual(self.index.coverage()["missing"], 1)
        self.index.refresh(self.root_id)
        self.assertEqual(self.index.file_issues()["items"], [])

    def test_pagination_and_folder_filter_exclude_healthy_files(self):
        for number in range(7):
            (self.root / f"unsupported{number}.csv").write_text("unsupported")
        (self.root / "healthy.txt").write_text("searchable content")
        self.index.refresh(self.root_id)
        other = Path(self.temp.name) / "other"
        other.mkdir()
        other_id = self.index.add_root(other)
        self.assertEqual(self.index.file_issues(other_id)["items"], [])
        ids, cursor = [], 0
        while cursor is not None:
            page = self.index.file_issues(self.root_id, cursor, limit=2)
            self.assertLessEqual(len(page["items"]), 2)
            ids.extend(r["file_id"] for r in page["items"])
            cursor = page["next_after_id"]
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(set(ids)), 7)
        for limit, after in [(0, 0), (501, 0), (2, -1)]:
            with self.assertRaisesRegex(ValueError, "invalid-issue-page"):
                self.index.file_issues(limit=limit, after_id=after)

    def test_recovery_does_not_render_untrusted_parser_text(self):
        self.assertNotIn("<script", issue_copy("failed", "<script>untrusted data</script>"))
        self.assertIn("English OCR", issue_copy("failed", "ocr-english-unavailable"))


if __name__ == "__main__":
    unittest.main()
