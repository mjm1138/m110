"""Publish / share dialog — pick sections + targets + an output folder, then run
the publisher(s) on a worker thread behind a modal progress dialog.

Mirrors the threaded plan/apply pattern of `import_dialog.py`: a `_PublishWorker`
(QThread) emits progress/done/failed, a `threading.Event` backs Cancel, and the
worker is torn down safely on close. Selection persists to settings for next time.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton, QVBoxLayout,
)

from m110 import config, publish
from m110.publish.options import ALL_SECTIONS, PublishOptions

# Human labels for the section ids (order = display order).
_SECTION_LABELS = [
    ("library", "Full catalog table"),
    ("summary", "Summary dashboard"),
    ("sessions", "Session log"),
    ("processing", "Processing queue"),
    ("journal", "Journal notes"),
    ("galleries", "Image galleries"),
]

_OUTPUT_KEY = "publish_output_dir"
_SECTIONS_KEY = "publish_sections"
_EXCLUDE_KEY = "publish_exclude_journals"
_TITLE_KEY = "publish_site_title"


class _PublishWorker(QThread):
    progressed = Signal(int, int)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, options, cancel_event, parent=None):
        super().__init__(parent)
        self._options = options
        self._cancel = cancel_event

    def run(self):
        try:
            res = publish.run_publish(
                self._options,
                should_cancel=self._cancel.is_set,
                progress=lambda i, t: self.progressed.emit(i, t))
            self.done.emit(res)
        except publish.PublishError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class PublishDialog(QDialog):
    published = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Publish / share")
        self._worker = None
        self._progress = None
        self._cancel_event = None
        self.resize(520, 0)

        from m110.ui.theme import tokens
        s = tokens.SPACE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s["lg"], s["lg"], s["lg"], s["lg"])
        layout.setSpacing(s["md"])
        layout.addWidget(QLabel(
            "Render a static website of your collection to a local folder. "
            "Push or host the folder yourself."))

        # ── what to publish ──
        sec_box = QGroupBox("Include")
        sec_l = QVBoxLayout(sec_box)
        saved_sections = config.get_setting(_SECTIONS_KEY, None)
        enabled = set(saved_sections) if isinstance(saved_sections, list) else set(ALL_SECTIONS)
        self._sec_checks = {}
        for sid, label in _SECTION_LABELS:
            cb = QCheckBox(label)
            cb.setChecked(sid in enabled)
            sec_l.addWidget(cb)
            self._sec_checks[sid] = cb
        self._exclude_journals = QCheckBox("Exclude all journal notes (privacy)")
        self._exclude_journals.setChecked(bool(config.get_setting(_EXCLUDE_KEY, False)))
        sec_l.addWidget(self._exclude_journals)
        layout.addWidget(sec_box)

        # ── targets ──
        tgt_box = QGroupBox("Publish to")
        tgt_l = QVBoxLayout(tgt_box)
        enabled_targets = set(publish.enabled_target_ids())
        self._tgt_checks = {}
        for p in publish.PUBLISHERS:
            cb = QCheckBox(p.label if p.available else f"{p.label}  (soon)")
            cb.setEnabled(p.available)
            cb.setChecked(p.available and p.id in enabled_targets)
            tgt_l.addWidget(cb)
            self._tgt_checks[p.id] = cb
        layout.addWidget(tgt_box)

        # ── site title ──
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Site title:"))
        self._title = QLineEdit(str(config.get_setting(_TITLE_KEY, publish.DEFAULT_SITE_TITLE)))
        title_row.addWidget(self._title)
        layout.addLayout(title_row)

        # ── output folder ──
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output folder:"))
        default_out = config.get_setting(
            _OUTPUT_KEY, str(Path.home() / "Documents" / "M110 Site"))
        self._out_edit = QLineEdit(str(default_out))
        out_row.addWidget(self._out_edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        out_row.addWidget(browse)
        layout.addLayout(out_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self._publish_btn = buttons.addButton("Publish", QDialogButtonBox.AcceptRole)
        self._publish_btn.clicked.connect(self._do_publish)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---- helpers ----
    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose output folder",
                                             self._out_edit.text())
        if d:
            self._out_edit.setText(d)

    def _selected_sections(self) -> set[str]:
        return {sid for sid, cb in self._sec_checks.items() if cb.isChecked()}

    def _selected_targets(self) -> list[str]:
        return [tid for tid, cb in self._tgt_checks.items()
                if cb.isEnabled() and cb.isChecked()]

    # ---- run ----
    def _do_publish(self):
        out = self._out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, "Publish", "Choose an output folder.")
            return
        targets = self._selected_targets()
        if not targets:
            QMessageBox.warning(self, "Publish", "Choose at least one target.")
            return

        sections = self._selected_sections()
        exclude_journals = self._exclude_journals.isChecked()
        title = self._title.text().strip() or publish.DEFAULT_SITE_TITLE
        # Persist choices for next time (targets take effect via the setting key).
        config.save_setting(publish.SETTING_KEY, targets)
        config.save_setting(_OUTPUT_KEY, out)
        config.save_setting(_SECTIONS_KEY, sorted(sections))
        config.save_setting(_EXCLUDE_KEY, exclude_journals)
        config.save_setting(_TITLE_KEY, title)

        options = PublishOptions(output_dir=Path(out), sections=sections,
                                 exclude_journals=exclude_journals, site_title=title)

        self._cancel_event = threading.Event()
        pd = QProgressDialog("Publishing…", "Cancel", 0, 0, self)
        pd.setWindowTitle("Publishing")
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.canceled.connect(self._cancel_event.set)
        self._progress = pd

        self._publish_btn.setEnabled(False)
        self._worker = _PublishWorker(options, self._cancel_event, self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        pd.show()

    def _on_progress(self, i, total):
        if self._progress is not None:
            self._progress.setMaximum(total)
            self._progress.setValue(i)

    def _on_done(self, result):
        self._finish_worker()
        self._close_progress()
        if self._cancel_event and self._cancel_event.is_set():
            self.reject()
            return
        self.published.emit(result)
        sub = result.get("static-site") or next(iter(result.values()), {})
        out_dir = sub.get("output_dir", "")
        msg = QMessageBox(self)
        msg.setWindowTitle("Published")
        msg.setText(f"Published {sub.get('pages', 0)} pages to:\n{out_dir}")
        open_btn = msg.addButton("Open folder", QMessageBox.AcceptRole)
        msg.addButton("Close", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() is open_btn and out_dir:
            self._open_folder(out_dir)
        self.accept()

    def _on_failed(self, message):
        self._finish_worker()
        self._close_progress()
        QMessageBox.warning(self, "Publish failed", message)
        self._publish_btn.setEnabled(True)

    @staticmethod
    def _open_folder(path: str):
        import subprocess
        import sys
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform.startswith("win"):
                import os
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    # ---- teardown ----
    def _close_progress(self):
        if self._progress is not None:
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None

    def _finish_worker(self):
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _stop_worker(self):
        if self._worker is not None:
            if self._cancel_event is not None:
                self._cancel_event.set()
            if self._worker.isRunning():
                self._worker.wait()
            self._worker.deleteLater()
            self._worker = None

    def reject(self):
        self._stop_worker()
        self._close_progress()
        super().reject()

    def closeEvent(self, event):
        self._stop_worker()
        self._close_progress()
        super().closeEvent(event)
