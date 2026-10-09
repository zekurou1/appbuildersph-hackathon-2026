# Parser containment and cross-window privacy

October 10, 2026. Windows CPU prototype; this increment closes parser lifecycle and cached-preview gaps, not the entire WP5 gate.

## Implemented boundary

Extraction is supervised by an unnamed Windows Job Object. The child waits for a stdin handshake before importing the parser; the supervisor sends that handshake only after assignment succeeds. Failed setup is reported as a failed file, with no unrestricted fallback. A parser job allows at most two processes to accommodate the installed uv interpreter trampoline plus Python. Both per-process and aggregate committed memory are limited to 256 MiB. Job handles are not inherited. Closing the supervisor's final handle kills remaining job members, including when the supervisor is forcibly terminated.

The supervisor enforces a 20-second wall-clock deadline and a 16 MiB stdout ceiling. Reader threads drain stdout into bounded memory and discard stderr rather than logging or accumulating it. No extracted-content temporary files are created. Cancellation and root authorization are checked between approximately 20 ms polling waits; cancel/removal kills an active extraction job and rejects its output. Inference cancellation still waits for the current model call. These limits do not cap the desktop/model process, do not replace Windows permissions, and do not sandbox filesystem or network access.

The implementation follows Microsoft's [job assignment and nested-job requirements](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject) and [extended limit structure](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information). No firewall, Application Control or administrator policy was changed. Indexing now explicitly rejects non-Windows hosts until an equivalent containment implementation is available; it does not silently remove resource limits.

## Cached evidence revocation

Remove-folder and clear-index atomically advance a persistent privacy epoch. Each open desktop window polls that epoch through a read-only SQLite connection every 250 ms. A changed epoch clears displayed passages/results, disables file actions, preserves the query, cancels obsolete work and refreshes selected folders. Search-result delivery and file actions also check the epoch. Polling is eventual, with timing dependent on the event loop and database locks; it is not a zero-delay cross-process notification. Previously copied clipboard content and OS/external artifacts remain outside this cleanup.

## Verification observed

Twenty-six passing tests, one skipped symlink test. Seven Windows containment tests pass:

- A sleeping actual Python worker is gone after timeout.
- A cancellation/revocation checkpoint kills the worker.
- A 512 MiB allocation is denied by a 128 MiB test ceiling.
- Oversized stdout fails without retaining an unbounded payload.
- Failed job assignment never starts the fault-probe module.
- Killing only the actual supervisor, without manually killing parser members, kills the parser.
- Removing a root during live supervised extraction leaves zero chunks and preserves the original.

Existing killed-transaction, restart, cleanup and real-junction tests also pass through the new worker path. The real MiniLM offscreen desktop verification passes digital PDF/TXT indexing, semantic source evidence, clear/rebuild and a second-window removal that clears the first window's preview/actions without further interaction. GUI verification observes zero participating Python socket-connect attempts. See [GUI report](gui-verification.json) and [containment report](containment-verification.json).

```powershell
& '.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.venv\Scripts\python.exe' scripts/verify_gui.py
```

## Next gates

OS-level attempted/successful egress collection for the complete inference/parser process tree is still unverified. No firewall-wide or machine-wide network settings were altered to simulate this. Clean-machine installation, native viewer/picker/screen-reader checks, low-storage recovery and a frozen holdout are also pending. The memory denial probe validates enforcement, not parser quality on every complex PDF or a supported corpus size. No OCR or screenshot support is introduced by this phase.
