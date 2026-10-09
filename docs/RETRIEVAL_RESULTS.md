# Retrieval development results

Measured October 10, 2026 (Asia/Manila). This is a small synthetic development evaluation, not production accuracy or a held-out result.

Environment: Python 3.12.15, Windows 11 build 26200, about 16.5 GB RAM, CPU PyTorch 2.14.1 / Transformers 5.19.0. MiniLM revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, direct attention-mask mean pooling and L2 normalization. Model setup uses 91,617,680 bytes of assets.

Ten synthetic digital PDF/TXT/MD documents, 50 author-labeled present-target development queries, and five absent-target probes. Document names are deliberately unhelpful. Labels are fixed in [development.json](../fixtures/development.json); some text shares exact query terms, so this corpus cannot establish broad real-world performance.

| Search mode | Top-1 | HitRate@5 | MRR@5 | Observed p95 query time |
| --- | ---: | ---: | ---: | ---: |
| Filename | 0% | 6% | 0.027 | 24 ms |
| Lexical | 92% | 96% | 0.940 | 25 ms |
| Semantic | 84% | 100% | 0.913 | 46 ms |
| Hybrid | 88% | 98% | 0.925 | 52 ms |

Each query has one labeled relevant file, so HitRate@5 equals Recall@5 on this dataset only. MRR is truncated at five. Timing includes core query work and source freshness checks with the model already loaded; it excludes GUI and source-open time. These are 50 timing samples per mode with no dedicated warm-up, not a standardized performance benchmark. Model cold load in the final run was 12.56 seconds; initial indexing was 2.44 seconds. No peak-memory measurement or large-corpus capacity claim is made.

Lexical search beats hybrid top-1 here. Semantic finds both targets missed by lexical in the top five; hybrid misses one target. Retain all modes and improve evidence/ranking using broader development data before claiming hybrid superiority. These initial WP2 results preceded the BGE comparison and weak-match gate; see [the later desktop-phase report](DESKTOP_PHASE.md) for those results. A frozen heldout evaluation remains pending.

All five absent-target probes returned five hybrid candidates. There is no calibrated rejection threshold yet: results are candidates requiring source verification. This is a release gap, not successful absent-target recognition.

The real-model evaluation also indexed a new synthetic library note after setup, retrieved it using a new query, restarted the index and retrieved it again, removed its root, and confirmed search exclusion while preserving originals. Python socket guards recorded zero connection attempts. This proves the tested Python operations worked with those connections blocked; it is not an OS-wide or native-process egress audit. Screenshot OCR was not run.

The lifecycle suite ran 11 tests: 10 passed and one symbolic-link test was skipped because this host cannot create symlinks. Passed checks include exact identifier/quoted phrase behavior, stale exclusion, refresh/delete, persistence, lexical recovery without model assets, file-type filtering before truncation, grouping long-file chunks, corrupt/unsupported files, scope rejection, incompatible model identity, transaction fault rollback, and root revocation during indexing/querying. Those lifecycle tests use deterministic fixture embeddings; local-AI proof comes from the separate real-model spike/evaluation. Actual junction escapes, process termination, concurrent refresh, memory limits and broader cleanup tests remain.

Machine-readable artifacts: [WP1 report](wp1-report.json), [retrieval report with per-query observations](retrieval-evaluation.json), [model asset manifest](model-assets.json). Reproduce with the README commands; no personal folders are scanned by the evaluation.

Implementation reference: [MiniLM's official mean-pooling recipe](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
