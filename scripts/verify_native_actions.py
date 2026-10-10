"""Invoke authorized native file actions on one uniquely named synthetic original."""
import ctypes
import hashlib
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from omnifind.core import Index
from omnifind.gui import Window
from tests.test_core import StorageEmbedder


def main():
    app = QApplication.instance() or QApplication([])
    assert app.platformName() == "windows"
    run = Path(f"reports/runtime/native-actions/omnifind-action-{time.time_ns()}").resolve()
    root = run / "omnifind-synthetic-action-folder"
    root.mkdir(parents=True)
    original = root / f"omnifind-synthetic-receipt-{time.time_ns()}.txt"
    original.write_text("Synthetic native action receipt ACT-483. No personal content.")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    database = run / "data/index.sqlite"
    index = Index(database, StorageEmbedder())
    try:
        rid = index.add_root(root)
        index.refresh(rid)
        result = index.search_response("ACT-483")["results"][0]
    finally:
        index.close()
    window = Window(database, Path("models/missing"))
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    def observed(needle):
        found = []
        @callback_type
        def callback(hwnd, _):
            title = ctypes.create_unicode_buffer(1024)
            user32.GetWindowTextW(hwnd, title, 1024)
            if needle in title.value:
                found.append(True)
            return True
        user32.EnumWindows(callback, 0)
        return bool(found)
    try:
        window.results = [result]
        window.select_result(0)
        window.act_on_file("open")
        open_error = window.last_error
        deadline = time.monotonic() + 15
        while not observed(original.stem) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.1)
        viewer_observed = observed(original.stem)
        window.act_on_file("reveal")
        deadline = time.monotonic() + 10
        while not observed(root.name) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.1)
        report = {"platform": app.platformName(), "open_dispatch_without_error": open_error is None,
                  "original_filename_observed_in_native_window": viewer_observed,
                  "folder_name_observed_in_native_window": observed(root.name),
                  "original_bytes_preserved": hashlib.sha256(original.read_bytes()).hexdigest() == digest,
                  "limits": ["Native dispatch and uniquely named window titles, not independent human confirmation of viewer content or Explorer selection",
                             "Synthetic viewer/Explorer windows left open to avoid closing reused user windows"]}
        (run.parent / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        assert report["open_dispatch_without_error"] and report["original_filename_observed_in_native_window"]
        assert report["folder_name_observed_in_native_window"] and report["original_bytes_preserved"]
    finally:
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
