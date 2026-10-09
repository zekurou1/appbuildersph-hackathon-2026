"""Actual installed OCR and scoped retrieval; fixture embeddings test storage only."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from omnifind.worker import run_worker
from omnifind.core import Index
from tests.test_core import StorageEmbedder


@unittest.skipUnless(os.name == "nt", "Installed Windows OCR")
class OcrTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "corpus"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def picture(self, name, text):
        image = Image.new("RGB", (1000, 450), "white")
        ImageDraw.Draw(image).multiline_text((40, 40), text, fill="black",
            font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 32), spacing=18)
        path = self.root / name
        image.save(path)
        return path

    def test_real_ocr_search_restart_and_revocation(self):
        source = self.picture("schedule.png", "CLASS SCHEDULE - SCH-642\nPhysics laboratory: Wednesday 3 PM\nRoom 307. Bring safety goggles.")
        database = Path(self.temp.name) / "data/index.sqlite"
        index = Index(database, StorageEmbedder())
        try:
            root_id = index.add_root(self.root)
            self.assertEqual(index.refresh(root_id)["searchable"], 1)
            response = index.search_response("SCH-642", suffix="png")
            self.assertEqual(len(response["results"]), 1)
            result = response["results"][0]
            self.assertEqual(result["provenance"], "ocr-recognized")
            self.assertIn("Wednesday 3 PM", result["text"])
            self.assertEqual(index.source_path(result["file_id"], result["revision"]), source)
            self.assertEqual(index.search_response("SCH-642", suffix="txt")["results"], [])
            index.close()
            index = Index(database, StorageEmbedder())
            self.assertEqual(len(index.search_response("SCH-642")["results"]), 1)
            index.remove_root(root_id)
            self.assertEqual(index.search_response("SCH-642")["results"], [])
            self.assertTrue(source.exists())
        finally:
            index.close()

    def test_blank_corrupt_and_oversized_fail_explicitly(self):
        blank = self.picture("blank.jpg", "")
        corrupt = self.root / "corrupt.png"
        corrupt.write_bytes(b"invalid image")
        large = self.root / "large.png"
        Image.new("RGB", (2001, 2000), "white").save(large)
        for path, error in [(blank, "ocr-no-readable-text"), (corrupt, "image-unreadable"), (large, "ocr-image-too-large")]:
            code, output = run_worker("omnifind.extract", [path, self.root])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output)["error"], error)


if __name__ == "__main__":
    unittest.main()
