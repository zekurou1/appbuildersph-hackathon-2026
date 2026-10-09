# Locked environment reproduction

A separate `.tools/clean-check` virtual environment was created with `uv sync --locked`. It passed the complete three-file desktop verification, including real CPU MiniLM PDF/screenshot search, OCR evidence, exact codes, restart, clear, stale-source rejection and cross-window revocation.

An offline dependency recreation was attempted first. The available caches did not contain every locked package, so recreation needed explicit public dependency downloads. This is installation, not an inference network requirement. It is a fresh virtual environment on the same Windows host, using existing verified model assets and installed OS OCR components; it is not a clean-machine or supported packaged deployment test.

The reusable readiness check makes no downloads or OS configuration changes:

```powershell
& '.venv/Scripts/python.exe' scripts/check_setup.py
```

It checks SQLite FTS/secure-delete support, imports the Qt runtime, verifies model checksums and actual local inference, reports the Windows OCR language/binding and recognizes a synthetic image inside the bounded worker. It emits no personal source paths or tracebacks and returns a failure exit code if readiness fails. See [setup result](setup-verification.json).

Release gates still include package identity for Windows OCR, another-machine installation, manual native picker/viewer and accessibility checks, consented real files, and full OS/process-tree egress inspection. No installer or clean-machine certification is claimed.
