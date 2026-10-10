"""Inspect native Qt accessibility interfaces; not a human screen-reader test."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QAccessible
from omnifind.gui import Window
from omnifind.core import Index
from tests.test_core import StorageEmbedder


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        window = Window(Path(temporary) / "data/index.sqlite", Path("models/minilm"))
        window.show()
        app.processEvents()
        rows = []
        try:
            for name, widget in [("query", window.query), ("search", window.search_button),
                ("type", window.type_filter), ("folders", window.folder_list),
                ("issues", window.issues_button), ("results", window.result_list),
                ("source_path", window.preview_path), ("evidence", window.preview),
                ("open", window.open_button), ("reveal", window.reveal_button),
                ("clear", window.clear_button)]:
                interface = QAccessible.queryAccessibleInterface(widget)
                assert interface is not None and interface.isValid(), name
                title = interface.text(QAccessible.Text.Name)
                assert title, f"Missing accessible name: {name}"
                rows.append({"control": name, "name": title, "role": str(interface.role()),
                             "disabled": interface.state().disabled})
            assert next(r for r in rows if r["control"] == "open")["disabled"]
            root = Path(temporary) / "corpus"
            root.mkdir()
            (root / "receipt.txt").write_text("Synthetic accessibility receipt ACC-483.")
            index = Index(window.database, StorageEmbedder())
            try:
                rid = index.add_root(root)
                index.refresh(rid)
                window.results = index.search_response("ACC-483")["results"]
            finally:
                index.close()
            window.select_result(0)
            interface = QAccessible.queryAccessibleInterface(window.preview)
            text_interface = interface.textInterface()
            assert text_interface is not None and text_interface.characterCount() > 0
            assert not QAccessible.queryAccessibleInterface(window.open_button).state().disabled
            report = {"platform": app.platformName(), "controls": rows,
                "populated_evidence_text_interface": True, "source_actions_enable_on_valid_result": True,
                "limits": ["Native Qt accessibility tree inspection, not Narrator/JAWS user validation",
                           "End-to-end keyboard checks are in verify_gui.py"]}
            output = Path("reports/runtime/accessibility/report.json")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
        finally:
            window.close()
            app.processEvents()


if __name__ == "__main__":
    main()
