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
from PIL import Image, ImageDraw, ImageFont

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
    screenshot = corpus / "schedule.png"
    image = Image.new("RGB", (1000, 450), "white")
    ImageDraw.Draw(image).multiline_text((40, 40), "CLASS SCHEDULE - SCH-642\nPhysics laboratory: Wednesday 3 PM\nRoom 307. Bring safety goggles.",
        fill="black", font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 32), spacing=18)
    image.save(screenshot)
    (corpus / "broken.png").write_bytes(b"invalid image")
    (corpus / "broken.pdf").write_bytes(b"invalid PDF")
    (corpus / "unsupported.csv").write_text("unsupported synthetic file")
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
        while window.thumbnail_tasks:
            app.processEvents()
            time.sleep(.02)
            if time.monotonic() > deadline:
                raise TimeoutError("Thumbnail exceeded verification deadline")
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
        assert "3 searchable" in window.status.text(), window.status.text()
        QTest.mouseClick(window.issues_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert window.issue_dialog and window.issue_dialog.issue_list.count() == 3
        issue_text = " ".join(window.issue_dialog.issue_list.item(i).text() for i in range(3))
        assert "broken.png" in issue_text and "could not be decoded" in issue_text
        assert "unsupported.csv" in issue_text and "not supported" in issue_text
        window.issue_dialog.grab().save(str(output / "file-issues.png"))
        window.issue_dialog.close()
        window.activateWindow()
        app.processEvents()
        QTest.keyClick(window, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
        app.processEvents()
        assert window.pages.currentIndex() == 0 and window.query.hasFocus()
        window.type_filter.setCurrentIndex(window.type_filter.findData("pdf"))
        search("getting my money back when I leave the apartment")
        assert window.results and Path(window.results[0]["path"]).name == original.name
        assert "security deposit" in window.preview.toPlainText()
        assert "page 1" in window.preview_location.text()
        assert window.open_button.isEnabled()
        window.type_filter.setCurrentIndex(window.type_filter.findData("png"))
        search("what should I wear to the physics practical class")
        assert window.results and Path(window.results[0]["path"]).name == screenshot.name
        assert "OCR-recognized" in window.preview_location.text()
        assert "safety goggles" in window.preview.toPlainText()
        assert window.image_preview.isVisible() and not window.image_preview.pixmap().isNull()
        search("SCH-642")
        assert window.last_response["status"] == "exact-identifier-matches"
        window.grab().save(str(output / "ocr-evidence.png"))
        window.type_filter.setCurrentIndex(window.type_filter.findData("pdf"))
        search("getting my money back when I leave the apartment")
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
        search("SCH-642")
        assert window.preview.toPlainText() and window.open_button.isEnabled()
        assert window.image_preview.isVisible()
        window.navigate(1)
        QTest.mouseClick(window.issues_button, Qt.MouseButton.LeftButton)
        assert window.issue_dialog and window.issue_dialog.issue_list.count() == 3
        # A separate window can revoke cached evidence without a new search/click.
        second_window = Window(run / "data/index.sqlite", Path("models/minilm"))
        second_window.remove_folder(second_window.folder_list.item(0).data(Qt.ItemDataRole.UserRole))
        deadline = time.monotonic() + 2
        while window.preview.toPlainText() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
        assert not window.preview.toPlainText() and not window.open_button.isEnabled()
        assert not window.image_preview.isVisible() and window.image_preview.pixmap().isNull()
        assert window.issue_dialog is None
        assert window.query.text() == "SCH-642" and window.folder_list.count() == 0
        second_window.close()
        window.add_folder(corpus)
        window.navigate(1)
        QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
        settle()
        search("SCH-642")
        # Close with a newly started image worker: cancellation must finish before destruction.
        window.select_result(0)
        assert window.thumbnail_tasks
        window.close()
        deadline = time.monotonic() + 5
        while window.thumbnail_tasks and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
        app.processEvents()
        assert not window.thumbnail_tasks and not window.isVisible()
        window = Window(run / "data/index.sqlite", Path("models/minilm"))
        window.model = model
        window.show()
        window.navigate(1)
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
                             "Synthetic six-file corpus: three searchable and three recorded issues", "No OS-level network audit"],
                  "ocr": {"engine": "Windows.Media.Ocr", "verified": ["contained screenshot extraction", "real MiniLM paraphrase search", "exact screenshot code", "OCR evidence label and original path"]}}
        report["ocr"]["verified"].append("bounded original-image thumbnail with asynchronous preview")
        report["ocr"]["verified"].extend(["cross-window revocation clears thumbnail", "close cancels thumbnail before window destruction"])
        report["passed"].extend(["file issues identify corrupt and unsupported files with recovery steps", "cross-window revocation closes file issues"])
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
