import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import psutil

from omnifind.worker import run_worker


@unittest.skipUnless(os.name == "nt", "Windows Job Object containment")
class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.marker = Path(self.temp.name) / "pid"

    def tearDown(self):
        self.temp.cleanup()

    def assert_worker_gone(self):
        pid = int(self.marker.read_text())
        deadline = time.monotonic() + 5
        while psutil.pid_exists(pid) and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertFalse(psutil.pid_exists(pid))

    def test_timeout_kills_actual_python_child(self):
        with self.assertRaisesRegex(ValueError, "extraction-timeout"):
            run_worker("tests.worker_probe", ["sleep", self.marker], timeout=.5)
        self.assert_worker_gone()

    def test_cancel_or_revocation_checkpoint_kills_worker(self):
        def checkpoint():
            if self.marker.exists():
                raise RuntimeError("scope-revoked")
        with self.assertRaisesRegex(RuntimeError, "scope-revoked"):
            run_worker("tests.worker_probe", ["sleep", self.marker], checkpoint)
        self.assert_worker_gone()

    def test_memory_ceiling_is_enforced(self):
        code, output = run_worker("tests.worker_probe", ["memory", self.marker], memory_bytes=128 * 1024 * 1024)
        self.assertEqual(code, 3)
        self.assertIn("memory-denied", output)
        self.assert_worker_gone()

    def test_output_limit_does_not_accumulate_unbounded_bytes(self):
        with self.assertRaisesRegex(ValueError, "extraction-output-too-large"):
            run_worker("tests.worker_probe", ["output", self.marker], output_bytes=8192)
        self.assert_worker_gone()

    def test_root_removal_during_extraction_kills_worker_and_prevents_commit(self):
        from omnifind.core import Index, ScopeError
        from tests.test_core import StorageEmbedder
        root = self.marker.parent / "corpus"
        root.mkdir()
        source = root / "source.txt"
        source.write_text("synthetic deposit agreement")
        index = Index(self.marker.parent / "data/index.sqlite", StorageEmbedder())
        root_id = index.add_root(root)
        other = Index(index.path)
        def supervised_probe(module, arguments, checkpoint):
            def revoke():
                if self.marker.exists():
                    other.remove_root(root_id)
                checkpoint()
            return run_worker("tests.worker_probe", ["sleep", self.marker], revoke)
        try:
            with patch("omnifind.core.run_worker", side_effect=supervised_probe):
                with self.assertRaises(ScopeError):
                    index.refresh(root_id)
            self.assert_worker_gone()
            self.assertEqual(index.roots(), [])
            self.assertEqual(index.db.execute("SELECT count(*) FROM chunks").fetchone()[0], 0)
            self.assertTrue(source.exists())
        finally:
            other.close()
            index.close()

    def test_containment_failure_never_starts_probe(self):
        with patch("omnifind.windows_job.WindowsJob.assign", side_effect=ValueError("extraction-containment-unavailable")):
            with self.assertRaisesRegex(ValueError, "extraction-containment-unavailable"):
                run_worker("tests.worker_probe", ["sleep", self.marker])
        self.assertFalse(self.marker.exists())

    def test_killed_supervisor_kills_contained_parser(self):
        code = "from omnifind.worker import run_worker; import sys; run_worker('tests.worker_probe',['sleep',sys.argv[1]])"
        parent = subprocess.Popen([sys.executable, "-c", code, str(self.marker)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not self.marker.exists() and parent.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(self.marker.exists(), "Probe did not start")
            parser_pid = int(self.marker.read_text())
            # Kill only the supervisor, never manually terminate its parser/job members.
            candidates = [psutil.Process(parent.pid), *psutil.Process(parent.pid).children(recursive=True)]
            supervisor = next(child for child in candidates if child.pid != parser_pid and code in child.cmdline()
                              and Path(child.exe()).resolve() == Path(sys._base_executable).resolve())
            supervisor.kill()
            self.assert_worker_gone()
        finally:
            if parent.poll() is None:
                parent.kill()
            parent.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
