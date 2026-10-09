"""WP1 only: synthetic extraction + CPU embeddings. No personal folder scan."""
import os

# Set before importing any model library. Setup is a separate explicit command.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import socket
import sqlite3
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/runtime"))
    args = parser.parse_args()
    model_path = args.model.resolve()
    if not (model_path / "asset-manifest.json").is_file():
        parser.error("Local model assets are missing. Run prepare_model.py explicitly first.")
    manifest = json.loads((model_path / "asset-manifest.json").read_text(encoding="utf-8"))
    for name, entry in manifest["files"].items():
        path = (model_path / name).resolve()
        if not path.is_relative_to(model_path) or not path.is_file():
            raise RuntimeError("Invalid model manifest path")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                raise RuntimeError("Model asset checksum mismatch")

    network_attempts = []
    def deny_connection(*args, **kwargs):
        network_attempts.append("socket-connect")
        raise RuntimeError("Network blocked during WP1 inference")
    socket.socket.connect = deny_connection
    socket.create_connection = deny_connection

    import numpy as np
    import psutil
    from PIL import Image, ImageDraw, ImageFont
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas
    from sentence_transformers import SentenceTransformer

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    corpus = output / "synthetic-corpus"
    corpus.mkdir(exist_ok=True)
    documents = [
        "Rental agreement: the security deposit is returned within thirty days after moving out, minus unpaid rent or damage repairs.",
        "Purchase receipt INV-2048: laptop charger, total 1250 pesos. Return defective items within seven days.",
        "Project instructions: prepare a ten-minute presentation about renewable energy for Friday.",
    ]
    pdf_path = corpus / "scan_0042.pdf"
    pdf = canvas.Canvas(str(pdf_path))
    text = pdf.beginText(50, 780)
    for line in ["Fictional rental agreement", "The security deposit is returned within thirty days after moving out,",
                 "minus unpaid rent or damage repairs."]:
        text.textLine(line)
    pdf.drawText(text)
    pdf.save()
    pages = PdfReader(pdf_path).pages
    extracted = pages[0].extract_text()
    assert "security deposit" in extracted and "thirty days" in extracted
    documents[0] = extracted
    (corpus / "notes_17.txt").write_text(documents[1], encoding="utf-8")
    (corpus / "draft.md").write_text(documents[2], encoding="utf-8")

    started = time.perf_counter()
    model = SentenceTransformer(str(model_path), device="cpu", local_files_only=True,
                                trust_remote_code=False, model_kwargs={"use_safetensors": True})
    load_seconds = time.perf_counter() - started
    vectors = model.encode(documents, normalize_embeddings=True)
    query = "Which document explains getting my money back when I leave the apartment?"
    durations = []
    for _ in range(6):
        started = time.perf_counter()
        query_vector = model.encode([query], normalize_embeddings=True)[0]
        scores = vectors @ query_vector
        durations.append(time.perf_counter() - started)
    assert vectors.shape == (3, 384)
    assert np.isfinite(vectors).all()
    assert int(np.argmax(scores)) == 0, "Synthetic paraphrase did not retrieve the rental PDF"
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
        connection.execute("INSERT INTO probe VALUES (?)", (extracted,))
        assert connection.execute("SELECT count(*) FROM probe WHERE probe MATCH 'deposit'").fetchone()[0] == 1

    ocr = {"status": "not-run", "reason": "Tesseract executable unavailable"}
    executable = shutil.which("tesseract")
    if executable:
        image = Image.new("RGB", (1200, 300), "white")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 40)
        except OSError:
            font = ImageFont.load_default(size=40)
        draw.text((40, 40), "CLASS SCHEDULE\nMonday 9:00 AM Mathematics\nTuesday 1:00 PM Chemistry", fill="black", font=font)
        image_path = corpus / "schedule.png"
        image.save(image_path)
        process = subprocess.run([executable, str(image_path), "stdout", "-l", "eng"],
                                 capture_output=True, text=True, timeout=30, check=True)
        assert "Mathematics" in process.stdout
        ocr = {"status": "passed", "recognized_schedule": True}

    report = {
        "phase": "WP1 feasibility", "python": platform.python_version(), "platform": platform.platform(),
        "physical_ram_bytes": psutil.virtual_memory().total,
        "current_process_rss_bytes": psutil.Process().memory_info().rss,
        "model_id": manifest["model_id"], "model_revision": manifest["revision"],
        "asset_bytes": manifest["total_bytes"], "backend": "CPU / PyTorch",
        "versions": {name: importlib.metadata.version(name) for name in
                     ["sentence-transformers", "torch", "transformers", "pypdf", "numpy", "Pillow"]},
        "model_load_seconds": load_seconds, "query_seconds": durations,
        "synthetic_pdf": {"status": "passed", "page": 1},
        "semantic_paraphrase": {"status": "passed", "top_file": "scan_0042.pdf", "scores": scores.tolist()},
        "embedding_shape": list(vectors.shape), "fts5": "passed", "ocr": ocr,
        "python_socket_connection_attempts": len(network_attempts),
        "limitations": ["Three synthetic documents only; not a retrieval benchmark",
                        "Socket guard covers this Python process; not an OS egress audit",
                        "RSS is a point sample, not peak process-tree memory",
                        "UI, durable index, refresh/removal and packaging are not implemented"],
    }
    (output / "wp1-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
