# Phone-local Android tier

Architecture accepted October 10, 2026: the user chose an Android app that indexes and searches files stored on the phone. This adds a phone-local application under `mobile/`; the Windows baseline and original master plan remain unchanged. There is no desktop companion, pairing service or cloud fallback.

Flutter supplies Search/Folders/Settings and full-screen source details. Kotlin handles Android's native folder picker, read-only persisted grants, app-private SQLite, freshness checks, deliberate native Open and CPU ONNX Runtime. The bundled public MiniLM ONNX model is pinned separately from the desktop model and checksum-verified before loading; model/runtime downloads happen on the build machine, not implicitly inside the app. ONNX Runtime telemetry is disabled, its automatic Android initializer is removed, and release builds remove Internet/network-state permissions injected by that dependency. Debug builds retain Flutter's development connection permission.

Only the Android external-storage document provider is accepted. Cloud providers and unrestricted storage permissions are excluded. Android's folder-picker restrictions still apply: choose a permitted subfolder, not a promise to scan every phone file. The index stores plaintext source passages and vectors; Android backup is disabled. A user-invoked external viewer has its own data behavior.

## Current format and lifecycle scope

The mobile tier supports English UTF-8 `.txt` and `.md`, English upright PNG/JPEG OCR, plus digital PDF text on Android 15/API 35 or newer. Native `PdfRenderer.Page.getTextContents()` extracts page text without an added third-party parser or network dependency. Older Android versions retain TXT/MD and image OCR and report PDFs as requiring Android 15+. Scanned PDFs remain unsupported. Folder cards show issue reasons, including unreadable/password-protected PDFs, no extractable text, exceeded PDF/image bounds and unsupported JPEG orientation. Indexing runs off the UI thread, can be canceled between bounded operations and commits each file transactionally. Refresh reconciles deletions only after a complete scan. Search and Open recheck original bytes and restored grants. Removing a folder deletes its derivatives and releases the grant while preserving originals. Returning from another app clears displayed evidence and reloads scope.

[Screenshot OCR](MOBILE_OCR_PHASE.md) uses a pinned Tesseract4Android runtime and bundled English model, with native/model checksum verification and license notices. OCR evidence is labeled recognized text and includes persisted original-pixel regions. Bounds are 4 million pixels and 100,000 recognized characters per image, within the existing 1 MiB byte limit. No source-image copy is persisted by extraction. Recognition is a blocking native call; cancellation is checked before/after it and before commit, while process isolation and a hard timeout remain release work.

PDFs retain page numbers and line numbers within extracted page text; these are not visual row coordinates. Existing text indexes migrate by adding a nullable page column. PDF staging is limited to the existing 1 MiB byte bound in a dedicated app-private cache directory. Temporary copies are removed in `finally` and crash leftovers on index initialization. Bounds are 20 pages and 100,000 extracted characters per PDF. Native parsing is in-process; cancellation cannot interrupt a single parser call. Parser-process isolation and hostile-input timing remain release work. Query editing is disabled during search; switching search modes clears the previous results.

Pilot bounds are 200 files per root, 1 MiB per file, 20 MiB of supported source bytes per refresh and 12 nested levels. Source chunks are up to 300 characters with 60-character overlap, with tokenizer budget validation; source line/page numbers are preserved. This differs from desktop token-based chunking and needs a mobile-specific quality evaluation. Mean-pooled normalized 384-dimensional embeddings combine with literal matching. The experimental `.25` match threshold is not a calibrated phone accuracy claim. Literal code and Words-only search can use the committed index without loading the model.

## Reproduce

From the repository root:

```powershell
.venv/Scripts/python.exe scripts/prepare_mobile_model.py
.venv/Scripts/python.exe scripts/prepare_mobile_ocr.py
.venv/Scripts/python.exe -m scripts.prepare_mobile_reference
cd mobile
flutter analyze
flutter test
flutter build apk --debug
./android/gradlew.bat -p android connectedDebugAndroidTest
```

