"""Ingest dialog — preview new staging captures, then move them on confirmation.

Strictly preview-then-confirm: scanning is read-only and runs on open; nothing
is written to Images/ until the user clicks Ingest and confirms. The move runs
on a background thread.
"""
from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView,
)

from astronamigo import config, ingest

KIND_LABEL = {"light": "light frame", "stack": "Seestar stack", "media": "media"}


class _ApplyWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, ops, parent=None):
        super().__init__(parent)
        self._ops = ops

    def run(self):
        try:
            self.done.emit(ingest.apply_ops(self._ops))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class IngestDialog(QDialog):
    ingested = Signal(int)  # number of files moved (so the main window can refresh)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ingest from staging")
        self.resize(760, 460)
        self._ops = []
        self._worker = None

        lay = QVBoxLayout(self)
        self._path_lbl = QLabel(f"Staging: {config.IMAGES_DIR / 'From the scope'}")
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

        self.scan()

    # ---- scan (read-only) ----
    def scan(self):
        if not ingest.staging_available():
            self._ops = []
            self._summary.setText(
                f"Staging folder not found:\n{config.IMAGES_DIR / 'From the scope'}")
            self.table.setRowCount(0)
            self._ingest_btn.setEnabled(False)
            return

        self._ops = ingest.scan_staging_plan()
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

        counts = Counter(op.kind for op in self._ops)
        if self._ops:
            parts = [f"{counts[k]} {KIND_LABEL[k]}{'s' if counts[k] != 1 else ''}"
                     for k in ("light", "stack", "media") if counts.get(k)]
            new_objs = sorted({op.group for op in self._ops if op.new_object})
            extra = f"  ·  new objects: {', '.join(new_objs)}" if new_objs else ""
            self._summary.setText(f"{len(self._ops)} new file(s) to ingest — "
                                  f"{', '.join(parts)}{extra}")
            self._ingest_btn.setEnabled(True)
        else:
            self._summary.setText("Nothing new to ingest.")
            self._ingest_btn.setEnabled(False)

    # ---- apply (writes Images/, gated) ----
    def _do_ingest(self):
        if not self._ops:
            return
        n = len(self._ops)
        new_objs = sorted({op.group for op in self._ops if op.new_object})
        msg = (f"Move {n} file(s) into the collection?\n\n"
               f"This writes into Images/ and cannot be undone from the app.")
        if new_objs:
            msg += f"\n\nNew object folder(s) will be created for: {', '.join(new_objs)}."
        if QMessageBox.question(self, "Confirm ingest", msg,
                                QMessageBox.Yes | QMessageBox.Cancel,
                                QMessageBox.Cancel) != QMessageBox.Yes:
            return

        self._ingest_btn.setEnabled(False)
        self._rescan_btn.setEnabled(False)
        self._summary.setText(f"Moving {n} file(s)…")
        self._worker = _ApplyWorker(list(self._ops), self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, result: dict):
        moved = result.get("moved", 0)
        skipped = result.get("skipped", 0)
        self.ingested.emit(moved)
        self._rescan_btn.setEnabled(True)
        skip_note = f", {skipped} already present" if skipped else ""
        QMessageBox.information(self, "Ingest complete",
                               f"Moved {moved} file(s){skip_note}.")
        self.scan()  # refresh the (now-empty) plan

    def _on_failed(self, msg: str):
        self._rescan_btn.setEnabled(True)
        self._ingest_btn.setEnabled(True)
        QMessageBox.warning(self, "Ingest failed", msg)
        self._summary.setText(f"Ingest failed: {msg}")
