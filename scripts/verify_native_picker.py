"""Exercise the actual Windows folder dialog on a synthetic directory only."""
import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QFileDialog


def main():
    app = QApplication.instance() or QApplication([])
    assert app.platformName() == "windows", "Native Windows platform required"
    root = Path("reports/runtime/native-picker/synthetic-folder").resolve()
    root.mkdir(parents=True, exist_ok=True)
    title = "OmniFind synthetic release folder test"
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    observed = []
    stopped = threading.Event()
    def control():
        deadline = time.monotonic() + 20
        while not stopped.is_set() and time.monotonic() < deadline:
            @callback_type
            def inspect(hwnd, _):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value != os.getpid():
                    return True
                text, klass = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, text, 256)
                user32.GetClassNameW(hwnd, klass, 256)
                if text.value == title and klass.value == "#32770":
                    observed.append("Windows common folder dialog")
                    # IDOK for this process's uniquely titled test dialog only.
                    user32.PostMessageW(hwnd, 0x0111, 1, 0)
                return True
            user32.EnumWindows(inspect, 0)
            time.sleep(.1)
    thread = threading.Thread(target=control, daemon=True)
    thread.start()
    selected = QFileDialog.getExistingDirectory(None, title, str(root), QFileDialog.Option.ShowDirsOnly)
    stopped.set()
    thread.join(1)
    report = {"platform": app.platformName(), "native_dialog_observed": bool(observed),
              "synthetic_folder_selected": bool(selected) and Path(selected).resolve() == root,
              "limits": ["Programmatic Windows IDOK acceptance of preset synthetic folder, not manual usability validation"]}
    (root.parent / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    assert report["native_dialog_observed"] and report["synthetic_folder_selected"]


if __name__ == "__main__":
    main()
