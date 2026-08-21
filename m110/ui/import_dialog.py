"""Import-finished-work dialog — bring a workflow's output back into the Library.

After you process in a workflow's sandbox, M110 detects the finished outputs and
this dialog previews them: pick which renders/stacks to import (renders →
`finished/`, stack → `stacks/`), optionally choose a hero, and choose how to
clean the sandbox up. Strictly preview-then-confirm; the gated apply runs on a
worker thread behind modal progress with Cancel. Cleanup only ever *moves* files,
and never outside the workflow's own sandbox.

**Workflow-parameterised, not Siril-bound.** The dialog is handed a
`processing.Workflow` and talks to its `importer` — `siril` or `astrowizard`
(ROADMAP 14b) — so the wording, the sandbox it scans and the cleanup it offers
all follow the workflow rather than being hardcoded to one tool.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QProgressDialog, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QGroupBox,
)

from m110 import objects, processing, roundtrip


def _fmt_size(n: int) -> str:
    mb = n / (1024 ** 2)
    return f"{mb/1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


class _ScanWorker(QThread):
    done = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, target, importer, cancel_event, parent=None):
        super().__init__(parent)
        self._target = target
        self._importer = importer
        self._cancel = cancel_event

    def run(self):
        try:
            self.done.emit(self._importer.scan_finished(
                self._target, should_cancel=self._cancel.is_set))
        except roundtrip.Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _ImportWorker(QThread):
    progressed = Signal(int, int)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, args, importer, cancel_event, parent=None):
        super().__init__(parent)
        self._args = args
        self._importer = importer
        self._cancel = cancel_event

    def run(self):
        target, srcs, hero_src, hero_slug, cleanup = self._args
        try:
            res = self._importer.apply_import(
                target, srcs, hero_src=hero_src, hero_slug=hero_slug,
                cleanup=cleanup,
                progress=lambda i, t: self.progressed.emit(i, t),
                should_cancel=self._cancel.is_set)
            self.done.emit(res)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ImportDialog(QDialog):
    imported = Signal(str)   # target (main window refreshes)

    #: What "archive" keeps differs per workflow, because their *inputs* differ:
    #: Siril keeps the hardlinked lights/ and the preset, AstroWizard keeps the
    #: handed-off stack. Saying "keep lights/" in the AstroWizard dialog would
    #: name something that isn't there.
    _KEEPS = {
        "siril": "lights/ + preset",
        "astrowizard": "the handed-off stack",
    }

    def __init__(self, target: str, slug: str,
                 workflow=None, parent=None):
        super().__init__(parent)
        self._wf = workflow or processing.WORKFLOWS_BY_ID["siril"]
        self._importer = self._wf.importer
        self.setWindowTitle(f"Import finished work — {target} ({self._wf.label})")
        self.resize(720, 520)
        self._target = target
        self._slug = slug
        self._plan = None
        self._worker = None
        self._progress = None
        self._cancel_event = None
        keeps = self._KEEPS.get(self._wf.id, "this workflow's inputs")
        self._CLEANUP = [
            (f"Archive this run; keep {keeps} ready for another run", "archive"),
            ("Leave the sandbox as-is", "none"),
        ]

        lay = QVBoxLayout(self)
        self._info = QLabel(f"Scanning the {self._wf.label} sandbox…")
        self._info.setWordWrap(True)
        lay.addWidget(self._info)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Import", "Output", "Goes to", "Size"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)

        opts = QHBoxLayout()
        hero_box = QGroupBox("Hero image")
        hb = QVBoxLayout(hero_box)
        self._hero = QComboBox()
        hb.addWidget(self._hero)
        opts.addWidget(hero_box, 1)
        clean_box = QGroupBox("After import, clean up")
        cb = QVBoxLayout(clean_box)
        self._cleanup = QComboBox()
        for label, key in self._CLEANUP:
            self._cleanup.addItem(label, key)
        cb.addWidget(self._cleanup)
        opts.addWidget(clean_box, 1)
        lay.addLayout(opts)

        row = QHBoxLayout()
        self._import_btn = QPushButton("Import")
        self._import_btn.clicked.connect(self._do_import)
        self._import_btn.setEnabled(False)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(self._import_btn)
        row.addWidget(close_btn)
        lay.addLayout(row)

        # Cleanup default tracks the selection (auto), until the user picks one.
        self._loading = False
        self._cleanup_user_set = False
        self.table.itemChanged.connect(self._on_item_changed)
        self._cleanup.activated.connect(
            lambda *_: setattr(self, "_cleanup_user_set", True))

        QTimer.singleShot(0, self._scan)

    # ---- scan (threaded, read-only) ----
    def _scan(self):
        self._make_progress("Scanning sandbox…", 0, "Scanning")
        self._worker = _ScanWorker(self._target, self._importer, self._cancel_event, self)
        self._worker.done.connect(self._on_scan_done)
        self._worker.cancelled.connect(lambda: (self._finish_worker(), self._close_progress()))
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()
        self._progress.show()

    def _on_scan_done(self, plan):
        self._finish_worker()
        self._close_progress()
        self._plan = plan
        self._loading = True             # suppress itemChanged during population
        self.table.setRowCount(len(plan.items))
        for r, it in enumerate(plan.items):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if it.default else Qt.Unchecked)
            chk.setData(Qt.UserRole, it.src)
            if it.already:
                chk.setText(" already imported")
            self.table.setItem(r, 0, chk)
            self.table.setItem(r, 1, QTableWidgetItem(it.name))
            tier = "finished/" if it.kind == "render" else "stacks/"
            self.table.setItem(r, 2, QTableWidgetItem(
                f"{tier}  ({it.note})" if it.note else tier))
            self.table.setItem(r, 3, QTableWidgetItem(_fmt_size(it.size_bytes)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._loading = False
        self._sync_cleanup_default()

        self._hero.clear()
        fm, _ = objects.read_journal(self._slug)
        current = fm.get("hero")
        # None data → no change ("keep current" if one is set, else leave unset).
        self._hero.addItem(f"Keep current ({current})" if current else "(none)", None)
        for src in plan.hero_candidates:
            self._hero.addItem(Path(src).name, src)

        n_new = sum(1 for it in plan.items if not it.already)
        if plan.items:
            self._info.setText(
                f"Found {len(plan.items)} finished output(s) in the sandbox "
                f"({n_new} not yet imported). Renders go to <b>finished/</b>, "
                f"stacks to <b>stacks/</b>.")
            self._import_btn.setEnabled(True)
        else:
            self._info.setText(
                f"No finished outputs found in the sandbox yet. Process in "
                f"{self._wf.label} "
                "first (stack + render), then import.")
            self._import_btn.setEnabled(False)

    def _on_scan_failed(self, msg):
        self._finish_worker()
        self._close_progress()
        self._info.setText(f"Scan failed: {msg}")

    def _checked_srcs(self):
        out = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item.checkState() == Qt.Checked:
                out.append(item.data(Qt.UserRole))
        return out

    def _has_deselected_new(self) -> bool:
        """True if any not-yet-imported output is left unchecked — archiving would
        sweep it into archive/, so 'leave as-is' is the safer default then."""
        if not self._plan:
            return False
        for r, it in enumerate(self._plan.items):
            if not it.already and self.table.item(r, 0).checkState() != Qt.Checked:
                return True
        return False

    def _on_item_changed(self, item):
        if self._loading or item.column() != 0:
            return
        self._sync_cleanup_default()

    def _sync_cleanup_default(self):
        # Once the user explicitly picks a cleanup option, stop steering it.
        if self._cleanup_user_set:
            return
        key = "none" if self._has_deselected_new() else "archive"
        i = self._cleanup.findData(key)
        if i >= 0:
            self._cleanup.setCurrentIndex(i)

    # ---- apply (threaded, gated) ----
    def _do_import(self):
        srcs = self._checked_srcs()
        cleanup = self._cleanup.currentData()
        if not srcs and cleanup == "none":
            return
        hero_src = self._hero.currentData()
        msg = f"Import {len(srcs)} output(s) into the Library?"
        keeps_now = self._KEEPS.get(self._wf.id, "this workflow's inputs")
        if cleanup == "archive":
            msg += ("\n\nThis run's output + intermediates will then be moved into "
                    f"{self._wf.id}/archive/; {keeps_now} stay(s) ready for "
                    "another run. Nothing is deleted.")
        if QMessageBox.question(self, "Confirm import", msg,
                                QMessageBox.Yes | QMessageBox.Cancel,
                                QMessageBox.Cancel) != QMessageBox.Yes:
            return
        self._import_btn.setEnabled(False)
        self._make_progress("Importing…", len(srcs), "Importing")
        args = (self._target, srcs, hero_src, self._slug, cleanup)
        self._worker = _ImportWorker(args, self._importer, self._cancel_event, self)
        self._worker.progressed.connect(
            lambda i, t: self._progress.setValue(i) if self._progress else None)
        self._worker.done.connect(self._on_import_done)
        self._worker.failed.connect(self._on_import_failed)
        self._worker.start()
        self._progress.show()

    def _on_import_done(self, res: dict):
        self._finish_worker()
        self._close_progress()
        self.imported.emit(self._target)   # main window refreshes the Library
        self.accept()                      # self-close once the import is done

    def _on_import_failed(self, msg):
        self._finish_worker()
        self._close_progress()
        self._import_btn.setEnabled(True)
        QMessageBox.warning(self, "Import failed", msg)

    # ---- progress + worker lifecycle (same pattern as ingest) ----
    def _make_progress(self, label, maximum, title):
        self._cancel_event = threading.Event()
        pd = QProgressDialog(label, "Cancel", 0, maximum, self)
        pd.setWindowTitle(title)
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.canceled.connect(self._cancel_event.set)
        self._progress = pd
        return pd

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
