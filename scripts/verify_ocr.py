"""Evaluate fixed synthetic English images; do not retune policy from these results."""
import hashlib
import json
import socket
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from omnifind.core import Index
from omnifind.model import LocalEmbedder
from omnifind.ocr import runtime_info


def main():
    output = Path("reports/runtime/ocr-validation").resolve()
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    corpus = run / "corpus"
    corpus.mkdir()
    fixture = Path("fixtures/ocr-validation.json")
    raw = fixture.read_bytes()
    data = json.loads(raw)
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 32)
    for case in data["cases"]:
        image = Image.new("RGB", (1200, 400), "white")
        ImageDraw.Draw(image).multiline_text((40, 40), case["text"], font=font, fill="black", spacing=18)
        image.save(corpus / case["file"])
    freeze = {"fixture_sha256": hashlib.sha256(raw).hexdigest(),
              "image_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in corpus.iterdir()}}
    (run / "freeze-before-evaluation.json").write_text(json.dumps(freeze, indent=2))
    attempts = []
    def deny(*args, **kwargs):
        attempts.append("connect")
        raise RuntimeError("Network disabled in verification Python process")
    socket.socket.connect = deny
    socket.create_connection = deny
    model = LocalEmbedder(Path("models/minilm"))
    index = Index(run / "data/index.sqlite", model)
    try:
        root_id = index.add_root(corpus)
        start = time.perf_counter()
        coverage = index.refresh(root_id)
        indexing_seconds = time.perf_counter() - start
        outcomes = []
        for case in data["cases"]:
            response = index.search_response(case["query"], limit=5)
            names = [Path(r["path"]).name for r in response["results"]]
            code = index.search_response(case["code"])
            exact = [Path(r["path"]).name for r in code["results"]]
            # OCR text is separately compared with authored text, never used to assign relevance.
            recognized = "".join(row[0] for row in index.db.execute(
                "SELECT c.text FROM chunks c JOIN files f ON f.id=c.file_id WHERE f.path=? ORDER BY c.id", (str(corpus / case["file"]),)))
            outcomes.append({"file": case["file"], "query": case["query"], "status": response["status"],
                             "top5": names, "relevant_in_top5": case["file"] in names,
                             "exact_code_files": exact, "exact_code_correct": exact == [case["file"]],
                             "recognized_text_equals_authored": recognized.strip() == case["text"].strip()})
        absent = {code: not index.search_response(code)["results"] for code in data["absent_codes"]}
        assert hashlib.sha256(fixture.read_bytes()).hexdigest() == freeze["fixture_sha256"]
        report = {"dataset": data["dataset"], "runtime": runtime_info(), "model": model.identity,
                  "coverage": coverage, "indexing_seconds": indexing_seconds, "freeze": freeze,
                  "outcomes": outcomes, "absent_codes_rejected": absent,
                  "python_socket_connect_attempts": len(attempts),
                  "limits": ["Six clean synthetic English images; author-created labels, not independent user validation",
                             "No ranking or gate tuning during evaluation; this corpus is now regression data",
                             "Socket guard covers evaluator only, not native OCR or process-tree egress",
                             "No handwriting, multilingual, rotated, low-contrast or scanned-PDF claim"]}
        (output / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        index.close()


if __name__ == "__main__":
    main()
