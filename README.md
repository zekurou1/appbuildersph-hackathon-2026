# OmniFind Local

Main project repository: [zekurou1/appbuildersph-hackathon-2026](https://github.com/zekurou1/appbuildersph-hackathon-2026).

Implementation has started with the master plan's **WP1 feasibility spike**. This is not yet the desktop application.

Current execution blocker: Windows Application Control prevents the downloaded Python runtime from importing `_ssl`. Dependencies installed and source compilation passed, but model setup and inference have not passed. Use an approved Python 3.12 runtime before continuing; see [status](docs/START.md).

## Run the spike (PowerShell, repository root)

Python 3.12 and uv are required. This workspace contains a local runtime under `.tools` and `.venv`; these are ignored by Git.

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.tools\cache'
& '.tools\uv\uv.exe' sync
& '.venv\Scripts\python.exe' scripts/prepare_model.py --destination models/minilm
& '.venv\Scripts\python.exe' scripts/spike.py --model models/minilm
```

Setup downloads dependencies and public model assets. The preparation script resolves an exact model revision and records SHA-256 hashes and sizes. The spike verifies hashes, uses CPU inference and local-only assets, blocks Python socket connections, generates a harmless digital PDF, checks a paraphrase against three documents and tests SQLite FTS5. If Tesseract is available on PATH, it also tests generated schedule OCR. Missing OCR does not pass the screenshot gate.

Results go to `reports/runtime/wp1-report.json`. Synthetic fixtures are created in that directory; no Downloads/Desktop/Documents folders are scanned. `uv.lock` records resolved dependencies. Models and private derivatives must stay out of Git.

See [implementation status and UI contract](docs/START.md).

Technical references checked at start: [Sentence Transformers installation](https://sbert.net/docs/installation.html), [MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [pypdf extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html). PDF extraction does not imply scanned-PDF OCR support.
