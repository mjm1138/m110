"""Import-finished-work dialog — bring Siril output back into the Library.

After you process in the `siril/` sandbox, M110 detects the finished outputs and
this dialog previews them: pick which renders/stacks to import (renders →
`finished/`, stack → `stacks/`), optionally choose a hero, and choose how to
clean the sandbox up. Strictly preview-then-confirm; the gated apply runs on a
worker thread behind modal progress with Cancel. Destructive cleanup is scoped to
`Images/<target>/siril/` and defaults to the always-safe lights-only removal.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QProgressDialog, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QGroupBox,
)

from m110 import siril


def _fmt_size(n: int) -> str:
    mb = n / (1024 ** 2)
    return f"{mb/1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


class _ScanWorker(QThread):
    done = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, target, cancel_event, parent=None):
        super().__init__(parent)
        self._target = target
        self._cancel = cancel_event

    def run(self):
        try:
            self.done.emit(siril.scan_finished(self._target,
                                               should_cancel=self._cancel.is_set))
        except siril.PrepCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _ImportWorker(QThread):
    progressed = Signal(int, int)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, args, cancel_event, parent=None):
        super().__init__(parent)
        self._args = args
        self._cancel = cancel_event

    def run(self):
        target, srcs, hero_src, hero_slug, cleanup = self._args
        try:
            res = siril.apply_import(
                target, srcs, hero_src=hero_src, hero_slug=hero_slug,
                cleanup=cleanup,
                progress=lambda i, t: self.progressed.emit(i, t),
                should_cancel=self._cancel.is_set)
            self.done.emit(res)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ImportDialog(QDialog):
    imported = Signal(str)   # target (main window refreshes)

    _CLEANUP = [
        ("Remove the hardlinked lights/ only (safe — originals kept)", "lights"),
        ("Remove the whole siril/ sandbox", "all"),
        ("Leave the sandbox as-is", "none"),
    ]

    def __init__(self, target: str, slug: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Import finished work — {target}")
        self.resize(720, 520)
        self._target = target
        self._slug = slug
        self._plan = None
        self._worker = None
        self._progress = None
        self._cancel_event = None

        lay = QVBoxLayout(self)
        self._info = QLabel("Scanning the Siril sandbox…")
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

        QTimer.singleShot(0, self._scan)

    # ---- scan (threaded, read-only) ----
    def _scan(self):
        self._make_progress("Scanning sandbox…", 0, "Scanning")
        self._worker = _ScanWorker(self._target, self._cancel_event, self)
        self._worker.done.connect(self._on_scan_done)
        self._worker.cancelled.connect(lambda: (self._finish_worker(), self._close_progress()))
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()
        self._progress.show()

    def _on_scan_done(self, plan):
        self._finish_worker()
        self._close_progress()
        self._plan = plan
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
            self.table.setItem(r, 2, QTableWidgetItem(tier))
            self.table.setItem(r, 3, QTableWidgetItem(_fmt_size(it.size_bytes)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self._hero.clear()
        self._hero.addItem("(none)", None)
        for src in plan.hero_candidates:
            from pathlib import Path
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
                "No finished outputs found in the sandbox yet. Process in Siril "
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

    # ---- apply (threaded, gated) ----
    def _do_import(self):
        srcs = self._checked_srcs()
        cleanup = self._cleanup.currentData()
        if not srcs and cleanup == "none":
            return
        hero_src = self._hero.currentData()
        msg = f"Import {len(srcs)} output(s) into the Library?"
        if cleanup == "all":
            msg += ("\n\nThis will then DELETE the entire siril/ sandbox, including "
                    "any un-imported intermediates. This can't be undone.")
        elif cleanup == "lights":
            msg += ("\n\nThe hardlinked lights/ will be removed afterward "
                    "(your originals in lights/ are untouched).")
        if QMessageBox.question(self, "Confirm import", msg,
                                QMessageBox.Yes | QMessageBox.Cancel,
                                QMessageBox.Cancel) != QMessageBox.Yes:
            return
        self._import_btn.setEnabled(False)
        self._make_progress("Importing…", len(srcs), "Importing")
        args = (self._target, srcs, hero_src, self._slug, cleanup)
        self._worker = _ImportWorker(args, self._cancel_event, self)
        self._worker.progressed.connect(
            lambda i, t: self._progress.setValue(i) if self._progress else None)
        self._worker.done.connect(self._on_import_done)
        self._worker.failed.connect(self._on_import_failed)
        self._worker.start()
        self._progress.show()

    def _on_import_done(self, res: dict):
        self._finish_worker()
        self._close_progress()
        self.imported.emit(self._target)
        bits = [f"{res.get('imported', 0)} imported"]
        if res.get("skipped"):
            bits.append(f"{res['skipped']} already present")
        clean = {"lights": "lights/ removed", "all": "sandbox removed",
                 "none": "sandbox kept"}.get(res.get("cleaned"), "")
        self._info.setText(", ".join(bits) + (f"; {clean}." if clean else "."))
        # refresh the view (re-scan what remains)
        QTimer.singleShot(0, self._scan)

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
