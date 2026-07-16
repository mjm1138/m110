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
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton,
    QVBoxLayout,
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
_GH_REPO_KEY = "publish_github_repo"
_GH_MODE_KEY = "publish_github_deploy_mode"
# Combo order = engine mode order (publish.ghpages.DEPLOY_MODES).
_DEPLOY_MODES = [
    ("replace", "Replace the site each time (smallest repo)"),
    ("incremental", "Upload only what changed (keeps history)"),
]
_GALLERY_LEVEL_KEY = "publish_gallery_level"
# Combo order = engine level order (publish.images.GALLERY_LEVELS).
_GALLERY_LEVELS = [
    ("finished", "Finished images only"),
    ("device-stacks", "Finished + device stacks"),
    ("all", "All images (working files too)"),
]


class _PublishWorker(QThread):
    progressed = Signal(int, int)
    status = Signal(str)
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
                progress=lambda i, t: self.progressed.emit(i, t),
                status=self.status.emit)
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
            "Render a static website of your collection to a local folder, "
            "and optionally deploy it straight to GitHub Pages."))

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
        # Gallery level rides under "Image galleries" (the last section row) —
        # working files dominate the site's size/upload time, so the default
        # publishes deliberate deliverables only.
        lvl_row = QHBoxLayout()
        lvl_row.addSpacing(s["lg"])
        self._gallery_level = QComboBox()
        for lid, label in _GALLERY_LEVELS:
            self._gallery_level.addItem(label, lid)
        saved_level = config.get_setting(_GALLERY_LEVEL_KEY, "finished")
        idx = next((i for i, (lid, _) in enumerate(_GALLERY_LEVELS)
                    if lid == saved_level), 0)
        self._gallery_level.setCurrentIndex(idx)
        gal_cb = self._sec_checks["galleries"]
        self._gallery_level.setEnabled(gal_cb.isChecked())
        gal_cb.toggled.connect(self._gallery_level.setEnabled)
        lvl_row.addWidget(self._gallery_level)
        lvl_row.addStretch(1)
        sec_l.addLayout(lvl_row)
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
            if p.id == "github-pages":
                # Repository field, indented under its checkbox and only live
                # while the target is selected. The branch is the gh-pages
                # convention (not a knob).
                repo_row = QHBoxLayout()
                repo_row.addSpacing(s["lg"])
                repo_row.addWidget(QLabel("Repository:"))
                self._gh_repo = QLineEdit(str(config.get_setting(_GH_REPO_KEY, "")))
                self._gh_repo.setPlaceholderText("owner/repo or git URL")
                self._gh_repo.setEnabled(cb.isChecked())
                cb.toggled.connect(self._gh_repo.setEnabled)
                repo_row.addWidget(self._gh_repo)
                tgt_l.addLayout(repo_row)
                # Upload mode: replace re-uploads the whole site every publish
                # but keeps the repo lean; incremental sends only changed
                # objects at the cost of an ever-growing history.
                mode_row = QHBoxLayout()
                mode_row.addSpacing(s["lg"])
                mode_row.addWidget(QLabel("Uploads:"))
                self._gh_mode = QComboBox()
                for mid, label in _DEPLOY_MODES:
                    self._gh_mode.addItem(label, mid)
                saved_mode = config.get_setting(_GH_MODE_KEY, "replace")
                self._gh_mode.setCurrentIndex(
                    next((i for i, (mid, _) in enumerate(_DEPLOY_MODES)
                          if mid == saved_mode), 0))
                self._gh_mode.setEnabled(cb.isChecked())
                cb.toggled.connect(self._gh_mode.setEnabled)
                mode_row.addWidget(self._gh_mode)
                mode_row.addStretch(1)
                tgt_l.addLayout(mode_row)
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
        # Save persists every choice without publishing (mirrors backup_dialog).
        save_btn = buttons.addButton("Save", QDialogButtonBox.ActionRole)
        save_btn.clicked.connect(self._do_save)
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
    def _save_settings(self, targets):
        """Persist every dialog choice (targets take effect via the setting key)."""
        config.save_setting(publish.SETTING_KEY, targets)
        config.save_setting(_OUTPUT_KEY, self._out_edit.text().strip())
        config.save_setting(_SECTIONS_KEY, sorted(self._selected_sections()))
        config.save_setting(_EXCLUDE_KEY, self._exclude_journals.isChecked())
        config.save_setting(_GALLERY_LEVEL_KEY, self._gallery_level.currentData())
        config.save_setting(_TITLE_KEY,
                            self._title.text().strip() or publish.DEFAULT_SITE_TITLE)
        config.save_setting(_GH_REPO_KEY, self._gh_repo.text().strip())
        config.save_setting(_GH_MODE_KEY, self._gh_mode.currentData())

    def _do_save(self):
        self._save_settings(self._selected_targets())
        self.accept()

    def _do_publish(self):
        out = self._out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, "Publish", "Choose an output folder.")
            return
        targets = self._selected_targets()
        if not targets:
            QMessageBox.warning(self, "Publish", "Choose at least one target.")
            return
        gh_repo = self._gh_repo.text().strip()
        if "github-pages" in targets and not gh_repo:
            QMessageBox.warning(
                self, "Publish",
                "Enter the GitHub repository to deploy to (owner/repo or a "
                "git URL).")
            return

        self._save_settings(targets)
        options = PublishOptions(
            output_dir=Path(out), sections=self._selected_sections(),
            exclude_journals=self._exclude_journals.isChecked(),
            site_title=self._title.text().strip() or publish.DEFAULT_SITE_TITLE,
            gallery_level=self._gallery_level.currentData(),
            github_repo=gh_repo,
            github_deploy_mode=self._gh_mode.currentData())

        self._cancel_event = threading.Event()
        pd = QProgressDialog("Rendering site…", "Cancel", 0, 0, self)
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
        self._worker.status.connect(self._on_status)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        pd.show()

    def _on_progress(self, i, total):
        if self._progress is not None:
            self._progress.setMaximum(total)
            self._progress.setValue(i)

    def _on_status(self, text):
        # New stage → new label, and the bar resets to busy until that stage
        # reports its own (i, total) — so "Uploading to GitHub…" never sits on a
        # stale 100% from the render phase.
        if self._progress is not None:
            self._progress.setLabelText(text)
            self._progress.setMaximum(0)
            self._progress.setValue(0)

    def _on_done(self, result):
        self._finish_worker()
        self._close_progress()
        if self._cancel_event and self._cancel_event.is_set():
            self.reject()
            return
        self.published.emit(result)
        sub = result.get("static-site") or next(iter(result.values()), {})
        out_dir = sub.get("output_dir", "")
        gh = result.get("github-pages") or {}
        text = f"Published {sub.get('pages', gh.get('pages', 0))} pages to:\n{out_dir}"
        if gh:
            where = gh.get("url") or gh.get("repo", "")
            text += (f"\n\nDeployed to GitHub Pages:\n{where}\n"
                     "(the site can take a minute or two to update)")
        msg = QMessageBox(self)
        msg.setWindowTitle("Published")
        msg.setText(text)
        open_btn = msg.addButton("Open folder", QMessageBox.AcceptRole)
        site_btn = (msg.addButton("Open site", QMessageBox.AcceptRole)
                    if gh.get("url") else None)
        msg.addButton("Close", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() is open_btn and out_dir:
            self._open_folder(out_dir)
        elif site_btn is not None and msg.clickedButton() is site_btn:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(gh["url"]))
        self.accept()

    def _on_failed(self, message):
        self._finish_worker()
        self._close_progress()
        if self._cancel_event is not None and self._cancel_event.is_set():
            # User cancelled — the engine reports it as an error, but it isn't
            # one worth a dialog. Leave the window open for another go.
            self._publish_btn.setEnabled(True)
            return
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
