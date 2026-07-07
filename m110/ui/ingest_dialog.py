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

from m110 import catalog, config, ingest

KIND_LABEL = {
    "light": "lights", "stack": "Seestar stack", "media": "media",
    "dark": "darks", "flat": "flats", "bias": "biases",
    "siril-stack": "Siril stack", "finished": "finished",
    "preview": "sub previews", "unassigned": "→ holding area",
}

# Kinds a held file can be manually assigned to (6c), in dropdown order.
ASSIGNABLE_KINDS = ["light", "dark", "flat", "bias", "stack",
                    "siril-stack", "finished", "media"]


def _fmt_size(n: int) -> str:
    mb = n / (1024 ** 2)
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.0f} MB" if mb >= 1 else f"{n} B"


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
            groups = ingest.group_ops(ops)
            # Pointing reads one FITS frame per group — keep it on the worker.
            ingest.annotate_pointing(groups, should_cancel=self._cancel.is_set)
            self.done.emit(groups)
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
            # Auto-prep each target that gained lights for the enabled
            # processing workflow(s) (idempotent; skips targets with pending
            # finished output). Driven by the "Prepare objects for processing in:"
            # preference — no-op if the user disabled all workflows.
            if not res.get("cancelled"):
                from pathlib import Path
                from m110 import processing
                targets = sorted({Path(op.dest_rel).parts[1]
                                  for op in self._ops if op.kind == "light"
                                  and len(Path(op.dest_rel).parts) > 1})
                if targets:
                    processing.run_autoprep(targets, should_cancel=self._cancel.is_set)
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
        self._groups = []
        self._cat = {}               # catalog cache for the remap dropdown
        self._loading = False        # guards itemChanged while (re)populating
        self._worker = None
        self._progress = None
        self._cancel_event = None

        lay = QVBoxLayout(self)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Source:"))
        self._source = QComboBox()
        self._source.addItem("Staging — Inbox", "staging")
        mw = config.find_seestar_myworks()
        if mw is not None:
            self._source.addItem(f"Seestar device — {mw.parent.name}", "seestar")
        self._source.currentIndexChanged.connect(self.scan)
        src_row.addWidget(self._source, 1)
        lay.addLayout(src_row)

        self._path_lbl = QLabel()
        self._path_lbl.setProperty("muted", True)
        lay.addWidget(self._path_lbl)

        # One row per object/source folder, each selectable via a checkbox.
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["", "Object", "Kind", "Files", "Size", "Pointing", "→ Destination"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.table)

        self._summary = QLabel()
        lay.addWidget(self._summary)

        row = QHBoxLayout()
        self._rescan_btn = QPushButton("Rescan")
        self._rescan_btn.clicked.connect(self.scan)
        self._all_btn = QPushButton("Select all")
        self._all_btn.clicked.connect(lambda: self._set_all_checked(True))
        self._none_btn = QPushButton("Select none")
        self._none_btn.clicked.connect(lambda: self._set_all_checked(False))
        self._ingest_btn = QPushButton("Ingest")
        self._ingest_btn.clicked.connect(self._do_ingest)
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.reject)
        row.addWidget(self._rescan_btn)
        row.addWidget(self._all_btn)
        row.addWidget(self._none_btn)
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
            staging = config.STAGING_DIR
            self._path_lbl.setText(f"Staging: {staging}  (files are moved)")
            if not ingest.staging_available():
                self._set_empty(f"Staging folder not found:\n{staging}")
                return
            self._start_scan(ingest.scan_staging_plan, "Scanning staging…")

    def _start_scan(self, plan_fn, label: str):
        self._set_busy(True)
        self._make_progress(label, 0, "Scanning")  # 0 max = busy/indeterminate
        self._worker = _ScanWorker(plan_fn, self._cancel_event, self)
        self._worker.done.connect(self._on_scan_done)
        self._worker.cancelled.connect(self._on_scan_cancelled)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()
        self._progress.show()

    def _on_scan_done(self, groups):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        self._groups = groups
        self._populate()

    def _on_scan_cancelled(self):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        self._set_empty("Scan cancelled.")

    def _on_scan_failed(self, msg):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        self._set_empty(f"Scan failed: {msg}")

    # ---- table / summary ----
    def _populate(self):
        self._loading = True
        self.table.setRowCount(len(self._groups))
        for r, g in enumerate(self._groups):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked)
            chk.setData(Qt.UserRole, r)
            self.table.setItem(r, 0, chk)
            self._set_object_cell(r, g)
            self.table.setItem(r, 2, QTableWidgetItem(KIND_LABEL.get(g.kind, g.kind)))
            self.table.setItem(r, 3, QTableWidgetItem(str(g.frames)))
            self.table.setItem(r, 4, QTableWidgetItem(_fmt_size(g.size_bytes)))
            point = g.pointing or ("—" if g.kind == "media" else "✓")
            self.table.setItem(r, 5, QTableWidgetItem(point))
            self.table.setItem(r, 6, QTableWidgetItem(g.dest_dir))
        self._loading = False
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self._update_summary()

    def _catalog_ids(self):
        if not self._cat:
            try:
                self._cat = catalog.load_library()
            except Exception:
                self._cat = {}
        return sorted((e.get("id") or s) for s, e in self._cat.items())

    def _set_object_cell(self, r, g):
        """Plain label, or a remap dropdown when the frame's pointing disagrees."""
        if g.pointing and g.kind != "media":
            combo = QComboBox()
            order = [g.object]
            self._catalog_ids()   # ensure self._cat is loaded
            if g.suggested:
                sid = self._cat.get(g.suggested, {}).get("id") or g.suggested
                if sid not in order:
                    order.append(sid)
            for cid in self._catalog_ids():
                if cid not in order:
                    order.append(cid)
            combo.addItems(order)
            combo.currentTextChanged.connect(
                lambda txt, idx=r: self._on_remap(idx, txt))
            self.table.setCellWidget(r, 1, combo)
        else:
            obj = g.object + ("  (new)" if g.new_object else "")
            self.table.setItem(r, 1, QTableWidgetItem(obj))

    def _on_remap(self, idx, new_id):
        if self._loading:
            return
        g = self._groups[idx]
        if not new_id or new_id == g.object:
            return
        ng = ingest.retarget(g, new_id)
        self._groups[idx] = ng
        self.table.item(idx, 6).setText(ng.dest_dir)
        self.table.item(idx, 5).setText(f"→ {new_id}")
        self._update_summary()
        if QMessageBox.question(
                self, "Remember alias?",
                f"Always route “{g.group}” to {new_id} on future ingests?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            ingest.add_alias(g.group, new_id)

    def _selected_groups(self):
        out = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None and it.checkState() == Qt.Checked:
                out.append(self._groups[it.data(Qt.UserRole)])
        return out

    def _on_item_changed(self, item):
        if not self._loading and item.column() == 0:
            self._update_summary()

    def _set_all_checked(self, checked: bool):
        self._loading = True
        state = Qt.Checked if checked else Qt.Unchecked
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(state)
        self._loading = False
        self._update_summary()

    def _update_summary(self):
        if not self._groups:
            self._summary.setText("Nothing new to ingest.")
            self._ingest_btn.setEnabled(False)
            return
        groups = self._selected_groups()
        ops = [o for g in groups for o in g.ops]
        if not ops:
            self._summary.setText(f"0 of {len(self._groups)} object(s) selected.")
            self._ingest_btn.setEnabled(False)
            return
        counts = Counter(o.kind for o in ops)
        parts = [f"{counts[k]} {KIND_LABEL.get(k, k)}" for k in KIND_LABEL
                 if counts.get(k)]
        size = _fmt_size(sum(o.size_bytes for o in ops))
        verb = "copy" if any(o.action == "copy" for o in ops) else "move"
        new_objs = sorted({g.object for g in groups if g.new_object})
        extra = f"  ·  new: {', '.join(new_objs)}" if new_objs else ""
        self._summary.setText(f"{len(ops)} file(s) · {size} to {verb} "
                              f"({', '.join(parts)}){extra}")
        self._ingest_btn.setEnabled(True)

    def _set_empty(self, msg):
        self._ops = []
        self._groups = []
        self.table.setRowCount(0)
        self._summary.setText(msg)
        self._ingest_btn.setEnabled(False)

    def _set_busy(self, busy: bool):
        self._source.setEnabled(not busy)
        self._rescan_btn.setEnabled(not busy)
        self._all_btn.setEnabled(not busy)
        self._none_btn.setEnabled(not busy)
        self.table.setEnabled(not busy)
        if busy:
            self._ingest_btn.setEnabled(False)

    # ---- apply (threaded, writes Images/, gated) ----
    def _do_ingest(self):
        groups = self._selected_groups()
        ops = [o for g in groups for o in g.ops]
        if not ops:
            return
        n = len(ops)
        verb = "Copy" if any(op.action == "copy" for op in ops) else "Move"
        size = _fmt_size(sum(o.size_bytes for o in ops))
        new_objs = sorted({g.object for g in groups if g.new_object})
        msg = (f"{verb} {n} file(s) ({size}) into the collection?\n\n"
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
        label = "Copying files…" if verb == "Copy" else "Moving files…"
        self._make_progress(label, len(ops), "Ingesting")
        self._worker = _ApplyWorker(ops, self._cancel_event, self)
        self._worker.progressed.connect(self._on_apply_progress)
        self._worker.done.connect(self._on_apply_done)
        self._worker.failed.connect(self._on_apply_failed)
        self._worker.start()
        self._progress.show()

    def _on_apply_progress(self, i, total):
        if self._progress is not None:
            self._progress.setValue(i)

    def _on_apply_done(self, result: dict):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        moved = result.get("moved", 0)
        skipped = result.get("skipped", 0)
        cancelled = result.get("cancelled", False)
        self.ingested.emit(moved)
        # Do NOT auto-rescan: a fresh device scan here is slow and pops another
        # modal (the "modal won't close" report). Clear the consumed plan; the
        # user can Rescan to look for more.
        self._ops = []
        self._groups = []
        self.table.setRowCount(0)
        self._ingest_btn.setEnabled(False)
        bits = [f"{moved} file(s) ingested"]
        if skipped:
            bits.append(f"{skipped} already present")
        prefix = "Ingest cancelled — " if cancelled else ""
        self._summary.setText(prefix + ", ".join(bits)
                              + ".   Rescan to check for more, or Close.")

    def _on_apply_failed(self, msg):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        QMessageBox.warning(self, "Ingest failed", msg)
        self._summary.setText(f"Ingest failed: {msg}")

    # ---- progress + worker lifecycle ----
    def _make_progress(self, label, maximum, title):
        self._cancel_event = threading.Event()
        pd = QProgressDialog(label, "Cancel", 0, maximum, self)
        pd.setWindowTitle(title)
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setAutoClose(False)   # we close it explicitly in the done handler
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
        """Detach a finished worker (called from its own terminal slot)."""
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _stop_worker(self):
        """Cancel and wait for a still-running worker before we close — never
        destroy a running QThread (that crashes the app)."""
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
