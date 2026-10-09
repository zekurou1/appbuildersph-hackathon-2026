# OmniFind Local implementation status

Updated October 10, 2026 (Asia/Manila), from master plan revision 2.

Main repository: [zekurou1/appbuildersph-hackathon-2026](https://github.com/zekurou1/appbuildersph-hackathon-2026).

| Package | Completion gate | Current state |
| --- | --- | --- |
| WP1 | Real CPU embeddings and digital PDF extraction; asset manifest | Passed for text tier; screenshot OCR not tested |
| WP2 | Labeled development queries, four retrieval baselines, grouped source evidence | Working CLI core; 50 synthetic development queries evaluated. Model comparison and no-match calibration remain |
| WP3 | Atomic state, restart, refresh, root revocation | Basic implementation and fault tests passed; comprehensive crash/concurrency/recovery work remains |
| WP4 | Select folder → index → search → inspect → open/reveal through UI | Next implementation package; no GUI yet |
| WP5 | Fresh offline file/query, egress, boundaries, cleanup and recovery | Python socket-guarded fresh file/query passed; full OS egress/privacy audit pending |
| WP6 | Holdout evaluation, clean setup and demo evidence | Pending |

## Verified runtime

The original `_ssl` failure no longer reproduces. A scikit-learn native DLL remained blocked by Windows Application Control. The smaller adapter now uses the MiniLM model card's direct Transformers/PyTorch mean-pooling and normalization path, removing unused Sentence Transformers/scikit-learn/SciPy dependencies. No security policy was changed. Dependencies are locked in `uv.lock`.

Python 3.12.15, Windows 11 build 26200, about 16.5 GB installed RAM. CPU MiniLM produced finite normalized 384-dimensional embeddings and found a synthetic rental PDF using a paraphrased query. Digital PDF extraction and FTS5 passed. Model assets total 91,617,680 bytes; exact revision and SHA-256 entries are in [model-assets.json](model-assets.json).

No Tesseract executable was found on PATH. Scope remains digital PDF/TXT/MD. Screenshot search, scanned PDFs and DOCX are unsupported, not silently treated as searchable.

## Retrieval and persistence

Explicit folders only. Overlapping roots, links/junctions, cloud placeholders and the index data folder are rejected/excluded. Workers recheck the path boundary before reading. PDF extraction runs in a separate process with a 20-second timeout, a 20 MiB file limit, 200-page limit and two-million-character output limit. Native parser peak-memory enforcement remains future work.

Chunks are original source slices using the pinned tokenizer: up to 160 tokens with 30 overlap. PDF evidence retains page numbers; text evidence retains line ranges. Source evidence is not generated prose. Inputs beyond the model token budget fail visibly rather than being silently truncated.

SQLite stores metadata, selected roots, file fingerprints, chunks, local vectors and FTS5. Per-file replacement is transactional across all those records. Search applies folder/type eligibility and freshness checks before candidate truncation, groups distinct files and revalidates source authorization before returning results. Model identity mismatches require a separate new index; migration is not yet implemented.

Manual refresh handles changed/new/deleted files and records unsupported/failed files. Changed or missing originals are excluded from results until refreshed, with coverage showing stale/missing states. Removing a root deletes its text/vector/FTS derivatives in one transaction, including after restart, and preserves originals. Lexical search of committed content works without loading the model, with an explicit mode selection.

## Evidence and remaining gates

See [retrieval development results](RETRIEVAL_RESULTS.md) and the machine-readable [evaluation report](retrieval-evaluation.json). Fifty present-target queries over ten synthetic documents compare filename, lexical, semantic and hybrid modes. This deliberately includes misleading filenames; it does not establish general superiority over filename search or production accuracy. Labels were authored with the corpus, not inferred from model winners.

Absent-target queries currently return candidates; they are labeled as requiring source verification. Before GUI release, add more absent/ambiguous queries, calibrate weak-match handling, compare an alternative embedding model, and validate on a frozen holdout. Also finish WP3 process termination/concurrent refresh, actual junction tests, parser memory limits, consented larger-corpus performance and cleanup audits. Current tests simulate transaction failure and revocation; they do not prove every crash state. The host does not permit symbolic-link creation, so that test is skipped.

## UI contract

Desktop Search/Folders/Settings. Explicit submit, visible folder/type filters, distinct results and source evidence; deliberate Open/Show in folder actions. Preserve the query on errors, label lexical-only mode, and cover empty, indexing, partial coverage, no strong match, model failure, stale/missing source and removed-folder states. Keyboard focus and accessible names are required. Mobile remains deferred under master section 33.

## Data boundary

Setup explicitly downloads public dependencies/model assets. Inference uses local-only model loading on CPU without cloud fallback or content telemetry. Python socket guards observed zero connection attempts in tested WP1 and retrieval operations; this is not an OS/process-tree egress audit. Query history is not stored. CLI search prints requested source results; error diagnostics omit paths/content/tracebacks.

The default CLI index is plaintext in `%LOCALAPPDATA%\OmniFindLocal`, outside this OneDrive workspace. Explicit `--db` overrides are for synthetic verification or a user-chosen storage location. Model assets remain under ignored `models/`; external folder sync/backup is outside the application's control. No personal folders were scanned during these tests.

Source master plan is unchanged: [OMNIFIND_LOCAL_MASTER_PLAN.md](OMNIFIND_LOCAL_MASTER_PLAN.md), SHA-256 `50F4D48128945921D52DC7FB8219628042F490D38C547BB2627CE7166473334A`.
