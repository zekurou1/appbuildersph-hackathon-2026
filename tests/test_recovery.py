"""Real subprocess interruption/lock and storage-cleanup tests on synthetic files."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from omnifind.core import Index
from tests.test_core import StorageEmbedder


CHILD = '''
import sys, time
from pathlib import Path
from omnifind.core import Index
from tests.test_core import StorageEmbedder
database, root_id, marker, phase = sys.argv[1:]
model = StorageEmbedder()
index = Index(database, model)
def pause(*args):
    Path(marker).write_text("ready")
    time.sleep(60)
if phase == "embedding":
    model.encode = pause
else:
    def trace(sql):
        if sql.startswith("INSERT INTO chunks") or (phase == "clear" and sql.startswith("DROP TABLE chunk_fts")):
            pause()
    index.db.set_trace_callback(trace)
if phase == "clear":
    index.clear()
else:
    index.refresh(int(root_id))
'''


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "corpus"
        self.root.mkdir()
        self.source = self.root / "receipt.txt"
        self.source.write_text("uniqueprivacycanary714 security deposit")
        self.database = self.base / "data/index.sqlite"
        self.index = Index(self.database, StorageEmbedder())
        self.root_id = self.index.add_root(self.root)
        self.index.refresh(self.root_id)

    def tearDown(self):
        self.index.close()
        self.temp.cleanup()

    def child(self, phase):
        marker = self.base / "ready"
        marker.unlink(missing_ok=True)
        process = subprocess.Popen([sys.executable, "-c", CHILD, str(self.database), str(self.root_id), str(marker), phase],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        if not marker.exists():
            process.kill()
            _, error = process.communicate()
            self.fail("Child did not reach interruption point: " + error.decode())
        return process

    def kill(self, process):
        process.kill()
        process.communicate(timeout=10)

    def test_interrupted_embedding_releases_lease_and_recovers(self):
        self.source.write_text("replacement receipt")
        process = self.child("embedding")
        try:
            with self.assertRaisesRegex(ValueError, "index-busy"):
                self.index.refresh(self.root_id)
            with self.assertRaisesRegex(ValueError, "index-busy"):
                self.index.clear()
            with self.assertRaisesRegex(ValueError, "index-busy"):
                self.index.add_root(self.root)
            self.assertEqual(self.index.search("deposit", "lexical"), [])
        finally:
            self.kill(process)
        self.index.refresh(self.root_id)
        self.assertEqual(len(self.index.search("replacement", "lexical")), 1)

    def test_killed_commit_rolls_back_metadata_chunks_and_fts(self):
        self.source.write_text("replacement receipt")
        process = self.child("commit")
        self.kill(process)
        self.index.close()
        self.index = Index(self.database, StorageEmbedder())
        self.assertEqual(self.index.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.index.db.execute("SELECT text FROM chunks").fetchone()[0], "uniqueprivacycanary714 security deposit")
        self.assertEqual(self.index.db.execute("SELECT content FROM chunk_fts").fetchone()[0], "uniqueprivacycanary714 security deposit")
        self.assertEqual(self.index.search("deposit", "lexical"), [])
        self.index.refresh(self.root_id)
        self.assertEqual(len(self.index.search("replacement", "lexical")), 1)

    def test_clear_restarts_empty_without_canary_or_sidecars(self):
        result = self.index.clear()
        self.assertTrue(result["compacted"])
        self.index.close()
        self.index = Index(self.database, StorageEmbedder())
        self.assertEqual(self.index.roots(), [])
        for table in ["files", "chunks", "chunk_fts"]:
            self.assertEqual(self.index.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(self.index.search("deposit", "lexical"), [])
        for path in self.database.parent.iterdir():
            self.assertNotIn(b"uniqueprivacycanary714", path.read_bytes())
        self.assertFalse(Path(str(self.database) + "-journal").exists())
        self.assertFalse(Path(str(self.database) + "-wal").exists())
        self.assertEqual(self.source.read_text(), "uniqueprivacycanary714 security deposit")
        # Clearing does not break subsequent trigger/FTS writes or folder removal.
        root_id = self.index.add_root(self.root)
        self.index.refresh(root_id)
        self.assertEqual(len(self.index.search("deposit", "lexical")), 1)
        self.index.remove_root(root_id)
        self.assertEqual(self.index.search("deposit", "lexical"), [])

    def test_removed_root_canary_is_not_in_current_database(self):
        self.index.remove_root(self.root_id)
        self.assertNotIn(b"uniqueprivacycanary714", self.database.read_bytes())
        self.assertNotIn(b"receipt.txt", self.database.read_bytes())

    def test_killed_clear_rolls_back_and_can_be_retried(self):
        process = self.child("clear")
        self.kill(process)
        self.index.close()
        self.index = Index(self.database, StorageEmbedder())
        self.assertEqual(self.index.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(len(self.index.search("deposit", "lexical")), 1)
        self.assertTrue(self.index.clear()["cleared"])
        self.assertEqual(self.index.roots(), [])

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_real_junction_cannot_index_or_authorize_outside(self):
        outside = self.base / "outside"
        outside.mkdir()
        secret = outside / "outside.txt"
        secret.write_text("outsidecanary914")
        junction = self.root / "escape"
        # Link creation only; neither tree is moved or recursively removed.
        completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True)
        if completed.returncode:
            self.skipTest("Host cannot create junction")
        try:
            with self.assertRaises(ValueError):
                self.index.authorize(self.root_id, junction / "outside.txt")
            self.index.refresh(self.root_id)
            self.assertEqual(self.index.search("outsidecanary914", "lexical"), [])
            self.assertTrue(secret.exists())
        finally:
            os.rmdir(junction)


if __name__ == "__main__":
    unittest.main()
