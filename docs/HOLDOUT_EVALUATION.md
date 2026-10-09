# Frozen synthetic holdout evaluation

October 10, 2026. The current hybrid weak-match gate misses the plan's 85% Recall@5 target on this holdout: raw hybrid retrieval reaches 100%, while the unchanged gate reduces it to 84%. This is an observed prototype limitation, not a release pass.

## Freeze and method

Twenty new author-created documents across two explicit roots, including duplicate basenames, digital PDF/TXT/MD, nearby topics and distinct identifiers. Fifty relevant-target queries contain 20 paraphrases, 20 identifiers, five queries with two relevant files and five folder/type-filtered queries. Twenty additional queries have no relevant file. No query text is reused from the development fixture. Labels were authored before running the model, not chosen from its winners.

The corpus, current policy and retrieval/model/extraction source identities were committed in [d33fe09](https://github.com/zekurou1/appbuildersph-hackathon-2026/commit/d33fe09) before the first evaluation. The [freeze manifest](../fixtures/holdout-v1.freeze.json) uses SHA-256 with CRLF normalized to LF. The runner checks those hashes before and after evaluation and refuses changed inputs/implementation. No threshold, model, ranking or relevance label was changed in response to this run. This set is held out from the earlier development tuning, but is not independent, blinded or consented-user validation.

Each method receives the same query/filters and returns at most five distinct files. Recall@5 measures the fraction of all labeled relevant files found, while HitRate@5 measures whether any was found. MRR uses the first relevant result. Fifty queries are timed three times per method, after one hybrid-policy warm-up. Evidence and original-file authorization are checked on every returned result; timings exclude that evaluator-only extra check. Timing order is fixed by method, with shared process/OS caches, so small method differences are not a randomized latency experiment.

## Results

| Method | Top-1 | HitRate@5 | Recall@5 | MRR@5 | Warm p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Filename | 2% | 8% | 8% | 0.039 | 65 ms |
| Words only | 90% | 100% | 100% | 0.939 | 69 ms |
| Semantic | 94% | 98% | 98% | 0.960 | 92 ms |
| Raw hybrid | 100% | 100% | 100% | 1.000 | 98 ms |
| Hybrid with existing weak gate | 84% | 84% | 84% | 0.840 | 174 ms |

The gate retains all 20 paraphrases, all five filtered queries and all five multi-relevant queries, but hides eight of the 20 exact-identifier searches. Raw hybrid ranks the correct identifier document first in all eight cases. Words only retrieves them; the current semantic similarity threshold incorrectly suppresses them in Meaning + words mode. The existing Show weaker matches option remains another recovery path. Future deterministic exact-match handling should be tested with new development examples and a new holdout rather than retuning on these labels.

Eighteen of 20 absent queries are rejected (90%). The gate accepts “community basketball tournament fixture list” and “piano tuning appointment and service quote” even though neither target exists. Returned passages still require source verification; a passed gate is not confidence or proof that the target exists.

The fixture deliberately uses uninformative filenames, so its poor filename score does not establish a general advantage over well-named personal files. All documents are short enough to produce one chunk each; long-document retrieval is covered by other functional tests, not this holdout.

## Device and cost

Windows 11 build 26200, Python 3.12.15, SQLite 3.53.1, AMD64 Family 25 Model 80 processor, 12 logical CPUs and 16,504,397,824 bytes RAM. Pinned MiniLM runs on CPU with four model threads. Model initialization takes 14.03 seconds, indexing takes 6.04 seconds and the first hybrid-policy request takes 161 ms. This is a new process, not a machine-cold cache measurement.

The corpus is 14,890 bytes, eight PDF pages and 20 chunks; the index is 122,880 bytes. Sampled peak evaluator-plus-descendant RSS is 489,172,992 bytes (about 466.5 MiB), including model initialization/extraction. Samples target 20 ms intervals; shared pages may be counted twice and short peaks missed. This is a small-corpus observation, not proof of 50 GB support, minimum RAM, or hard peak-memory bounds for the model/UI.

Participating Python socket guards observed zero connection attempts. This is not an OS/process-tree egress audit. No personal folders were scanned. Synthetic generated files, databases and raw runtime paths remain ignored by Git; the public [report](holdout-evaluation.json) contains synthetic query labels, document IDs and device metrics, not personal paths.

## Reproduce and remaining gates

```powershell
& '.venv\Scripts\python.exe' scripts/evaluate_holdout.py
& '.venv\Scripts\python.exe' -m unittest tests.test_holdout -v
```

Use the implementation commit accompanying this report. Future core/policy edits intentionally fail the v1 freeze check; do not replace its hashes to advertise a new run as the original holdout. Keep it as historical/regression evidence and author a new frozen evaluation set for changed retrieval.

The warm-latency target passes only on this small host corpus; the current gated recall target does not. Clean installation, OS egress, native usability, consenting users, broader corpora, languages and OCR remain unverified. WP6 remains partial.
