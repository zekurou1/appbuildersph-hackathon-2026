"""Native desktop journey backed by the real local core; no web content or server."""
import argparse
import base64
import json
import os
import re
import sqlite3
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QKeySequence, QShortcut, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QGridLayout,
    QPushButton, QSplitter, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget, QScrollArea, QSizePolicy, QDialog,
)

from .core import Index, ScopeError, WorkCancelled, is_identifier_query
from .worker import run_worker
from .issues import issue_copy


class ThumbnailTask(QThread):
    result = Signal(object)

    def __init__(self, database, source, parent=None):
        super().__init__(parent)
        self.database, self.source = database, source
        self.cancel = threading.Event()

    def run(self):
        index = None
        try:
            index = Index(self.database)
            def checkpoint():
                if self.cancel.is_set():
                    raise WorkCancelled("operation-cancelled")
                index.source_path(self.source["file_id"], self.source["revision"])
            checkpoint()
            root = index.db.execute("SELECT path FROM roots WHERE id=?", (self.source["root_id"],)).fetchone()[0]
            code, output = run_worker("omnifind.thumbnail", [self.source["path"], root, self.source["revision"]], checkpoint)
            checkpoint()
            if code == 0:
                self.result.emit(json.loads(output))
        except Exception:
            pass  # Text evidence remains usable if an optional thumbnail fails.
        finally:
            if index:
                index.close()


def error_copy(error):
    code = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z-]{1,80}", str(error)) else "local-operation-failed"
    messages = {
        "folder-not-authorized": "This folder has been removed. Choose another folder.",
        "index-busy-retry-after-refresh": "Another window is refreshing this index. Wait for it to finish, then retry.",
        "source-changed-refresh-required": "This file changed. Refresh its folder before opening it.",
        "overlapping-roots": "That folder overlaps a selected folder. Choose one parent folder or separate folders.",
        "link-or-cloud-placeholder": "Choose an available local folder. Links and cloud-only placeholders are excluded.",
        "model-mismatch-create-new-index": "This index uses a different model. Keep the original model or create a separate index.",
        "model-token-limit-shorten-query": "This description is too long. Try a shorter phrase.",
        "query-or-result-limit": "This description is too long. Try a shorter phrase.",
        "too-many-query-terms": "This description has too many words. Try a shorter phrase.",
    }
    return messages.get(code, "The operation could not finish. Check folder access and local model setup, then retry.")


class Task(QThread):
    result = Signal(object)
    problem = Signal(str)
    progress = Signal(object)
    model_ready = Signal(object)

    def __init__(self, database, model_directory, model, operation, parameters, parent=None):
        super().__init__(parent)
        self.database, self.model_directory = database, model_directory
        self.model, self.operation, self.parameters = model, operation, parameters
        self.cancel = threading.Event()

    def run(self):
        index = None
        try:
            needs_model = self.operation == "refresh" or (self.operation == "search" and
                (self.parameters["mode"] == "semantic" or
                 (self.parameters["mode"] == "hybrid" and not is_identifier_query(self.parameters["query"]))))
            if needs_model and self.model is None:
                from .model import LocalEmbedder
                self.model = LocalEmbedder(self.model_directory)
                self.model_ready.emit(self.model)
            if self.cancel.is_set():
                raise WorkCancelled("operation-cancelled")
            index = Index(self.database, self.model)
            if self.operation == "refresh":
                result = index.refresh(self.parameters["root_id"], self.cancel, self.progress.emit)
            elif self.operation == "clear":
                result = index.clear()
            else:
                result = index.search_response(**self.parameters)
            if self.cancel.is_set():
                raise WorkCancelled("operation-cancelled")
            self.result.emit(result)
        except WorkCancelled:
            self.problem.emit("Canceled. Files already indexed are kept; refresh again to continue.")
        except (ValueError, OSError, RuntimeError, ImportError, sqlite3.Error) as error:
            self.problem.emit(error_copy(error))
        except Exception:
            self.problem.emit("The local operation failed. Retry or check the setup instructions.")
        finally:
            if index:
                index.close()


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap or name == "headline")
    if name:
        widget.setObjectName(name)
    return widget


