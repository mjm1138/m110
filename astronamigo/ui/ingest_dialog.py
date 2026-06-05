"""Ingest dialog — preview new captures, then move/copy them on confirmation.

Scanning and applying both run on background threads behind modal progress
dialogs (with Cancel), so a slow source (e.g. a Seestar over SMB) never freezes
the UI. Strictly preview-then-confirm: nothing is written to Images/ until the
user clicks Ingest and confirms.
"""
from __future__ import annotations

import threading
from collections import Counter

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView, QComboBox, QProgressDialog,
)

from astronamigo import config, ingest

KIND_LABEL = {"light": "light frame", "stack": "Seestar stack", "media": "media"}


class _ScanWorker(QThread):
    done = Signal(list)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, plan_fn, cancel_event, parent=None):
        super().__init__(parent)
        self._plan_fn = plan_fn
        self._cancel = cancel_event

    def run(self):
        try:
            ops = self._plan_fn(should_cancel=self._cancel.is_set)
            self.done.emit(ops)
        except ingest.IngestCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _ApplyWorker(QThread):
    progressed = Signal(int, int)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, ops, cancel_event, parent=None):
        super().__init__(parent)
        self._ops = ops
        self._cancel = cancel_event

    def run(self):
        try:
            res = ingest.apply_ops(
                self._ops,
                progress=lambda i, t: self.progressed.emit(i, t),
                should_cancel=self._cancel.is_set)
            self.done.emit(res)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class IngestDialog(QDialog):
    ingested = Signal(int)  # number of files moved/copied (main window refreshes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ingest")
        self.resize(780, 480)
        self._ops = []
        self._worker = None
        self._progress = None
        self._cancel_event = None

        lay = QVBoxLayout(self)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Source:"))
        self._source = QComboBox()
        self._source.addItem("Staging — From the scope", "staging")
        mw = config.find_seestar_myworks()
        if mw is not None:
            self._source.addItem(f"Seestar device — {mw.parent.name}", "seestar")
        self._source.currentIndexChanged.connect(self.scan)
        src_row.addWidget(self._source, 1)
        lay.addLayout(src_row)

        self._path_lbl = QLabel()
        self._path_lbl.setStyleSheet("color:#8b949e")
        lay.addWidget(self._path_lbl)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Kind", "From", "File", "→ Destination"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        lay.addWidget(self.table)

        self._summary = QLabel()
        lay.addWidget(self._summary)

        row = QHBoxLayout()
        self._rescan_btn = QPushButton("Rescan")
        self._rescan_btn.clicked.connect(self.scan)
        self._ingest_btn = QPushButton("Ingest")
        self._ingest_btn.clicked.connect(self._do_ingest)
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.reject)
        row.addWidget(self._rescan_btn)
        row.addStretch(1)
        row.addWidget(self._ingest_btn)
        row.addWidget(self._close_btn)
        lay.addLayout(row)

        # Defer the first scan until the dialog is on screen, so the scan's
        # progress modal appears over it rather than before it.
        QTimer.singleShot(0, self.scan)

    # ---- scan (threaded, read-only) ----
    def scan(self, *_):
        source = self._source.currentData()
        if source == "seestar":
            mw = config.find_seestar_myworks()
            self._path_lbl.setText(f"Seestar: {mw}  (files are copied; device left intact)")
            if mw is None:
                self._set_empty("No Seestar device mounted.")
                return
            self._start_scan(ingest.scan_seestar_plan, "Scanning Seestar…")
        else:
            staging = config.IMAGES_DIR / "From the scope"
            self._path_lbl.setText(f"Staging: {staging}  (files are moved)")
            if not ingest.staging_available():
                self._set_empty(f"Staging folder not found:\n{staging}")
                return
            self._start_scan(ingest.scan_staging_plan, "Scanning staging…")

    def _start_scan(self, plan_fn, label: str):
        self._set_busy(True)
        self._cancel_event = threading.Event()
        self._progress = QProgressDialog(label, "Cancel", 0, 0, self)  # 0,0 = busy
        self._progress.setWindowTitle("Scanning")
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.canceled.connect(self._cancel_event.set)
        self._worker = _ScanWorker(plan_fn, self._cancel_event, self)
        self._worker.done.connect(self._on_scan_done)
        self._worker.cancelled.connect(self._on_scan_cancelled)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()
        self._progress.show()

    def _on_scan_done(self, ops):
        self._close_progress()
        self._set_busy(False)
        self._ops = ops
        self._populate()

    def _on_scan_cancelled(self):
        self._close_progress()
        self._set_busy(False)
        self._set_empty("Scan cancelled.")

    def _on_scan_failed(self, msg):
        self._close_progress()
        self._set_busy(False)
        self._set_empty(f"Scan failed: {msg}")

    # ---- table / summary ----
    def _populate(self):
        self.table.setRowCount(len(self._ops))
        for r, op in enumerate(self._ops):
            label = KIND_LABEL.get(op.kind, op.kind)
            if op.new_object:
                label += "  (new object)"
            self.table.setItem(r, 0, QTableWidgetItem(label))
            self.table.setItem(r, 1, QTableWidgetItem(op.group))
            self.table.setItem(r, 2, QTableWidgetItem(op.src.rsplit("/", 1)[-1]))
            self.table.setItem(r, 3, QTableWidgetItem(op.dest_rel))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

        if self._ops:
            counts = Counter(op.kind for op in self._ops)
            parts = [f"{counts[k]} {KIND_LABEL[k]}{'s' if counts[k] != 1 else ''}"
                     for k in ("light", "stack", "media") if counts.get(k)]
            new_objs = sorted({op.group for op in self._ops if op.new_object})
            extra = f"  ·  new objects: {', '.join(new_objs)}" if new_objs else ""
            verb = "copy" if any(o.action == "copy" for o in self._ops) else "move"
            self._summary.setText(f"{len(self._ops)} new file(s) to {verb} — "
                                  f"{', '.join(parts)}{extra}")
            self._ingest_btn.setEnabled(True)
        else:
            self._summary.setText("Nothing new to ingest.")
            self._ingest_btn.setEnabled(False)

    def _set_empty(self, msg):
        self._ops = []
        self.table.setRowCount(0)
        self._summary.setText(msg)
        self._ingest_btn.setEnabled(False)

    def _set_busy(self, busy: bool):
        self._source.setEnabled(not busy)
        self._rescan_btn.setEnabled(not busy)
        if busy:
            self._ingest_btn.setEnabled(False)

    # ---- apply (threaded, writes Images/, gated) ----
    def _do_ingest(self):
        if not self._ops:
            return
        n = len(self._ops)
        verb = "Copy" if any(op.action == "copy" for op in self._ops) else "Move"
        new_objs = sorted({op.group for op in self._ops if op.new_object})
        msg = (f"{verb} {n} file(s) into the collection?\n\n"
               f"This writes into Images/ and cannot be undone from the app.")
        if verb == "Copy":
            msg += "\nFiles are copied; the Seestar device is left untouched."
        if new_objs:
            msg += f"\n\nNew object folder(s) will be created for: {', '.join(new_objs)}."
        if QMessageBox.question(self, "Confirm ingest", msg,
                                QMessageBox.Yes | QMessageBox.Cancel,
                                QMessageBox.Cancel) != QMessageBox.Yes:
            return

        self._set_busy(True)
        n = len(self._ops)
        self._cancel_event = threading.Event()
        self._progress = QProgressDialog(f"{verb}ing {n} file(s)…", "Cancel", 0, n, self)
        self._progress.setWindowTitle("Ingesting")
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.canceled.connect(self._cancel_event.set)
        self._worker = _ApplyWorker(list(self._ops), self._cancel_event, self)
        self._worker.progressed.connect(self._on_apply_progress)
        self._worker.done.connect(self._on_apply_done)
        self._worker.failed.connect(self._on_apply_failed)
        self._worker.start()
        self._progress.show()

    def _on_apply_progress(self, i, total):
        if self._progress:
            self._progress.setValue(i)

    def _on_apply_done(self, result: dict):
        self._close_progress()
        self._set_busy(False)
        moved = result.get("moved", 0)
        skipped = result.get("skipped", 0)
        cancelled = result.get("cancelled", False)
        self.ingested.emit(moved)
        bits = [f"{moved} file(s)"]
        if skipped:
            bits.append(f"{skipped} already present")
        note = "Ingest cancelled — " if cancelled else ""
        QMessageBox.information(self, "Ingest", f"{note}{', '.join(bits)}.")
        self.scan()  # re-scan (now-smaller) plan

    def _on_apply_failed(self, msg):
        self._close_progress()
        self._set_busy(False)
        QMessageBox.warning(self, "Ingest failed", msg)
        self._summary.setText(f"Ingest failed: {msg}")

    def _close_progress(self):
        if self._progress:
            self._progress.close()
            self._progress = None
