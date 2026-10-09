# OmniFind Local

Describe a file you remember, search selected folders locally, and inspect matching source passages.

Main repository: [zekurou1/appbuildersph-hackathon-2026](https://github.com/zekurou1/appbuildersph-hackathon-2026).

**Current artifact: a native desktop prototype plus command-line retrieval core.** Digital PDF/TXT/MD, local CPU embeddings, lexical/semantic/hybrid search, page/line evidence, SQLite persistence, manual refresh and folder removal are implemented. OCR, scanned PDFs, DOCX and a packaged installer are pending.

## Setup

Use Python 3.12 and [uv](https://docs.astral.sh/uv/). From the repository root:

```powershell
uv sync --locked
& '.venv\Scripts\python.exe' scripts/prepare_model.py --destination models/minilm
& '.venv\Scripts\python.exe' scripts/spike.py --model models/minilm
```

This existing workspace also has `.tools\uv\uv.exe`; it is a local convenience, not distributed with Git. If using it, set `$env:UV_CACHE_DIR = Join-Path $PWD '.tools\cache'` before syncing.

Setup needs internet for dependencies and about 92 MB of public model assets. The tested model revision is pinned by default; preparation records its file hashes. Runtime verifies those assets and uses local-only CPU inference. Model downloads are a separate explicit action. Windows Application Control can block native dependencies: use an approved runtime/environment; this project does not disable those controls.

## Launch the desktop app

```powershell
& '.venv\Scripts\python.exe' -m omnifind.gui
# Alternatively, from the project folder:
& 'scripts\start-desktop.ps1'
```

Open Folders, choose a local folder, and select Refresh selected. Then describe a file in Search, inspect the original passage, and choose Open original or Show in folder. Search runs on Enter or Search; query/filter changes require another explicit Search. The first local model load runs in the background. Cancel stops after the current step; removing a folder revokes its scope and keeps original files. Settings includes light/dark appearance, larger text and plaintext-storage disclosure.

If no strong match is found, revise the description or enable Show weaker matches and search again. Thresholds were fitted to synthetic development examples and can hide valid files; they are not confidence scores. Words only can search an existing index when model assets are missing. GUI verification used real inference and offscreen Qt controls; native picker responses and OS open/reveal launches were intercepted in the test. Manual Windows and screen-reader validation remain.

See [desktop phase and model comparison](docs/DESKTOP_PHASE.md). The desktop default remains MiniLM. BGE is an explicit experiment requiring its own index:

```powershell
& '.venv\Scripts\python.exe' scripts/prepare_model.py --destination models/bge --model-id BAAI/bge-small-en-v1.5
& '.venv\Scripts\python.exe' scripts/compare_models.py
```

The optional BGE setup downloads about 135 MB. To launch with it, pass `--model models/bge --db <separate-index-path>` to `omnifind.gui`; model vectors are not automatically migrated or mixed.

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

Refresh manually after changes. Stale/missing files are excluded until refreshed. Search results include the original path, excerpt and page/line reference. Ranking scores are not confidence probabilities; inspect the source before opening it. Semantic/hybrid search uses an experimental model-specific weak-match gate. Pass `--show-weak` after the search subcommand to reveal weaker candidates. A candidate does not guarantee a matching file exists.

Settings → Clear index forgets all selected folders and removes derived index data after confirmation; originals and downloaded models are preserved. CLI equivalent: `python -m omnifind clear-index --yes` using the project's virtual environment. Competing refresh/add/clear operations receive a retry message. SQLite 3.42 or newer is required for secure FTS deletion. See [reliability and cleanup checks](docs/RELIABILITY_PHASE.md) for tested crash recovery and privacy limits.

Windows extraction now runs in a Job Object with bounded memory, process count, duration and output. Cancellation/removal stops an active parser; model inference stops after its current call. Other desktop windows automatically clear revoked previews/actions through a persistent privacy epoch. See [containment verification](docs/CONTAINMENT_PHASE.md). OS-level network auditing and clean-machine packaging remain pending.

For alternate synthetic test storage, pass `--db path/to/index.sqlite` **before** the subcommand. `--model` is also a global option. Lexical and filename search do not load model assets; indexing and semantic/hybrid search require them. Search does not execute retrieved content or automatically open files.

## Verification

```powershell
& '.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.venv\Scripts\python.exe' scripts/evaluate.py --model models/minilm
& '.venv\Scripts\python.exe' scripts/verify_gui.py
```

The evaluation generates ten synthetic documents from `fixtures/development.json`, runs 50 author-labeled present-target queries and 20 absent-target probes, and checks fresh-file indexing, restart and removal under a Python socket guard. It evaluates raw ranking separately from the weak-match gate. Each run uses a fresh isolated directory. Desktop verification additionally drives the real Qt controls, background inference, evidence, weak-match recovery, stale-file safety and removal; screenshots go to `reports/runtime/gui`. These are development results, not a held-out product benchmark or complete network audit. Runtime fixtures/reports, local model assets and index databases are ignored by Git.

See [current status and gates](docs/START.md), [measured development results](docs/RETRIEVAL_RESULTS.md), and [master plan](docs/OMNIFIND_LOCAL_MASTER_PLAN.md).

The [frozen holdout report](docs/HOLDOUT_EVALUATION.md) measures new synthetic documents without retuning the current policy. Raw hybrid retrieves all labeled targets, but its weak-match gate hides eight identifier searches and reaches 84% Recall@5. For exact codes, Words only avoids this semantic gate. Reproduce with `python scripts/evaluate_holdout.py` from the virtual environment; the runner rejects changes to frozen inputs or retrieval implementation. This is not user validation or a release pass.

Technical references: [MiniLM model card and pooling recipe](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [Transformers local asset loading](https://huggingface.co/docs/transformers/installation#offline-mode), [SQLite FTS5](https://sqlite.org/fts5.html), [pypdf extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html). Model card declares Apache-2.0; see [asset provenance](docs/model-assets.json). Local storage is not encryption.
