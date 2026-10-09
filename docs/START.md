# OmniFind Local implementation start

Started October 10, 2026 (Asia/Manila), from the supplied master plan revision 2.

The first deliverable is WP1 feasibility, followed by WP2 retrieval and WP3 durable state. Full desktop UI begins after those gates pass. Windows CPU-first, English-first, digital PDF/TXT/MD is the initial scope. Screenshot OCR is gated separately. No personal folders are authorized by these synthetic tests.

| Package | Completion gate | Initial state |
| --- | --- | --- |
| WP1 | Real CPU query/document embeddings, PDF extraction, pinned asset manifest; OCR separately | Scaffold ready; runtime blocked by Windows Application Control |
| WP2 | Labeled queries, lexical/semantic/hybrid comparison, grouped source evidence | Pending |
| WP3 | Atomic revisions, restart, refresh and root revocation | Pending |
| WP4 | Select folder → index → search → inspect → open/reveal | Pending |
| WP5 | Fresh offline file/query, egress, boundaries, cleanup and recovery | Pending |
| WP6 | Holdout evaluation, clean setup and demo evidence | Pending |

## Verified start results

- Workspace was empty; no existing application stack or repository instructions were present.
- Prepared workspace-local Python 3.12.15, uv, virtual environment and `uv.lock`; 47 dependencies installed.
- Python source compilation passed. Missing-model invocation exits with a setup-required error before importing inference dependencies.
- Model setup failed importing `_ssl`: `DLL load failed while importing _ssl: An Application Control policy has blocked this file.` This occurred with elevated execution too; security policy was not changed.
- No model download, embedding, PDF extraction or OCR success is claimed. Tesseract was not found on PATH. WP1 is not passed.
- Next action: use an approved Python 3.12 runtime that can import `ssl`, rebuild this project's virtual environment from `uv.lock`, prepare model assets and rerun WP1. Measure hardware during that run; an earlier CIM RAM lookup was denied.

Source plan copied unchanged to [OMNIFIND_LOCAL_MASTER_PLAN.md](OMNIFIND_LOCAL_MASTER_PLAN.md), SHA-256 `50F4D48128945921D52DC7FB8219628042F490D38C547BB2627CE7166473334A`.

## UI contract for the next phase

Desktop Search/Folders/Settings destinations. Search uses explicit submit, type/folder filters, distinct-file results and an evidence panel with original page/line references. Open and Show in folder require deliberate user actions. Preserve the query on errors; label limited lexical mode when model assets are missing. Define empty, indexing, partial coverage, no matches, failed model, stale/missing source and removed-folder states. Native keyboard focus and accessible labels are required. Mobile is deferred as described in master section 33.

## Data boundary

Model setup downloads public assets explicitly. Spike inference reads only generated synthetic files and local model assets. No hosted inference, content telemetry or cloud fallback is configured. Later private indexes must use local application data outside this OneDrive workspace; the prototype index will be plaintext and disclosed. Socket-blocked inference is an initial check, not a complete network audit.
