# Desktop phase and model-selection evidence

October 10, 2026 (Asia/Manila). Native PySide6 desktop prototype, connected to the real local retrieval core. This is not a packaged or public-pilot release.

## Operable journey

Search/Folders/Settings navigation, explicit native folder selection, manual background refresh with committed coverage, query submission by Enter or Search, folder/type/mode filters, original page/line evidence and deliberate Open original/Show in folder/Copy path actions. No file opens on selection. No account, hosted assets or webview is involved. Query history stays off.

The search field is stable across empty and populated states. Changing the query or a filter clears old evidence and disables file actions while preserving the description. In this prototype, filters require another explicit Search; this is a declared departure from the master plan's automatic filter resubmission. While a task runs, its query/filter controls are disabled and navigation remains available. Tasks are serialized; results from concurrent UI requests cannot replace each other. Committed search is not simultaneously available during a refresh in this first UI.

Small windows use stacked results/preview and two filter rows. Light/dark colors follow the master tokens. Settings offers Standard/Larger/Largest text and scrolls when content grows. Theme/text size changes apply for the current session; persistence is deferred. Ctrl+K focuses Search, Enter submits, Escape requests cancellation, and list navigation uses native keyboard behavior. Native accessibility names, label buddies and visible focus borders are provided; screen-reader behavior has not been validated.

The later [containment phase](CONTAINMENT_PHASE.md) now kills active Windows parser jobs on cancellation/removal and bounds their memory/output. Model inference still stops after its current call. Close requests cancellation and waits for the worker to finish before closing. Folder removal stays available while background work runs, requires a concrete confirmation, revokes scope and removes derived index records while retaining originals. Generation checks discard obsolete queued results, and a persistent privacy epoch clears revoked previews in other windows.

Evidence and file actions revalidate root authorization, source freshness and the expected indexed fingerprint. A refreshed file cannot be opened using an older cached passage. Text preview is inert plain text. Model/load/file errors preserve the query and re-enable controls; Words only can search an existing index without model assets.

## Model comparison and weak matches

Two isolated indexes used the same ten synthetic documents, 50 present-target development queries and 20 absent-target probes. MiniLM uses masked mean pooling; BGE uses CLS pooling and the recommended query instruction. Both run normalized embeddings on CPU with local assets, no custom remote code and verified file hashes. Exact identities are recorded in [model-comparison.json](model-comparison.json) and [BGE assets](bge-model-assets.json).

| Development result | MiniLM | BGE small English v1.5 |
| --- | ---: | ---: |
| Raw hybrid top-1 | 88% | 92% |
| Raw hybrid HitRate@5 | 98% | 98% |
| Assets | 91,617,680 bytes | 134,505,816 bytes |
| Present queries retained at fitted threshold | 44/50 | 40/50 |
| Absent queries rejected at fitted threshold | 19/20 | 20/20 |

Thresholds maximize balanced query-presence accuracy on these development labels, breaking ties toward more absent-query rejection. They decide whether to show candidates; they do not establish that the top-ranked candidate is correct. The raw ranking values above are before rejection, and therefore differ from gated end-to-end success. Six MiniLM and ten BGE present-target queries fall below the fitted thresholds. This is why Show weaker matches is an explicit recovery control. One absent MiniLM probe passes the gate.

MiniLM remains the desktop default: it preserves compatible existing indexes, has smaller assets, and retains more valid descriptions at the fitted gate. BGE is available as an explicitly selected experimental adapter with a separate database; the app will not silently migrate or mix model vectors. No universal model-superiority claim follows from ten documents. CPU worker threads are bounded to four for the desktop runtime; earlier raw timing samples are retained in the report rather than advertised as final GUI timings.

The threshold config is pinned to the complete model/revision/pooling identity. Missing or incompatible calibration produces explicitly labeled candidate mode. The UI hides all candidates when no strong match is found unless the user enables Show weaker matches; candidates shown below threshold are labeled Weaker match. Literal/filename-only search is explicitly identified and bypasses semantic gating. Similarity is never displayed as a confidence percentage.

The corpus and queries are author-generated development data. A frozen heldout set, consented user tasks, ambiguous multi-relevant queries, larger corpora and broader absent-target tests remain necessary. The fitted rejection rates are not release guarantees.

## Verification and limits

Thirteen lifecycle/retrieval tests passed; one link test was skipped because this host cannot create symlinks. The real-model offscreen GUI verification passed folder selection, responsive background preparation, semantic PDF evidence, safe action dispatch/copy, wide/narrow light/dark and larger-text screens, Ctrl+K/Enter/list-arrow controls, cancellation, weak-match recovery, stale-open rejection, restart, missing-model recovery and folder revocation while work runs. Screenshots were visually inspected after loading installed Segoe UI fonts for the offscreen plugin; final action controls stayed visible at 1180×780 and 720×900, including Larger text. No fonts are redistributed in the repository.

The Python socket guard recorded zero connection attempts in the tested GUI operations; it tests only participating Python operations, not all native processes or OS egress. Offscreen Qt controls can verify runtime transitions and render screens; they do not verify manual Windows interactions, screen readers, native permission/picker behavior, or external viewer/Explorer behavior. These limitations are recorded with the automated [GUI report](gui-verification.json).

Process termination, actual junction boundaries, concurrent-refresh protection and synthetic index cleanup have since passed their scoped tests; see the later reliability/containment notes. Native PDF viewing, packaging/installer, OCR and complete OS egress/cleanup audits remain pending. No personal folders were scanned during automated verification.

References: [BGE model card, pooling and query-prefix guidance](https://huggingface.co/BAAI/bge-small-en-v1.5), [Qt worker threads](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html), [Qt folder dialog](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QFileDialog.html).
