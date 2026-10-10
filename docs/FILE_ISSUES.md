# File issues and recovery

Folders now has **Review file issues** for the selected root. It lists failed, unsupported, pending, stale, missing and unavailable records with recovery guidance. Healthy searchable files are omitted. This explains partial coverage without requiring users to inspect the SQLite index or raw parser errors.

The view loads at most 100 issues per page; **Show more** continues by file ID. Messages cover missing English OCR, unreadable/blank/oversized images, encrypted or scanned PDFs, parser limits and unavailable originals. Unsupported formats remain explicitly unsupported. Refresh is a deliberate separate action; reviewing issues does not download assets, run inference, modify originals or invoke a viewer.

Records come from the existing local index and freshness checks. A new failure or file may remain unknown until manual refresh. Missing/stale states reuse the same checks as coverage; this view is not a background watcher. There is no new issue/history cache. Root removal and clear-index delete existing file records; privacy invalidation closes the dialog and clears its rows across windows. Closing the parent also clears the dialog.

## CLI

```powershell
& '.venv/Scripts/python.exe' -m omnifind issues --folder 1
& '.venv/Scripts/python.exe' -m omnifind issues --folder 1 --limit 100 --after 123
```

Use the selected root ID and `next_after_id` from the previous page, not the illustrative values above. Without `--folder`, the CLI reviews all selected roots. The command returns paths and recovery guidance explicitly requested by the user; it requires no model. It does not print extracted source text. Invalid limits/cursors fail without a traceback.

## Verification

On the existing Windows host, all 40 executed tests passed; one symbolic-link test was skipped. New tests cover persistence without a model, root filtering/removal, cursor paging without duplicates, healthy-file omission, stale/missing reconciliation and recovery messages that do not render arbitrary parser text.

Offscreen desktop verification indexes three valid synthetic files and three issue fixtures, reviews the broken PNG/unsupported file explanations, preserves real PDF and screenshot search, and verifies another window's root removal closes the issue dialog and clears previews. The real CLI was also tested against a synthetic unsupported file with a nonexistent model directory. See [desktop verification](gui-verification.json).

These are same-host synthetic checks. Native picker/viewer usability, screen-reader use, another-machine installation and large-corpus responsiveness remain unverified.