`prepare_mobile_model.py` downloads only two pinned public assets (about 90.6 MB), validates hashes and creates the tracked provenance manifest. Weights stay ignored. Android dependencies and licenses must be available through the normal SDK setup. Build configuration currently uses debug signing for pilot artifacts; it is not a store release.

The Windows host has Flutter 3.47.7, Dart 3.13.5, Android SDK 36 and a running Android 17/API 37 x86_64 emulator. Five widget checks cover folder removal/query preservation, known-stale preview clearing, doubled-text scrolling, in-flight query locking, PDF page evidence, search-mode invalidation and OCR evidence labeling/warnings. Fourteen native instrumented tests passed: SQLite startup/root listing, four English tokenizer/vector parity fixtures against desktop (cosine greater than .999), native two-page PDF extraction and semantic page preference, malformed/blank PDFs, page bounds, cancellation cleanup, original TXT/MD line numbers, version-1/version-2 index migrations preserving text and PDF pages, PNG/JPEG OCR, source pixel regions, recognized semantic passage preference, blank/corrupt images, pre-OCR pixel limits and cancellation without partial image evidence. These tests do not establish general tokenizer or retrieval quality.

The actual release UI selected a synthetic phone subfolder, indexed two TXT/MD originals and found the rental agreement from a paraphrased query. Source line evidence displayed; an exact code survived restart/update. A deliberately changed synthetic original was excluded from search and rejected by Open. After restoring that test edit and removing the root, both original hashes matched, and the old code returned no results after a process restart. These are builder observations, not independent user acceptance. Actual external viewer contents were not verified. See [flow evidence](mobile-flow-verification.json) and [APK/native-test verification](mobile-artifact-verification.json).

The digital-PDF release flow then selected a separate four-file synthetic folder: PDF and Markdown were searchable while blank and malformed PDFs displayed separate issue reasons. A paraphrased rental query returned page 2 of `unrelated.pdf`; the detail and native PDF viewer both displayed the actual passage. Returning cleared old results. The PDF code survived a process restart without refresh. Removing that root excluded the code, and all four original hashes were preserved. See [PDF flow evidence and limits](mobile-pdf-verification.json). Generate fresh probe originals with `.venv/Scripts/python.exe scripts/prepare_mobile_pdf_probe.py`; it writes only synthetic files under `reports/runtime/mobile-pdf-corpus`.

The screenshot-OCR release flow ran with airplane mode enabled and Wi-Fi disabled before first use. Two image originals and Markdown were searchable; blank and corrupt images displayed distinct issue reasons. A paraphrased query found both images, details labeled recognized text and warned about OCR errors, and the native image viewer displayed the original PNG. Exact image-code search survived a process restart without refresh. Removing the root cleared matches, and all five original hashes were preserved. Emulator network settings were restored afterward. See [OCR flow evidence and limits](mobile-ocr-verification.json).

The universal release APK is 254,681,402 bytes (about 243 MiB) before ABI-specific packaging optimization. `scripts/verify_mobile_artifact.py` checks its embedded model hashes/notices, backup flag, removed telemetry initializer and absent Internet permission, and records its SHA-256. A manifest check is not a complete OS/service egress audit.

Physical Android hardware, low-memory recovery, Android provider edge cases, TalkBack, mobile holdout quality, battery/thermal measurements and a complete Android process-level privacy audit remain release gates.

Platform references: [Android PDF page text](https://developer.android.com/reference/android/graphics/pdf/PdfRenderer.Page#getTextContents()), [Android document access](https://developer.android.com/training/data-storage/shared/documents-files), [Flutter platform channels](https://docs.flutter.dev/platform-integration/platform-channels), [ONNX Runtime Android installation](https://onnxruntime.ai/docs/install/), [pinned public ONNX model](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/10dbd2f06a8baf40ad285b037edda610c1b9a57c/onnx/model.onnx).
