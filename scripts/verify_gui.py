"""Offscreen Qt interaction check with real CPU inference and synthetic originals."""
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtGui import QFontDatabase
from reportlab.pdfgen import canvas

from omnifind.core import Index
from omnifind.gui import Window


def main():
    attempts = []
    def deny(*args, **kwargs):
        attempts.append("connect")
        raise RuntimeError("Network blocked during GUI verification")
    socket.socket.connect = deny
    socket.create_connection = deny
    app = QApplication.instance() or QApplication([])
    output = Path("reports/runtime/gui").resolve()
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    corpus = run / "corpus"
    corpus.mkdir()
    original = corpus / "scan_0042.pdf"
    pdf = canvas.Canvas(str(original))
    text = pdf.beginText(50, 780)
    for line in ["Fictional rental agreement", "The security deposit is returned within thirty days after moving out,",
                 "minus unpaid rent or damage repairs."]:
        text.textLine(line)
    pdf.drawText(text)
    pdf.save()
    receipt = corpus / "misc.txt"
    receipt.write_text("Laptop charger receipt INV-2048. Paid 1250 pesos.", encoding="utf-8")
    actions = []
    window = Window(run / "data/index.sqlite", Path("models/minilm"),
                    file_action=lambda action, path: actions.append((action, str(path))) or True)
    assert "Segoe UI" in QFontDatabase.families(), "No verified font available for screenshot inspection"

    def settle(expect_error=False):
        deadline = time.monotonic() + 60
        while window.task and (window.task.isRunning() or window.busy.isVisible()):
            app.processEvents()
            # Yield Python's GIL as well as pumping Qt events for Python QThread work.
            time.sleep(0.02)
            if time.monotonic() > deadline:
                raise TimeoutError(f"GUI task exceeded verification deadline; stage: {window.status.text()}")
        app.processEvents()
        assert bool(window.last_error) == expect_error, window.last_error

    def search(query, mode="hybrid"):
        window.navigate(0)
        window.mode.setCurrentIndex(window.mode.findData(mode))
        window.query.setText(query)
        window.query.setFocus()
        QTest.keyClick(window.query, Qt.Key.Key_Return)
        settle()

    try:
        window.show()
        window.activateWindow()
        app.processEvents()
        window.navigate(1)
        with patch.object(QFileDialog, "getExistingDirectory", return_value=str(corpus)):
            QTest.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
        assert window.folder_list.count() == 1
        QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
        window.task.progress.connect(lambda info: print(f'GUI extraction file {info["processed"]}', flush=True))
        window.task.model_ready.connect(lambda model: print('GUI local model ready', flush=True))
        assert not window.query.isEnabled() and window.cancel_button.isVisible()
        # Navigation remains responsive while inference prepares in the background.
        QTest.mouseClick(window.nav[2], Qt.MouseButton.LeftButton)
        assert window.pages.currentIndex() == 2
        settle()
        print('GUI first refresh passed', flush=True)
        assert "2 searchable" in window.status.text(), window.status.text()
        QTest.keyClick(window, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
        app.processEvents()
        assert window.pages.currentIndex() == 0 and window.query.hasFocus()
        window.type_filter.setCurrentIndex(window.type_filter.findData("pdf"))
        search("getting my money back when I leave the apartment")
        assert window.results and Path(window.results[0]["path"]).name == original.name
        assert "security deposit" in window.preview.toPlainText()
        assert "page 1" in window.preview_location.text()
        assert window.open_button.isEnabled()
        QTest.mouseClick(window.open_button, Qt.MouseButton.LeftButton)
        QTest.mouseClick(window.reveal_button, Qt.MouseButton.LeftButton)
        assert actions == [("open", str(original)), ("reveal", str(original))]
        QTest.mouseClick(window.copy_button, Qt.MouseButton.LeftButton)
        assert app.clipboard().text() == str(original)
        window.grab().save(str(output / "search-light.png"))
        window.dark.setChecked(True)
        window.grab().save(str(output / "search-dark.png"))
        window.resize(720, 900)
        app.processEvents()
        assert window.splitter.orientation() == Qt.Orientation.Vertical
        assert window.query.geometry().width() > 100
        assert window.open_button.isVisible()
        window.grab().save(str(output / "search-narrow.png"))
        window.text_size.setCurrentIndex(1)
        app.processEvents()
        window.grab().save(str(output / "search-large-text.png"))
        assert window.open_button.height() >= window.open_button.sizeHint().height()

        # Filter changes preserve query but invalidate old evidence/actions.
        remembered_query = window.query.text()
        window.type_filter.setCurrentIndex(0)
        assert window.query.text() == remembered_query and not window.open_button.isEnabled()
        search("submarine maintenance log")
        assert window.last_response["status"] == "no-strong-match"
        assert window.result_list.count() == 0
        window.weak.setChecked(True)
        QTest.mouseClick(window.search_button, Qt.MouseButton.LeftButton)
        settle()
        assert window.result_list.count() > 0 and window.results[0]["weak_match"]
        if window.result_list.count() > 1:
            window.result_list.setFocus()
            QTest.keyClick(window.result_list, Qt.Key.Key_Down)
            assert window.selected == window.results[1]
        search("INV-2048", "lexical")
        assert "INV-2048" in window.preview.toPlainText()
        old_actions = len(actions)
        receipt.write_text("Updated receipt INV-2048 with changed purchase information.", encoding="utf-8")
        QTest.mouseClick(window.open_button, Qt.MouseButton.LeftButton)
        assert len(actions) == old_actions and not window.open_button.isEnabled()
        assert "changed" in window.status.text()
        window.navigate(1)
        QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
        settle()
        remembered_query = window.query.text()
        QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
        QTest.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
        settle()
        assert window.query.text() == remembered_query and "Canceled" in window.status.text()

        model = window.model
        window.close()
        window = Window(run / "data/index.sqlite", Path("models/missing"),
                        file_action=lambda action, path: actions.append((action, str(path))) or True)
        window.show()
        assert window.folder_list.count() == 1
        search("INV-2048", "lexical")
        assert window.results and window.model is None
        search("INV-2048", "hybrid")
        assert window.results and window.model is None
        assert window.last_response["status"] == "exact-identifier-matches"
        assert "Exact identifier" in window.status.text() and "INV-2048" in window.preview.toPlainText()
        search("INV-9999", "hybrid")
        assert not window.results and window.model is None
        search("INV-2048", "hybrid")
        window.navigate(1)
        QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
        settle(expect_error=True)
        assert window.query.text() == "INV-2048" and window.search_button.isEnabled()
        window.model = model
        window.navigate(1)
        # Settings cleanup requires explicit confirmation and works without model loading.
        window.navigate(2)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            QTest.mouseClick(window.clear_button, Qt.MouseButton.LeftButton)
        assert window.folder_list.count() == 1
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(window.clear_button, Qt.MouseButton.LeftButton)
        settle()
        assert window.folder_list.count() == 0 and "Index cleared" in window.status.text()
        assert original.exists() and receipt.exists()
        window.add_folder(corpus)
        window.navigate(1)
        QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
        settle()
        search("INV-2048", "lexical")
        assert window.preview.toPlainText() and window.open_button.isEnabled()
        # A separate window can revoke cached evidence without a new search/click.
        second_window = Window(run / "data/index.sqlite", Path("models/minilm"))
        second_window.remove_folder(second_window.folder_list.item(0).data(Qt.ItemDataRole.UserRole))
        deadline = time.monotonic() + 2
        while window.preview.toPlainText() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
        assert not window.preview.toPlainText() and not window.open_button.isEnabled()
        assert window.query.text() == "INV-2048" and window.folder_list.count() == 0
        second_window.close()
        window.add_folder(corpus)
        window.navigate(1)
        QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
        settle()
        # Removing scope remains available while background work runs.
        QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
        assert window.remove_button.isEnabled()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(window.remove_button, Qt.MouseButton.LeftButton)
        settle()
        assert window.folder_list.count() == 0 and not window.open_button.isEnabled()
        assert original.exists() and receipt.exists()
        index = Index(run / "data/index.sqlite")
        try:
            assert not index.roots() and not index.search("INV-2048", "lexical")
        finally:
            index.close()
        report = {"artifact": "working-offscreen-Qt-desktop-prototype", "local_model": model.identity,
                  "passed": ["folder-picker control with synthetic selection", "background inference and responsive navigation",
                             "real semantic search with PDF page evidence", "original open/reveal dispatch", "copy path",
                             "light/dark/narrow/large-text rendering", "Ctrl+K Enter and result-arrow keyboard controls",
                             "cancel preserves query and committed index", "filter invalidation preserves query",
                             "no-strong-match and weak-match recovery", "stale open rejected", "manual refresh",
                             "restart persistence", "missing-model failure and lexical recovery", "clear-index confirmation and rebuild preserve originals",
                             "hybrid exact identifier works without model assets and rejects absent codes",
                             "cross-window revocation clears preview and actions without interaction",
                             "folder revocation during work preserves originals"],
                  "python_socket_connect_attempts": len(attempts),
                  "limits": ["Offscreen QtTest, not manual Windows usability or screen-reader validation",
                             "Native picker response was supplied by the test", "OS viewer and Explorer launches intercepted after path authorization",
                             "Synthetic two-file corpus only", "No OS-level network audit"]}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        if window.task and window.task.isRunning():
            window.task.cancel.set()
            window.task.wait(30000)
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
