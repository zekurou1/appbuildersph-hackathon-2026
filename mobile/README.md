# OmniFind Local for Android

Phone-local selected-folder indexing and search. Flutter UI, Android Storage Access Framework, app-private SQLite and bundled MiniLM/ONNX Runtime CPU inference. No desktop server or cloud fallback.

Start with the [mobile implementation and verification guide](../docs/MOBILE_PHASE.md). Download checksum-pinned public build assets from the repository root with `.venv/Scripts/python.exe scripts/prepare_mobile_model.py`, then run `flutter build apk --release` here. The pilot is debug-signed even in the release build; it is not a Play Store distribution.

Choose a phone subfolder through the system picker, then Refresh. The first tier supports English UTF-8 text and Markdown. PDF and screenshot OCR are not yet ported from Windows. Original files remain untouched when removing a folder.

The release manifest removes Internet/network-state permissions and ONNX Runtime's automatic telemetry provider. Debug builds keep Flutter's development connection permission. Bundled model assets have no in-app download path. Physical-phone and independent user validation remain necessary.
