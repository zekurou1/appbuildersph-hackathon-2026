# English screenshot OCR

PNG, JPG and JPEG now use installed `Windows.Media.Ocr` (English `en-US`) inside the existing Windows Job Object parser. The text then passes through the pinned local MiniLM tokenizer and embedding model. Original files stay in their selected folders. No remote OCR or generated descriptions are used.

The preview explicitly says **OCR-recognized English text**. OCR can make transcription errors; Open original and Show in folder retain the same authorization/fingerprint checks. Image filters are available. Standalone identifier recovery searches the recognized text, so it cannot recover characters OCR misreads.

Inputs are limited to 20 MiB, four million pixels and a 6000-pixel longest edge. Animated, mismatched, corrupt, blank and oversized images fail explicitly. Parser timeout, cancellation, root revocation and the 256 MiB job limit still apply. Manual refresh reprocesses images even when bytes are unchanged because Windows manages OCR language components separately from our pinned MiniLM assets.

## Verified evidence

Windows 11 build 26200, PyWinRT bindings 3.2.1, installed English OCR. The real contained worker recognized the schedule screenshot. Desktop Qt controls then found it through a paraphrased question using real CPU MiniLM, recovered `SCH-642`, showed the OCR label and authorized the original path. This is offscreen automation, not manual native viewer or accessibility validation.

[OCR verification](ocr-verification.json) records six clean synthetic PNG/JPEG images with authored labels and hashes written before evaluation. Reports include exact transcription comparisons, gated hybrid top-five retrieval, similar receipt codes and absent codes. These are small author-created tests, not independent user or general OCR accuracy evidence. No policy or ranking tuning occurred during the run.

The suite now executes 35 passing tests and skips one symbolic-link test. New tests use the actual installed OCR and cover indexing, filtering, restart, root removal preserving originals, blank/corrupt/oversized failure states. Test fixture embeddings verify storage only; the desktop and OCR evaluation scripts use real MiniLM.

## Setup and release limits

`uv sync --locked` installs Windows-only WinRT projections. Windows must already provide the English OCR language component. Missing runtime/language and recognition failures produce explicit file errors; there is no automatic language/model download. A Tesseract wheel was tested but a native dependency was blocked by Application Control; it was removed from dependencies and no security policy was changed.

Microsoft documents [Windows OCR](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr?view=winrt-26100) support for desktop applications with package identity. Recognition succeeded in this current Python environment, but that does not establish supported distribution to arbitrary unpackaged machines. A packaged deployment and clean-machine OCR test remain release gates. Bindings follow [PyWinRT namespace packaging](https://pywinrt.readthedocs.io/en/stable/api/windows.html); OS-managed OCR weights have no separate project-controlled weight hash.

Scanned PDF OCR, handwriting, multilingual text, rotated/low-contrast images and visual understanding remain outside verified scope. The evaluator's Python socket guard does not audit native OCR or all process-tree network traffic.

Reproduce:

```powershell
& '.venv/Scripts/python.exe' -m unittest tests.test_core tests.test_recovery tests.test_worker tests.test_holdout tests.test_identifiers tests.test_ocr -v
& '.venv/Scripts/python.exe' scripts/verify_gui.py
& '.venv/Scripts/python.exe' scripts/verify_ocr.py
```
