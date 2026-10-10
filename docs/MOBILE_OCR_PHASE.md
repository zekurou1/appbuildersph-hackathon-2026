# Phone-local screenshot OCR

The Android tier adds English readable-text recognition for upright PNG/JPEG files in explicitly selected phone subfolders. It uses the standard single-threaded Tesseract4Android 4.9.0 runtime (Tesseract 5.5.1) and the `tessdata_fast` English LSTM model at revision `87416418657359cb625c412a48b6e1d6d41c29bd`.

## Build and data path

From the repository root, run `.venv/Scripts/python.exe scripts/prepare_mobile_ocr.py`. This downloads public data/notices to build assets and writes `ocr-manifest.json`; the 4,113,088-byte model is ignored by Git. Its SHA-256 is `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. Gradle verifies the pinned native AAR checksum before compiling. No app model-download path, service, metrics SDK or cloud fallback was added. The release manifest continues to remove Internet/network-state permissions. Debug builds retain Flutter's development connection permission.

On first OCR use, the model is verified and copied to app-private `files/ocr/tessdata`; this is a public model, not indexed content. Native OCR runs on the existing serial worker. The bitmap and Tesseract page state are released after each extraction; the engine is released when the index closes. No source-image copy or thumbnail is stored by this extractor. Recognized text, source line numbers and pixel regions are persisted with embeddings in the existing app-private SQLite index. Schema version 3 adds provenance columns and preserves existing text/PDF passages. Removing a root removes these derivatives and releases its grant while retaining original files and public models.

## Scope and evidence

Image results explicitly say `OCR line`; details say `Recognized image text` and warn that OCR can misread words and codes. Text search uses the recognized passage, not an invented caption. `Open original` rechecks source bytes and launches the provider URI deliberately. Stored bounding regions refer to the original upright image pixels; image highlighting is not implemented in this phase.

The compressed-byte limit remains 1 MiB. PNG/JPEG headers are validated before decoding; the decoded bound is 4 million pixels, and OCR output is bounded to 100,000 characters and 2,000 source passages. Blank, corrupt, oversized and rotated/mirrored JPEG files receive explicit issue codes. JPEGs with EXIF orientation other than normal/undefined are rejected; PNG orientation metadata is not interpreted. Users should choose upright screenshots.

Recognition uses a blocking native call. Cancellation is checked before/after it and before committing any passage; no partial canceled image revision is exposed. Native calls are not isolated in a killable process or bounded by a hard timeout. Those controls, hostile decoder/parser inputs, physical-phone memory/thermal behavior, handwriting, complicated tables, rotation and multilingual quality remain release work. OCR is not general object/scene understanding, and synthetic examples are not a retrieval benchmark.

## Reproduce

The release APK was exercised on the Android 17/API 37 x86_64 emulator with airplane mode enabled and Wi-Fi disabled before first-use OCR indexing. Three files were searchable; a blank PNG and corrupt PNG produced distinct issues. Meaning search returned both recognized images, OCR detail and its warning were inspected, and the original PNG was visually checked in the native viewer. Exact code search worked after force-stopping and restarting OmniFind without a refresh. Scope removal cleared matches while all five original hashes matched the synthetic corpus. Airplane mode and Wi-Fi were restored to their previous settings. Five Flutter widget tests and fourteen native instrumented tests passed; Flutter analysis found no issues. These are builder observations on synthetic inputs, not physical-phone or independent-user acceptance. See [recorded flow evidence](mobile-ocr-verification.json) and [artifact checks](mobile-artifact-verification.json).

Prepare MiniLM and OCR public assets, then run `flutter analyze`, `flutter test` and `./android/gradlew.bat -p android connectedDebugAndroidTest` inside `mobile`. Build with `flutter build apk --release`, then run `.venv/Scripts/python.exe scripts/verify_mobile_artifact.py` from the repository root to check bundled assets, native architectures, notices and privacy configuration.

`.venv/Scripts/python.exe scripts/prepare_mobile_ocr_probe.py` creates only synthetic probe files under `reports/runtime/mobile-ocr-corpus`. It does not read personal images or use any PharmaSync asset. Copy that folder into a dedicated emulator Documents subfolder, select it through the app's system picker and Refresh. Search by meaning or by `PKG-483`, inspect OCR evidence, open the original, restart, and remove the selected scope. External viewers have their own data behavior; a manifest check is not an OS/service egress audit.

Runtime/model references: [Tesseract4Android release and API](https://github.com/adaptech-cz/Tesseract4Android/tree/4.9.0), [pinned English model](https://github.com/tesseract-ocr/tessdata_fast/tree/87416418657359cb625c412a48b6e1d6d41c29bd). The APK includes Apache licenses for the wrapper, engine and model, Leptonica's notice, libpng's license and libjpeg's notice. These are bundled notices, not a complete legal certification or native SBOM.
