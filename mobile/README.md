# OmniFind Local for Android

Phone-local selected-folder indexing and search. Flutter UI, Android Storage Access Framework, app-private SQLite and bundled MiniLM/ONNX Runtime CPU inference. No desktop server or cloud fallback.

Start with the [mobile implementation and verification guide](../docs/MOBILE_PHASE.md). Download checksum-pinned public build assets from the repository root with `.venv/Scripts/python.exe scripts/prepare_mobile_model.py`, then run `flutter build apk --release` here. The pilot is debug-signed even in the release build; it is not a Play Store distribution.

Choose a phone subfolder through the system picker, then Refresh. This tier supports English UTF-8 text and Markdown, plus native digital-PDF text extraction on Android 15+. PDF results show page numbers and extracted line numbers. Older Android versions retain TXT/MD search. Scanned PDFs and screenshot OCR remain unsupported. Original files remain untouched when removing a folder.

PDF pilot bounds: 1 MiB per file, 20 pages and 100,000 extracted characters. Temporary PDF bytes use an app-private cache directory, are deleted after extraction or cancellation, and crash leftovers are cleared on index initialization. Parsing runs on the native worker but is not isolated in a killable process; cancellation takes effect between native calls. Folder issues explain unreadable/password-protected PDFs, missing text and exceeded bounds.

The release manifest removes Internet/network-state permissions and ONNX Runtime's automatic telemetry provider. Debug builds keep Flutter's development connection permission. Bundled model assets have no in-app download path. Physical-phone and independent user validation remain necessary.
