# OmniFind Local

Describe a file you remember, search selected folders locally, and inspect matching source passages.

Main repository: [zekurou1/appbuildersph-hackathon-2026](https://github.com/zekurou1/appbuildersph-hackathon-2026).

**Current artifact: a working command-line retrieval core, not yet the desktop GUI.** Digital PDF/TXT/MD, local CPU embeddings, lexical/semantic/hybrid search, page/line evidence, SQLite persistence, manual refresh and folder removal are implemented. OCR, scanned PDFs, DOCX and a packaged installer are pending.

## Setup

Use Python 3.12 and [uv](https://docs.astral.sh/uv/). From the repository root:

```powershell
uv sync --locked
& '.venv\Scripts\python.exe' scripts/prepare_model.py --destination models/minilm
& '.venv\Scripts\python.exe' scripts/spike.py --model models/minilm
```

This existing workspace also has `.tools\uv\uv.exe`; it is a local convenience, not distributed with Git. If using it, set `$env:UV_CACHE_DIR = Join-Path $PWD '.tools\cache'` before syncing.

Setup needs internet for dependencies and about 92 MB of public model assets. The tested model revision is pinned by default; preparation records its file hashes. Runtime verifies those assets and uses local-only CPU inference. Model downloads are a separate explicit action. Windows Application Control can block native dependencies: use an approved runtime/environment; this project does not disable those controls.

## Search a folder you explicitly choose

The index stores plaintext extracted text and vectors under `%LOCALAPPDATA%\OmniFindLocal`; original files are preserved. Start with a small synthetic or consented folder. Commands must run from the repository root.

```powershell
& '.venv\Scripts\python.exe' -m omnifind add-folder 'C:\path\to\chosen-folder'
# Use the root_id returned by add-folder; 1 is an example.
& '.venv\Scripts\python.exe' -m omnifind refresh 1
& '.venv\Scripts\python.exe' -m omnifind search 'getting my deposit back after moving out' --type pdf
& '.venv\Scripts\python.exe' -m omnifind search 'INV-2048' --mode lexical --folder 1
& '.venv\Scripts\python.exe' -m omnifind status
& '.venv\Scripts\python.exe' -m omnifind remove-folder 1
```

Refresh manually after changes. Stale/missing files are excluded until refreshed. Search results include the original path, excerpt and page/line reference. Ranking scores are not confidence probabilities; inspect the source before opening it. Absent-target handling is still being calibrated, so candidate results do not guarantee a matching file exists.

For alternate synthetic test storage, pass `--db path/to/index.sqlite` **before** the subcommand. `--model` is also a global option. Lexical and filename search do not load model assets; indexing and semantic/hybrid search require them. Search does not execute retrieved content or automatically open files.

## Verification

```powershell
& '.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.venv\Scripts\python.exe' scripts/evaluate.py --model models/minilm
```

The evaluation generates ten synthetic documents from `fixtures/development.json`, runs 50 author-labeled development queries across all four baselines, and checks fresh-file indexing, restart and removal under a Python socket guard. It creates a fresh isolated run directory each time. These are development results, not a held-out product benchmark or complete network audit. Runtime fixtures/reports, local model assets and index databases are ignored by Git.

See [current status and gates](docs/START.md), [measured development results](docs/RETRIEVAL_RESULTS.md), and [master plan](docs/OMNIFIND_LOCAL_MASTER_PLAN.md).

Technical references: [MiniLM model card and pooling recipe](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [Transformers local asset loading](https://huggingface.co/docs/transformers/installation#offline-mode), [SQLite FTS5](https://sqlite.org/fts5.html), [pypdf extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html). Model card declares Apache-2.0; see [asset provenance](docs/model-assets.json). Local storage is not encryption.
