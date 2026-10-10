"""Explicit frozen-GUI pilot diagnostic using new synthetic files only."""
import json
import tempfile
import time
from pathlib import Path


def run(report_path):
    def stage(name):
        Path(report_path).write_text(json.dumps({'stage': name}))
    stage('imports')
    import sys
    from PIL import Image, ImageDraw, ImageFont
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QAccessible
    from .core import Index
    from .gui import Window
    stage('application')
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "corpus"
        root.mkdir()
        source = root / "schedule.png"
        image = Image.new("RGB", (1000, 350), "white")
        ImageDraw.Draw(image).text((40, 40), "Physics laboratory Wednesday SCH-846", fill="black",
            font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 32))
        image.save(source)
        model = Path(sys.executable).parent / "models/minilm" if getattr(sys, "frozen", False) else Path("models/minilm")
        window = Window(Path(temporary) / "data/index.sqlite", model)
        stage('window')
        window.show()
        def settle():
            deadline = time.monotonic() + 120
            while (window.task and (window.task.isRunning() or window.busy.isVisible())) or window.thumbnail_tasks:
                app.processEvents()
                time.sleep(.02)
                if time.monotonic() > deadline:
                    raise RuntimeError("GUI probe timed out")
            app.processEvents()
            if window.last_error:
                raise RuntimeError("GUI probe failed")
        try:
            rid = window.add_folder(root)
            window.start_task("refresh", {"root_id": rid})
            stage('refresh')
            settle()
            window.query.setText("what day is the physics laboratory")
            window.submit_search()
            stage('search')
            settle()
            assert window.results and Path(window.results[0]["path"]) == source
            assert "Wednesday" in window.preview.toPlainText() and window.image_preview.isVisible()
            interface = QAccessible.queryAccessibleInterface(window.preview)
            assert interface.textInterface().characterCount() > 0
            index = Index(window.database)
            try:
                index.remove_root(rid)
            finally:
                index.close()
            deadline = time.monotonic() + 3
            while window.preview.toPlainText() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.02)
            assert not window.preview.toPlainText() and not window.open_button.isEnabled()
            assert source.exists()
            Path(report_path).write_text(json.dumps({"frozen_gui": bool(getattr(sys, "frozen", False)),
                "qt_platform": app.platformName(), "real_model_screenshot_query": True,
                "thumbnail_and_accessible_evidence": True, "privacy_revocation": True}, indent=2))
        finally:
            window.close()
            app.processEvents()
