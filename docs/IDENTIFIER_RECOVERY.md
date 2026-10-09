# Exact-identifier recovery

October 10, 2026. Meaning + words now treats a standalone alphanumeric code as an exact source-text lookup. The original holdout's eight hidden codes are recovered without changing model assets, similarity thresholds or raw semantic ranking.

## User-visible behavior

Enter `INV-2048`, `ABC42`, `ITEM_471` or `QXZ.471` in Meaning + words. A recognized code contains letters and digits, is a single token of at most 128 characters, and can contain underscores, hyphens or periods. Matching is case-insensitive but retains punctuation: `QXZ-471` does not match `QXZ.471`, `QXZ-4710` or `PRE-QXZ-471-ALT`. Sentence punctuation after a complete code is allowed.

The result displays an original passage containing the exact code and explicitly says meaning scoring is not used. It has no similarity/confidence score. Matches in multiple eligible files remain separate files. An absent code returns no result, even with Show weaker matches enabled; the app does not substitute a semantically similar or near-identical identifier. Folder/type filters, root authorization, freshness and expected-revision checks still apply.

Standalone code lookup works on committed content without loading a model, including in the CLI and desktop. Indexing and ordinary descriptions still require the local model. Plain numbers, quoted phrases and prose such as `find INV-2048` keep their existing search-mode behavior. This is a deliberately narrow literal route, not a claim of meaningful model inference for code lookup.

## Verification

Thirty-three tests passed; one symlink test skipped. Four new tests use a new synthetic code family rather than the old holdout labels. They check semantic-gate independence, punctuation/prefix boundaries, absent codes, missing models, root/type filters, stale originals, removal and prose retaining its semantic contract. Real-model offscreen desktop verification also passes ordinary semantic PDF retrieval and exact/absent codes with a missing model directory. CLI checks retrieve the indexed synthetic PDF with `WTR-612` and reject `WTR-999` using a missing model directory.

The original [frozen holdout report](HOLDOUT_EVALUATION.md) and freeze hashes are unchanged. An explicit regression run reuses those 50 relevant queries and 20 absent targets after the fix:

| Observation | Original frozen run | Regression after code fix |
| --- | ---: | ---: |
| Hybrid-policy Top-1 | 42/50 | 50/50 |
| Hybrid-policy HitRate@5 | 42/50 | 50/50 |
| Macro Recall@5 | 84% | 100% |
| Identifier queries recovered | 12/20 | 20/20 |
| Absent targets rejected | 18/20 | 18/20 |

This is regression reuse, **not new held-out validation or a release pass**. The two semantic absent-query false accepts remain unchanged. See [regression report](identifier-regression.json), whose metadata records reuse and the changed implementation hash. During the beginning of this run, lifecycle/GUI checks ran concurrently on the same host; timing samples are retained for traceability, not used to claim a performance improvement over the original run.

```powershell
& '.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.venv\Scripts\python.exe' scripts/verify_gui.py
& '.venv\Scripts\python.exe' scripts/evaluate_holdout.py --regression
```

Default evaluation still rejects changed frozen implementation. Regression mode allows changed `omnifind/` source only, requires unchanged corpus/policy and checks that implementation hashes stay stable during the run. Its default output directory is separate from the historical holdout output. No new OCR/mobile functionality or cloud inference is introduced.

Next gates remain fresh held-out validation of the changed retrieval policy, screenshot OCR, OS-level egress, native usability and clean-machine packaging.