class Window(QMainWindow):
    def __init__(self, database, model_directory, file_action=None):
        super().__init__()
        self.database = Path(database)
        self.model_directory = Path(model_directory)
        self.file_action = file_action or self._native_action
        self.model = None
        self.task = None
        self.thumbnail_tasks = []
        self.preview_generation = 0
        self.closing = False
        self.results = []
        self.selected = None
        self.last_response = None
        self.last_error = None
        self.issue_dialog = None
        self.text_scale = 1.0
        self.generation = 0
        self.cancel_requested = False
        # The offscreen Windows Qt plugin does not enumerate installed fonts itself.
        if "Segoe UI" not in QFontDatabase.families():
            font_directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for name in ["segoeui.ttf", "segoeuib.ttf"]:
                path = font_directory / name
                if path.is_file():
                    QFontDatabase.addApplicationFont(str(path))
        self.setWindowTitle("OmniFind Local")
        self.resize(1180, 780)
        self.setMinimumSize(680, 620)
        self.setFont(QFont("Segoe UI", 10))
        shell = QWidget()
        self.setCentralWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.addWidget(label("OmniFind", "brand"))
        header.addWidget(label("LOCAL", "badge"))
        header.addStretch()
        self.nav = []
        for title in ["Search", "Folders", "Settings"]:
            button = QPushButton(title)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=len(self.nav): self.navigate(i))
            self.nav.append(button)
            header.addWidget(button)
        layout.addLayout(header)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self._search_page()
        self._folders_page()
        self._settings_page()
        self.status = label("Choose a folder to start. Your originals stay where they are.", "status", True)
        layout.addWidget(self.status)
        busy = QHBoxLayout()
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setAccessibleName("Local operation running")
        self.busy.hide()
        self.cancel_button = QPushButton("Cancel after current step")
        self.cancel_button.clicked.connect(self.cancel_work)
        self.cancel_button.hide()
        busy.addWidget(self.busy, 1)
        busy.addWidget(self.cancel_button)
        layout.addLayout(busy)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.focus_search)
        QShortcut(QKeySequence("Escape"), self, activated=self.cancel_work)
        self.set_theme(False)
        self.navigate(0)
        self.update_folders()
        # Read-only connection avoids schema/setup writes on each privacy heartbeat.
        self.scope_monitor = None
        self.privacy_epoch = None
        try:
            self.scope_monitor = sqlite3.connect(self.database.resolve().as_uri() + "?mode=ro", uri=True, timeout=.05)
            self.privacy_epoch = self.read_privacy_epoch()
        except (sqlite3.Error, TypeError):
            if self.scope_monitor:
                self.scope_monitor.close()
            self.scope_monitor = None
        self.scope_timer = QTimer(self)
        self.scope_timer.setInterval(250)
        self.scope_timer.timeout.connect(self.check_external_revocation)
        self.scope_timer.start()

    def read_privacy_epoch(self):
        return self.scope_monitor.execute("SELECT value FROM metadata WHERE key='privacy-epoch'").fetchone()[0]

    def check_external_revocation(self):
        if not self.scope_monitor or (self.task and self.task.isRunning() and self.task.operation == "clear"):
            return
        try:
            epoch = self.read_privacy_epoch()
        except sqlite3.Error:
            return
        if epoch != self.privacy_epoch:
            self.privacy_epoch = epoch
            self.cancel_work()
            self.generation += 1
            self.invalidate_results()
            self.update_folders()
            self.status.setText("Folder access changed. Previous evidence was cleared; search again in the remaining folders.")

    def _search_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Find the file you remember.", "headline"))
        layout.addWidget(label("Search its contents, check the evidence, then open the original.", "secondary", True))
        query_label = label("Describe the file")
        layout.addWidget(query_label)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setAccessibleName("Describe the file")
        query_label.setBuddy(self.query)
        self.query.setPlaceholderText("e.g. the agreement about getting my deposit back")
        self.query.setClearButtonEnabled(True)
        self.query.returnPressed.connect(self.submit_search)
        self.query.textChanged.connect(self.invalidate_results)
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self.submit_search)
        row.addWidget(self.query, 1)
        row.addWidget(self.search_button)
        layout.addLayout(row)
        self.filters = QGridLayout()
        self.type_filter = QComboBox()
        for text, value in [("All supported types", None), ("PDF", "pdf"), ("Text", "txt"), ("Markdown", "md"), ("PNG screenshot", "png"), ("JPEG image", "jpg"), ("JPEG (.jpeg)", "jpeg")]:
            self.type_filter.addItem(text, value)
        self.type_filter.setAccessibleName("File type filter")
        self.folder_filter = QComboBox()
        self.folder_filter.setAccessibleName("Folder filter")
        self.mode = QComboBox()
        for text, value in [("Meaning + words", "hybrid"), ("Meaning", "semantic"), ("Words only (limited)", "lexical"), ("Filename only", "filename")]:
            self.mode.addItem(text, value)
        self.mode.setAccessibleName("Search mode")
        self.weak = QCheckBox("Show weaker matches")
        self.weak.setToolTip("Experimental thresholds can hide useful files. Inspect the original evidence.")
        for number, widget in enumerate([self.type_filter, self.folder_filter, self.mode]):
            widget.currentIndexChanged.connect(self.invalidate_results)
            self.filters.addWidget(widget, 0, number)
        self.filters.addWidget(self.weak, 0, 3)
        self.weak.toggled.connect(self.invalidate_results)
        layout.addLayout(self.filters)
        self.result_count = label("Your folders are your search space.", "secondary", True)
        layout.addWidget(self.result_count)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.result_list = QListWidget()
        self.result_list.setAccessibleName("Matching files")
        self.result_list.currentRowChanged.connect(self.select_result)
        self.result_list.setWordWrap(True)
        self.result_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.result_list.setSpacing(6)
        self.splitter.addWidget(self.result_list)
        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)
        self.preview_title = label("Check the source", "section", True)
        self.preview_path = QLineEdit()
        self.preview_path.setObjectName("sourcePath")
        self.preview_path.setReadOnly(True)
        self.preview_path.setAccessibleName("Original file path")
        self.preview_path.setPlaceholderText("Select a result to inspect its matching passage.")
        self.preview_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.preview_location = label("", "secondary", True)
        self.image_preview = QLabel()
        self.image_preview.setAccessibleName("Original image thumbnail")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMaximumHeight(180)
        self.image_preview.hide()
        self.preview = QTextBrowser()
        self.preview.setAccessibleName("Original matching passage")
        self.preview.setOpenExternalLinks(False)
        self.preview.setOpenLinks(False)
        self.preview.setPlaceholderText("Original source evidence appears here.")
        actions = QHBoxLayout()
        self.open_button = QPushButton("Open original")
        self.open_button.setObjectName("primary")
        self.reveal_button = QPushButton("Show in folder")
        self.copy_button = QPushButton("Copy path")
        self.open_button.clicked.connect(lambda: self.act_on_file("open"))
        self.reveal_button.clicked.connect(lambda: self.act_on_file("reveal"))
        self.copy_button.clicked.connect(lambda: self.act_on_file("copy"))
        for button in [self.open_button, self.reveal_button, self.copy_button]:
            button.setEnabled(False)
            actions.addWidget(button)
        for widget in [self.preview_title, self.preview_path, self.preview_location, self.image_preview, self.preview]:
            preview_layout.addWidget(widget)
        preview_layout.addLayout(actions)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setSizes([560, 460])
        layout.addWidget(self.splitter, 1)
        self.pages.addWidget(page)

    def _folders_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Choose your search space.", "headline"))
        layout.addWidget(label("OmniFind reads only folders you choose. Supported now: digital PDF, TXT, MD and English PNG/JPEG OCR. "
                               "It stores searchable text and vectors locally; original files stay untouched.", "secondary", True))
        self.folder_list = QListWidget()
        self.folder_list.setAccessibleName("Selected folders")
        self.folder_list.setWordWrap(True)
        layout.addWidget(self.folder_list, 1)
        controls = QHBoxLayout()
        self.add_button = QPushButton("Add folder…")
        self.add_button.setObjectName("primary")
        self.refresh_button = QPushButton("Refresh selected")
        self.remove_button = QPushButton("Remove from index…")
        self.issues_button = QPushButton("Review file issues")
        self.issues_button.clicked.connect(self.review_issues)
        self.add_button.clicked.connect(self.choose_folder)
        self.refresh_button.clicked.connect(self.refresh_selected)
        self.remove_button.clicked.connect(self.confirm_remove)
        for button in [self.add_button, self.refresh_button, self.remove_button, self.issues_button]:
            controls.addWidget(button)
        layout.addLayout(controls)
        self.coverage = label("No folders selected.", "secondary", True)
        layout.addWidget(self.coverage)
        layout.addWidget(label("Refresh is manual. Cloud-only files, links and scanned PDF pages are excluded. Readable English PNG/JPEG screenshots are supported.", "secondary", True))
        self.pages.addWidget(page)

    def _settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Local by design. Clear about limits.", "headline"))
        layout.addWidget(label("After setup, files and queries are processed on this computer. Model setup downloads public assets. "
                               "There is no cloud inference fallback or account requirement.", "secondary", True))
        layout.addWidget(label("What is stored", "section"))
        layout.addWidget(label("The index contains extracted text, paths and embeddings in plaintext. Local storage is not encryption. "
                               "Query history is off. Removing a folder removes its searchable derivatives and preserves originals.", wrap=True))
        layout.addWidget(label(str(self.database.resolve()), "secondary", True))
        self.clear_button = QPushButton("Clear index…")
        self.clear_button.clicked.connect(self.confirm_clear)
        layout.addWidget(self.clear_button)
        layout.addWidget(label("Prototype scope", "section"))
        layout.addWidget(label("English-first digital PDF/TXT/MD and PNG/JPEG OCR using installed Windows English OCR. Scanned PDFs, installers and large-corpus performance are not verified. "
                               "Weak-match thresholds were tuned on synthetic development examples; verify evidence before opening a file.", wrap=True))
        layout.addWidget(label("If model assets are missing, use Words only for previously indexed content. "
                               "To prepare assets, follow the local setup instructions in the README, then retry.", wrap=True))
        self.dark = QCheckBox("Dark appearance")
        self.dark.toggled.connect(self.set_theme)
        layout.addWidget(self.dark)
        text_size_label = label("Text size")
        layout.addWidget(text_size_label)
        self.text_size = QComboBox()
        self.text_size.setAccessibleName("Text size")
        text_size_label.setBuddy(self.text_size)
        for title, factor in [("Standard", 1.0), ("Larger", 1.3), ("Largest", 1.5)]:
            self.text_size.addItem(title, factor)
        self.text_size.currentIndexChanged.connect(self.change_text_size)
        layout.addWidget(self.text_size)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)

    def change_text_size(self):
        self.text_scale = self.text_size.currentData()
        self.set_theme(self.dark.isChecked())

    def confirm_clear(self):
        if self.task and self.task.isRunning():
            self.status.setText("Wait for the current operation to finish before clearing the index.")
            return
        response = QMessageBox.question(self, "Clear the entire index?",
            "Forget all selected folders and remove their searchable text, paths and embeddings. "
            "Original files and downloaded models stay untouched. Add folders again to rebuild.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if response == QMessageBox.StandardButton.Yes:
            self.invalidate_results()
            self.start_task("clear", {})

    def set_theme(self, dark):
        canvas, surface, text, secondary, accent, action, border, selected, focus = (
            ("#111923", "#192432", "#E8EEF5", "#A9B8C9", "#71D5C6", "#0C201D", "#8193A8", "#213D3C", "#90BAFF") if dark else
            ("#F7F9FC", "#FFFFFF", "#172B3A", "#526373", "#0B6B62", "#FFFFFF", "#718096", "#E9F5F2", "#2563EB"))
        tick = (Path(__file__).resolve().parent / "assets" / ("check-dark.svg" if dark else "check-light.svg")).as_posix()
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {canvas}; color: {text}; font-family: 'Segoe UI'; font-size: {10 * self.text_scale}pt; }}
            QLabel#brand {{ font-size: {23 * self.text_scale}px; font-weight: 700; }}
            QLabel#badge {{ color: {accent}; font-size: {11 * self.text_scale}px; font-weight: 700; }}
            QLabel#headline {{ font-size: {27 * self.text_scale}px; font-weight: 600; padding-top: 12px; }}
            QLabel#section {{ font-size: {17 * self.text_scale}px; font-weight: 600; }}
            QLabel#secondary, QLabel#status {{ color: {secondary}; }}
            QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 7px; padding: 9px 12px; }}
            QPushButton#primary {{ background: {accent}; color: {action}; border-color: {accent}; font-weight: 600; }}
            QPushButton:checked, QListWidget::item:selected {{ background: {selected}; color: {text}; }}
            QPushButton:disabled {{ color: {secondary}; background: {canvas}; }}
            QLineEdit, QComboBox, QTextBrowser, QListWidget {{ background: {surface}; border: 1px solid {border}; border-radius: 7px; padding: 8px; }}
            QLineEdit:focus, QPushButton:focus, QComboBox:focus, QListWidget:focus, QTextBrowser:focus {{ border: 2px solid {focus}; }}
            QLineEdit#sourcePath {{ background: {canvas}; color: {secondary}; border: none; padding: 0; }}
            QListWidget::item {{ padding: 10px; border-bottom: 1px solid {border}; }}
            QProgressBar {{ border: 1px solid {border}; border-radius: 5px; max-height: 10px; }}
            QProgressBar::chunk {{ background: {accent}; }}
            QCheckBox {{ spacing: 8px; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {border}; border-radius: 3px; background: {surface}; }}
            QCheckBox::indicator:checked {{ background: {accent}; image: url("{tick}"); }}
        """)

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for number, button in enumerate(self.nav):
            button.setChecked(index == number)
        if index == 1:
            self.update_folders()

    def focus_search(self):
        self.navigate(0)
        self.query.setFocus()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "splitter"):
            narrow = self.width() < 960
            self.splitter.setOrientation(Qt.Orientation.Vertical if narrow else Qt.Orientation.Horizontal)
            for number, widget in enumerate([self.type_filter, self.folder_filter, self.mode, self.weak]):
                self.filters.removeWidget(widget)
                self.filters.addWidget(widget, number // 2 if narrow else 0, number % 2 if narrow else number)

    def clear_preview(self):
        self.preview_generation += 1
        for task in self.thumbnail_tasks:
            task.cancel.set()
        self.image_preview.clear()
        self.image_preview.hide()
        self.selected = None
        self.preview_title.setText("Check the source")
        self.preview_path.clear()
        self.preview_location.clear()
        self.preview.clear()
        for button in [self.open_button, self.reveal_button, self.copy_button]:
            button.setEnabled(False)

    def invalidate_results(self, *args):
        if self.issue_dialog:
            self.issue_dialog.issue_list.clear()
            self.issue_dialog.close()
        self.results = []
        self.result_list.clear()
        self.clear_preview()
        self.result_count.setText("Press Search to apply this description and these filters.")

    def review_issues(self):
        self.check_external_revocation()
        item = self.folder_list.currentItem()
        if not item:
            self.status.setText("Choose a selected folder to review its files.")
            return
        if self.issue_dialog:
            self.issue_dialog.close()
        root_id = item.data(Qt.ItemDataRole.UserRole)
        dialog = QDialog(self)
        dialog.setWindowTitle("File issues in selected folder")
        dialog.resize(760, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Files that need attention", "section"))
        dialog.summary = label("", "secondary", True)
        layout.addWidget(dialog.summary)
        dialog.issue_list = QListWidget()
        dialog.issue_list.setAccessibleName("File issues and recovery steps")
        dialog.issue_list.setWordWrap(True)
        dialog.issue_list.setSpacing(8)
        layout.addWidget(dialog.issue_list, 1)
        more = QPushButton("Show more")
        more.setAccessibleName("Show next file issues")
        close = QPushButton("Close")
        close.clicked.connect(dialog.close)
        actions = QHBoxLayout()
        actions.addWidget(more)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)
        dialog.cursor = 0
        self.issue_dialog = dialog
        def load_page():
            index = None
            try:
                index = Index(self.database)
                page = index.file_issues(root_id, dialog.cursor)
                self.check_external_revocation()
                if self.issue_dialog is not dialog:
                    return
                for issue in page["items"]:
                    path = Path(issue["path"])
                    text = f'{path.name}\n{path.parent}\n{issue["state"].capitalize()} · {issue_copy(issue["state"], issue["error"])}'
                    entry = QListWidgetItem(text)
                    entry.setData(Qt.ItemDataRole.AccessibleTextRole, text)
                    dialog.issue_list.addItem(entry)
                dialog.cursor = page["next_after_id"]
                more.setEnabled(dialog.cursor is not None)
                count = dialog.issue_list.count()
                dialog.summary.setText(f"{count} file issues shown. Refresh this folder after addressing them." if count else
                                       "No recorded issues in this folder. Refresh to discover new or changed files.")
            except (OSError, ValueError, sqlite3.Error):
                dialog.issue_list.clear()
                more.setEnabled(False)
                dialog.summary.setText("Folder access changed or is unavailable. Close this view and check the selected folders.")
            finally:
                if index:
                    index.close()
        def finished():
            dialog.issue_list.clear()
            if self.issue_dialog is dialog:
                self.issue_dialog = None
            dialog.deleteLater()
        dialog.finished.connect(finished)
        more.clicked.connect(load_page)
        load_page()
        if self.issue_dialog is dialog:
            dialog.show()

    def update_folders(self):
        selected_id = self.folder_filter.currentData() if hasattr(self, "folder_filter") else None
        self.folder_filter.blockSignals(True)
        self.folder_filter.clear()
        self.folder_filter.addItem("All selected folders", None)
        self.folder_list.clear()
        index = None
        try:
            index = Index(self.database)
            for root in index.roots():
                coverage = index.coverage(root["id"])
                item = QListWidgetItem(f'{root["path"]}\n{coverage["searchable"]} searchable · {coverage["failed"]} failed · {coverage["unsupported"]} unsupported')
                item.setData(Qt.ItemDataRole.UserRole, root["id"])
                self.folder_list.addItem(item)
                self.folder_filter.addItem(Path(root["path"]).name or root["path"], root["id"])
            position = self.folder_filter.findData(selected_id)
            self.folder_filter.setCurrentIndex(max(position, 0))
            coverage = index.coverage()
            self.coverage.setText(" · ".join(f"{count} {state}" for state, count in coverage.items()))
            if self.folder_list.count():
                self.folder_list.setCurrentRow(0)
        except (OSError, ValueError, sqlite3.Error) as error:
            self.show_problem(error_copy(error))
        finally:
            if index:
                index.close()
            self.folder_filter.blockSignals(False)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to index")
        if path:
            self.add_folder(path)

    def add_folder(self, path):
        index = None
        try:
            index = Index(self.database)
            root_id = index.add_root(path)
            self.invalidate_results()
            self.update_folders()
            for number in range(self.folder_list.count()):
                if self.folder_list.item(number).data(Qt.ItemDataRole.UserRole) == root_id:
                    self.folder_list.setCurrentRow(number)
            self.status.setText("Folder added. Choose Refresh selected to make its supported files searchable.")
            return root_id
        except (OSError, ValueError, sqlite3.Error) as error:
            self.show_problem(error_copy(error))
        finally:
            if index:
                index.close()

    def refresh_selected(self):
        item = self.folder_list.currentItem()
        if not item:
            self.status.setText("Add or select a folder first.")
            return
        self.start_task("refresh", {"root_id": item.data(Qt.ItemDataRole.UserRole)})

    def confirm_remove(self):
        item = self.folder_list.currentItem()
        if not item:
            return
        response = QMessageBox.question(self, "Remove folder from index?",
                                        "This removes searchable text and embeddings for this folder. Original files stay untouched.",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                        QMessageBox.StandardButton.No)
        if response == QMessageBox.StandardButton.Yes:
            self.remove_folder(item.data(Qt.ItemDataRole.UserRole))

    def remove_folder(self, root_id):
        index = None
        try:
            index = Index(self.database)
            index.remove_root(root_id)
            self.privacy_epoch = self.read_privacy_epoch() if self.scope_monitor else None
            self.generation += 1
            if self.task and self.task.isRunning():
                self.task.cancel.set()
            self.invalidate_results()
            self.update_folders()
            self.status.setText("Folder removed from search. Original files are preserved. Choose a folder or search again to apply the new scope.")
        except (OSError, ValueError, sqlite3.Error) as error:
            self.show_problem(error_copy(error))
        finally:
            if index:
                index.close()

    def submit_search(self):
        if not self.query.text().strip():
            self.status.setText("Describe the file you want to find.")
            self.query.setFocus()
            return
        self.start_task("search", {"query": self.query.text(), "mode": self.mode.currentData(),
                                   "root_id": self.folder_filter.currentData(), "suffix": self.type_filter.currentData(),
                                   "show_weak": self.weak.isChecked()})

    def start_task(self, operation, parameters):
        if self.task and self.task.isRunning():
            return
        self.last_error = None
        self.cancel_requested = False
        self.generation += 1
        generation = self.generation
        self.invalidate_results()
        self.busy.show()
        self.cancel_button.setVisible(operation != "clear")
        self.cancel_button.setEnabled(True)
        self.set_busy(True)
        self.status.setText("Clearing local index…" if operation == "clear" else
                           "Preparing local search…" if self.model is None and parameters.get("mode", "hybrid") in {"hybrid", "semantic"} else "Working locally…")
        self.task = Task(self.database, self.model_directory, self.model, operation, parameters, self)
        self.task.model_ready.connect(lambda model: setattr(self, "model", model))
        callback = {"search": self.search_done, "refresh": self.refresh_done, "clear": self.clear_done}[operation]
        self.task.result.connect(lambda result: callback(result) if self.generation == generation else None)
        self.task.problem.connect(lambda message: self.show_problem(message) if self.generation == generation else None)
        self.task.progress.connect(lambda info: self.status.setText(f'Processing file {info["processed"]} · {info["coverage"]["searchable"]} searchable so far') if self.generation == generation else None)
        self.task.finished.connect(self.finish_task)
        self.task.start()

    def set_busy(self, busy):
        for widget in [self.query, self.search_button, self.type_filter, self.folder_filter, self.mode,
                       self.weak, self.add_button, self.refresh_button, self.clear_button]:
            widget.setEnabled(not busy)

    def cancel_work(self):
        if self.task and self.task.isRunning() and self.task.operation != "clear":
            self.task.cancel.set()
            self.generation += 1
            self.cancel_requested = True
            self.cancel_button.setEnabled(False)
            self.status.setText("Stopping after the current extraction or inference step. Committed files are kept.")

    def finish_task(self):
        self.busy.hide()
        self.cancel_button.hide()
        self.set_busy(False)
        self.update_folders()
        if self.cancel_requested:
            self.status.setText("Canceled. Files already indexed are kept; refresh again to continue.")
        if self.closing:
            self.close()

    def show_problem(self, message):
        self.last_error = message
        self.status.setText(message)

    def refresh_done(self, coverage):
        self.status.setText(f'Refresh complete: {coverage["searchable"]} searchable, {coverage["failed"]} failed, {coverage["unsupported"]} unsupported.')
        self.update_folders()

    def clear_done(self, result):
        self.privacy_epoch = self.read_privacy_epoch() if self.scope_monitor else None
        self.invalidate_results()
        self.update_folders()
        self.status.setText("Index cleared. Original files and models are kept. Add folders to start again." if result["compacted"]
                            else "Index cleared; storage compaction could not finish. Original files and models are kept.")

    def search_done(self, response):
        generation = self.generation
        self.check_external_revocation()
        if generation != self.generation:
            return
        index = None
        validated = []
        try:
            index = Index(self.database)
            for result in response["results"]:
                try:
                    path = index.source_path(result["file_id"], result["revision"])
                    if str(path) == result["path"]:
                        validated.append(result)
                except (OSError, ValueError):
                    pass
        except (OSError, ValueError, sqlite3.Error) as error:
            self.show_problem(error_copy(error))
            return
        finally:
            if index:
                index.close()
        if response["results"] and not validated:
            response["status"] = "no-results"
        response["results"] = validated
        self.last_response = response
        self.results = response["results"]
        self.result_list.clear()
        self.clear_preview()
        copy = {
            "no-strong-match": "No strong match. Try another description or enable Show weaker matches and search again.",
            "no-results": "No matches in these folders and filters. Refresh your folders or broaden the search.",
            "literal-candidates": "Words-only or filename matches. Meaning search is not used in this mode.",
            "exact-identifier-matches": "Exact identifier found in the source text. Meaning scoring is not used; verify the original passage.",
            "uncalibrated-candidates": "Candidate matches. Weak-match calibration is unavailable for this model.",
            "matches": "Check the original passage before opening. Ranking is not confidence.",
        }
        self.status.setText(copy.get(response["status"], "Describe the file you want to find."))
        noun = "file" if len(self.results) == 1 else "files"
        self.result_count.setText(f'{len(self.results)} {noun} · {copy.get(response["status"], "")}')
        for result in self.results:
            path = Path(result["path"])
            origin = f'Page {result["page"]}' if result["page"] else f'Lines {result["line_start"]}–{result["line_end"]}'
            warning = " · Weaker match" if result.get("weak_match") else ""
            parent = self.result_list.fontMetrics().elidedText(path.parent.as_posix(), Qt.TextElideMode.ElideMiddle,
                                                             max(150, self.result_list.viewport().width() - 50))
            item = QListWidgetItem(f'{path.name}\n{parent}\n{origin}{warning}\n{result["text"][:180]}')
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.AccessibleTextRole, f'{path.name}, {path.parent}, {origin}. {result["text"][:180]}')
            self.result_list.addItem(item)
        if self.results:
            self.result_list.setCurrentRow(0)

    def select_result(self, row):
        self.clear_preview()
        if not 0 <= row < len(self.results):
            return
        result = self.results[row]
        index = None
        try:
            index = Index(self.database)
            path = index.source_path(result["file_id"], result["revision"])
            if str(path) != result["path"]:
                raise ScopeError("source-changed-refresh-required")
            self.selected = result
            self.preview_title.setText(path.name)
            self.preview_path.setText(str(path))
            self.preview_path.setToolTip(str(path))
            self.preview_path.setCursorPosition(0)
            self.preview_location.setText(f'Original text · page {result["page"]}' if result["page"] else
                                          f'Original text · lines {result["line_start"]}–{result["line_end"]}')
            self.preview.setPlainText(result["text"])
            if result.get("provenance") == "ocr-recognized":
                self.preview_location.setText("OCR-recognized English text · check the original image for errors")
                self.load_thumbnail(result)
            for button in [self.open_button, self.reveal_button, self.copy_button]:
                button.setEnabled(True)
        except (OSError, ValueError, sqlite3.Error) as error:
            self.show_problem(error_copy(error))
        finally:
            if index:
                index.close()

    def load_thumbnail(self, source):
        if len(self.thumbnail_tasks) >= 2:
            return
        generation = self.preview_generation
        task = ThumbnailTask(self.database, source, self)
        self.thumbnail_tasks.append(task)
        def display(payload):
            self.check_external_revocation()
            if generation != self.preview_generation or self.selected != source:
                return
            index = None
            try:
                index = Index(self.database)
                index.source_path(source["file_id"], source["revision"])
                if not (0 < payload["width"] <= 640 and 0 < payload["height"] <= 360):
                    return
                png = base64.b64decode(payload["png"], validate=True)
                if len(png) > 1024 * 1024:
                    return
                pixmap = QPixmap()
                if pixmap.loadFromData(png, "PNG"):
                    self.image_preview.setPixmap(pixmap.scaled(640, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    self.image_preview.show()
            except (OSError, ValueError, sqlite3.Error, KeyError):
                self.clear_preview()
            finally:
                if index:
                    index.close()
        def finished():
            self.thumbnail_tasks.remove(task)
            task.deleteLater()
            if self.closing:
                self.close()
        task.result.connect(display)
        task.finished.connect(finished)
        task.start()

    def act_on_file(self, action):
        self.check_external_revocation()
        if not self.selected:
            return
        index = None
        try:
            index = Index(self.database)
            path = index.source_path(self.selected["file_id"], self.selected["revision"])
            if str(path) != self.selected["path"]:
                raise ScopeError("source-changed-refresh-required")
            if action == "copy":
                QApplication.clipboard().setText(str(path))
                self.status.setText("Original file path copied.")
            else:
                if self.file_action(action, path) is False:
                    raise OSError("file-action-failed")
                self.status.setText("Opening the original file…" if action == "open" else "Showing the original in its folder…")
        except (OSError, ValueError, sqlite3.Error) as error:
            self.clear_preview()
            self.show_problem(error_copy(error))
        finally:
            if index:
                index.close()

    @staticmethod
    def _native_action(action, path):
        if action == "open":
            return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", "/select,", str(path)])
            return True
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def closeEvent(self, event):
        if self.issue_dialog:
            self.issue_dialog.issue_list.clear()
            self.issue_dialog.close()
        if self.thumbnail_tasks:
            self.closing = True
            for task in self.thumbnail_tasks:
                task.cancel.set()
            event.ignore()
            return
        if self.task and self.task.isRunning():
            self.closing = True
            self.cancel_work()
            event.ignore()
        else:
            if hasattr(self, "scope_timer"):
                self.scope_timer.stop()
                if self.scope_monitor:
                    self.scope_monitor.close()
            event.accept()


def main():
    parser = argparse.ArgumentParser(description="OmniFind Local desktop prototype")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OmniFindLocal/index.sqlite")
    parser.add_argument("--model", type=Path, default=Path("models/minilm"))
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    window = Window(args.db, args.model)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
