"""Readiness probe using synthetic data only; no downloads or OS changes."""
import argparse
import json
import platform
import sqlite3
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from omnifind.model import LocalEmbedder
from omnifind.worker import run_worker
from omnifind.ocr import runtime_info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path("models/minilm"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"python": platform.python_version(), "os": platform.platform(),
              "sqlite": sqlite3.sqlite_version, "checks": {}}
    checks = report["checks"]
    try:
        from PIL import Image, ImageDraw, ImageFont
        from PySide6.QtCore import qVersion
        report["qt"] = qVersion()
        report["packages"] = {name: version(name) for name in ["torch", "transformers", "Pillow", "PySide6"]}
        checks["sqlite_secure_fts_available"] = sqlite3.sqlite_version_info >= (3, 42, 0)
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
            connection.execute("INSERT INTO probe(probe, rank) VALUES('secure-delete', 1)")
            checks["sqlite_fts_probe"] = True
        finally:
            connection.close()
        model = LocalEmbedder(args.model)
        checks["verified_local_model_inference"] = model.encode(["Synthetic setup test"] ).shape == (1, 384)
        report["model"] = model.identity
        report["ocr"] = runtime_info()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "probe.png"
            image = Image.new("RGB", (700, 180), "white")
            ImageDraw.Draw(image).text((30, 30), "SETUP TEST OCR-482", fill="black",
                font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 32))
            image.save(source)
            code, result = run_worker("omnifind.extract", [source, root])
            checks["contained_windows_ocr"] = code == 0 and "OCR-482" in result
            if code:
                report["ocr_error"] = json.loads(result).get("error", "ocr-worker-failed")
    except Exception:
        # Deliberately omit paths, tracebacks and source content from setup reports.
        checks["runtime_probe_completed"] = False
    report["ready_on_this_host"] = bool(checks) and all(checks.values())
    report["limits"] = ["Same-host readiness only; not a clean-machine or packaged deployment certification",
                        "No OS-level process-tree network audit"]
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ready_on_this_host"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
