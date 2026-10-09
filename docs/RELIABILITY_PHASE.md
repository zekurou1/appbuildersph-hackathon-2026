# Reliability and cleanup phase

October 10, 2026. Windows prototype hardening; not a packaged-release privacy certification.

## Changes

Refresh takes a nonblocking cross-process byte-range lock on Windows (flock on other hosts). A second refresh, folder addition or clear-index receives a retry error while that lock is owned. The OS releases it when the owner exits or is killed; no stale PID cleanup or lock-file deletion is needed. The one-byte `.lock` file contains no private paths or job data and is intentionally retained. Removal remains possible during refresh and existing authorization checks prevent late commits. Search continues to use committed records; the GUI itself still serializes tasks.

Settings now offers Clear index with a default-No confirmation. It runs in the background, forgets selected folders, deletes derived records, recreates the FTS table and compacts the database. Originals and model assets are preserved. No query history, OCR cache or preview file cache is created by the application. This operation is not cancelable after confirmation. If compaction fails, the app reports durable logical deletion separately from incomplete compaction. A process killed before deletion commits leaves the prior index intact; rerun Clear index after restart.

Both SQLite core and FTS secure-delete are enabled. Existing FTS segments are rebuilt once when adopting this setting; SQL temporary storage uses memory. FTS secure-delete requires SQLite 3.42 or later, now checked explicitly. This follows [SQLite's FTS deletion guidance](https://sqlite.org/fts5.html#the_secure_delete_configuration_option); core secure-delete alone does not cover old FTS segments. Clear-index recreates the shadow tables and then uses [VACUUM](https://sqlite.org/lang_vacuum.html). These controls are not encryption or a guarantee of forensic erasure from SSDs, backups or OS artifacts.

## Observed verification

Nineteen passing tests and one skipped symbolic-link test across core/lifecycle/recovery. Six recovery tests use synthetic files and include real subprocesses and a real Windows directory junction:

- Kill during embedding: competing refresh/add/clear are rejected; the lease is released after kill and reindex succeeds.
- Kill inside a replacement transaction before new chunks: restart integrity check is `ok`, previous chunks and FTS remain consistent, stale originals are hidden and refresh recovers.
- Kill during clear before commit: restart retains the previous searchable revision; retry clears successfully.
- Clear and restart: roots/files/chunks/FTS are empty, the synthetic canary is absent from current app database-directory files, rollback journal/WAL are absent, originals retain their exact content and rebuilding works.
- Root removal: the synthetic text/path canaries are absent from the current database bytes.
- Junction points outside the selected root: authorization rejects it, traversal excludes it and its original target survives.

The real MiniLM offscreen desktop check passes both declined and accepted clear confirmation, rebuild and the existing search/evidence/revocation flow, with zero participating Python socket-connect attempts. See [GUI report](gui-verification.json). Picker response and viewer launches remain intercepted; this is not manual Windows validation.

Reproduce from the repository root:

```powershell
& '.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.venv\Scripts\python.exe' scripts/verify_gui.py
# Destructive to derived index data only; use a synthetic database for verification.
& '.venv\Scripts\python.exe' -m omnifind --db reports/runtime/cleanup/index.sqlite clear-index --yes
```

## Remaining gates

No OS/process-tree egress audit, parser memory/job containment, forced termination of a native extraction child, low-disk/low-memory device fault injection, clean-machine packaging or frozen holdout evaluation has passed yet. The tests use rollback-journal mode on a local synthetic database; arbitrary externally configured WAL stores and network filesystems are not verified. Other open windows may retain already displayed passages until their next operation; authorization is rechecked for search/actions, but cross-window live preview clearing is not implemented. Clipboard contents, old test reports, downloaded models, OS dumps and external backups are not erased by Clear index. Do not promise complete-device or forensic cleanup.
