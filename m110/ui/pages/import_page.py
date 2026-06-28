"""Import page — point at any directory, recurse, preview, then copy in (ROADMAP 6a).

The successor to the old Ingest dialog: a top-level page rather than a modal. You
pick a **source directory** (a device mount, another scope's export, an arbitrary
tree) from Favorites/Recent places or **Browse…**; the page recurses it
(`ingest.scan_directory_plan`), shows the familiar grouped/selectable preview, and
on confirm **copies** the selected groups into the collection (the source is left
untouched). Scanning and applying run on the shared workers behind modal progress
dialogs — strictly preview-then-confirm.
"""
from __future__ import annotations

import threading
from collections import Counter

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QProgressDialog,
    QFileDialog, QSplitter, QGroupBox,
)

from m110 import catalog, config, ingest
from m110.ui.ingest_dialog import (
    _ScanWorker, _ApplyWorker, _fmt_size, KIND_LABEL, ASSIGNABLE_KINDS,
)

RECENTS_KEY = "import_recents"
MAX_RECENTS = 8


class ImportPage(QWidget):
    imported = Signal(int)   # number of files copied in (the shell refreshes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = None            # the chosen source directory (str) or None
        self._groups = []
        self._holding_groups = []    # Inbox/ holding-area groups (6c)
        self._cat = {}               # catalog cache for the remap dropdown
        self._loading = False        # guards itemChanged while (re)populating
        self._worker = None
        self._progress = None
        self._cancel_event = None

        outer = QVBoxLayout(self)

        title = QLabel("<h2>Import</h2>")
        title.setTextFormat(Qt.RichText)
        outer.addWidget(title)

        # Top block (source picker + scan preview) and the holding-area panel share
        # a vertical splitter so the panel is always visible (6c).
        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 0)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Source:"))
        self._source = QComboBox()
        self._source.activated.connect(self._on_source_chosen)
        src_row.addWidget(self._source, 1)
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.clicked.connect(self._browse)
        src_row.addWidget(self._browse_btn)
        tv.addLayout(src_row)

        self._path_lbl = QLabel()
        self._path_lbl.setStyleSheet("color:#8b949e")
        tv.addWidget(self._path_lbl)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["", "Object", "Kind", "Files", "Size", "Pointing", "→ Destination"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        tv.addWidget(self.table, 1)

        self._summary = QLabel()
        tv.addWidget(self._summary)

        row = QHBoxLayout()
        self._rescan_btn = QPushButton("Rescan")
        self._rescan_btn.clicked.connect(self.scan)
        self._all_btn = QPushButton("Select all")
        self._all_btn.clicked.connect(lambda: self._set_all_checked(True))
        self._none_btn = QPushButton("Select none")
        self._none_btn.clicked.connect(lambda: self._set_all_checked(False))
        self._import_btn = QPushButton("Import")
        self._import_btn.clicked.connect(self._do_import)
        row.addWidget(self._rescan_btn)
        row.addWidget(self._all_btn)
        row.addWidget(self._none_btn)
        row.addStretch(1)
        row.addWidget(self._import_btn)
        tv.addLayout(row)

        split = QSplitter(Qt.Vertical)
        split.addWidget(top)
        split.addWidget(self._build_holding_panel())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)

        # Wait for a still-running worker before the app tears down — never destroy
        # a running QThread (Qt aborts). Mirrors MainWindow's guard.
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_worker)

        self.reload()

    # ---- source list (Favorites / Recent places) ----
    def reload(self):
        """Rebuild the source list (a freshly-mounted device shows up here). Does
        not auto-scan — scanning a big tree is modal, so it's user-initiated."""
        self._populate_sources()
        if self._root is None:
            self._set_empty("Choose a folder to import from "
                            "(a device, another scope's export, or any directory).")
        self.refresh_holding()

    def _places(self):
        """(label, path) entries: detected device(s) + the user's recent browse
        targets. The Inbox is the holding area now (6c), not a browse source."""
        places, seen = [], set()

        def add(label, path):
            if path and path not in seen:
                seen.add(path)
                places.append((label, path))

        mw = config.find_seestar_myworks()
        if mw is not None:
            add(f"Seestar device — {mw.parent.name}", str(mw))
        for p in config.get_setting(RECENTS_KEY, []) or []:
            add(f"Recent — {p}", p)
        return places

    def _populate_sources(self):
        cur = self._root
        self._source.blockSignals(True)
        self._source.clear()
        self._source.addItem("Choose a source…", None)
        for label, path in self._places():
            self._source.addItem(label, path)
        # keep the current selection if it's still in the list
        if cur is not None:
            i = self._source.findData(cur)
            if i >= 0:
                self._source.setCurrentIndex(i)
        self._source.blockSignals(False)

    def _on_source_chosen(self, _idx):
        path = self._source.currentData()
        if path:
            self._root = path
            self.scan()

    def _browse(self):
        start = self._root or str(config.DATA_ROOT)
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to import from", start)
        if not path:
            return
        self._remember_recent(path)
        self._root = path
        self._populate_sources()
        i = self._source.findData(path)
        if i >= 0:
            self._source.setCurrentIndex(i)
        self.scan()

    def _remember_recent(self, path: str):
        recents = [p for p in (config.get_setting(RECENTS_KEY, []) or []) if p != path]
        recents.insert(0, path)
        config.save_setting(RECENTS_KEY, recents[:MAX_RECENTS])

    # ---- scan (threaded, read-only) ----
    def scan(self, *_):
        if not self._root:
            return
        from pathlib import Path
        if not Path(self._root).is_dir():
            self._set_empty(f"Folder not found:\n{self._root}")
            return
        self._path_lbl.setText(f"{self._root}  (files are copied; the source is left untouched)")
        root = self._root
        self._set_busy(True)
        self._make_progress("Scanning…", 0, "Scanning")   # 0 max = indeterminate
        plan_fn = (lambda should_cancel=None, r=root:
                   ingest.scan_directory_plan(r, should_cancel=should_cancel))
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
            kind_item = QTableWidgetItem(KIND_LABEL.get(g.kind, g.kind))
            kind_item.setToolTip(f"Detected layout: {ingest.layout_label(g.layout)}")
            self.table.setItem(r, 2, kind_item)
            self.table.setItem(r, 3, QTableWidgetItem(str(g.frames)))
            self.table.setItem(r, 4, QTableWidgetItem(_fmt_size(g.size_bytes)))
            no_pointing = g.kind in ("media", "dark", "flat", "bias", "finished",
                                     "unassigned")
            point = g.pointing or ("—" if no_pointing else "✓")
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

    # ---- holding area (6c): manual assign of unclassifiable files ----
    def _build_holding_panel(self) -> QGroupBox:
        box = QGroupBox("Holding area")
        v = QVBoxLayout(box)
        self._holding_header = QLabel()
        self._holding_header.setStyleSheet("color:#8b949e")
        v.addWidget(self._holding_header)
        self.holding_table = QTableWidget(0, 6)
        self.holding_table.setHorizontalHeaderLabels(
            ["Source folder", "Files", "Size", "Object", "Kind", ""])
        self.holding_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.holding_table.verticalHeader().setVisible(False)
        self.holding_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        v.addWidget(self.holding_table, 1)
        return box

    def refresh_holding(self):
        """Rescan the Inbox/ holding area and repopulate the panel (synchronous —
        the holding area is local + small)."""
        try:
            self._holding_groups = ingest.group_ops(ingest.scan_holding())
        except Exception:
            self._holding_groups = []
        self._populate_holding()

    def _populate_holding(self):
        groups = self._holding_groups
        n = sum(g.frames for g in groups)
        if not groups:
            self._holding_header.setText(
                "Nothing held. Files the importer can't classify land here for "
                "manual assignment.")
        else:
            self._holding_header.setText(
                f"{n} file(s) awaiting assignment — pick an object + kind, then Assign.")
        self.holding_table.setRowCount(len(groups))
        for r, g in enumerate(groups):
            self.holding_table.setItem(r, 0, QTableWidgetItem(g.group))
            self.holding_table.setItem(r, 1, QTableWidgetItem(str(g.frames)))
            self.holding_table.setItem(r, 2, QTableWidgetItem(_fmt_size(g.size_bytes)))
            obj = QComboBox()
            obj.setEditable(True)               # allow new / off-catalog objects
            obj.addItem("— choose —")
            obj.addItems(self._catalog_ids())
            self.holding_table.setCellWidget(r, 3, obj)
            kind = QComboBox()
            for k in ASSIGNABLE_KINDS:
                kind.addItem(KIND_LABEL.get(k, k), k)
            self.holding_table.setCellWidget(r, 4, kind)
            btn = QPushButton("Assign")
            btn.clicked.connect(lambda _=False, idx=r: self._on_assign(idx))
            self.holding_table.setCellWidget(r, 5, btn)
        self.holding_table.resizeColumnsToContents()
        self.holding_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

    def _on_assign(self, row):
        if row >= len(self._holding_groups) or self.is_busy():
            return
        g = self._holding_groups[row]
        obj = self.holding_table.cellWidget(row, 3).currentText().strip()
        kind_combo = self.holding_table.cellWidget(row, 4)
        kind = kind_combo.currentData()
        if not obj or obj == "— choose —":
            QMessageBox.information(self, "Assign", "Choose an object first.")
            return
        assigned = ingest.assign(g, obj, kind)
        dest = assigned.dest_dir
        if QMessageBox.question(
                self, "Confirm assign",
                f"Move {assigned.frames} file(s) from the holding area into "
                f"{dest}?\n\nThis writes into the collection and moves the files "
                f"out of Inbox/.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Yes:
            return
        self._set_busy(True)
        self._make_progress("Moving files…", assigned.frames, "Assigning")
        self._worker = _ApplyWorker(assigned.ops, self._cancel_event, self)
        self._worker.progressed.connect(self._on_apply_progress)
        self._worker.done.connect(lambda res, grp=g, o=obj: self._on_assign_done(res, grp, o))
        self._worker.failed.connect(self._on_apply_failed)
        self._worker.start()
        self._progress.show()

    def _on_assign_done(self, result: dict, group, obj):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        moved = result.get("moved", 0)
        self.imported.emit(moved)
        if moved and QMessageBox.question(
                self, "Remember alias?",
                f"Always route “{group.group}” to {obj} on future imports?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            ingest.add_alias(group.group, obj)
        self.refresh_holding()

    def _set_object_cell(self, r, g):
        """Plain label, or a remap dropdown when the frame's pointing disagrees."""
        # Clear any stale label/combo first — setRowCount reuses rows across scans,
        # and setCellWidget/setItem don't remove each other, so a row switching
        # between label and dropdown would otherwise render both, overlapping.
        self.table.removeCellWidget(r, 1)
        self.table.takeItem(r, 1)
        if g.kind == "unassigned":
            # Held for the holding-area panel; not assigned inline here.
            self.table.setItem(r, 1, QTableWidgetItem("—"))
            return
        if g.pointing and g.kind != "media":
            combo = QComboBox()
            order = [g.object]
            self._catalog_ids()
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
                f"Always route “{g.group}” to {new_id} on future imports?",
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
            self._summary.setText("Nothing new to import.")
            self._import_btn.setEnabled(False)
            return
        groups = self._selected_groups()
        ops = [o for g in groups for o in g.ops]
        if not ops:
            self._summary.setText(f"0 of {len(self._groups)} object(s) selected.")
            self._import_btn.setEnabled(False)
            return
        counts = Counter(o.kind for o in ops)
        parts = [f"{counts[k]} {KIND_LABEL.get(k, k)}"
                 for k in ("light", "stack", "siril-stack", "dark", "flat",
                           "bias", "finished", "media")
                 if counts.get(k)]
        size = _fmt_size(sum(o.size_bytes for o in ops))
        new_objs = sorted({g.object for g in groups if g.new_object})
        extra = f"  ·  new: {', '.join(new_objs)}" if new_objs else ""
        self._summary.setText(f"{len(ops)} file(s) · {size} to copy "
                              f"({', '.join(parts)}){extra}")
        self._import_btn.setEnabled(True)

    def _set_empty(self, msg):
        self._groups = []
        self.table.setRowCount(0)
        self._summary.setText(msg)
        self._import_btn.setEnabled(False)

    def _set_busy(self, busy: bool):
        self._source.setEnabled(not busy)
        self._browse_btn.setEnabled(not busy)
        self._rescan_btn.setEnabled(not busy)
        self._all_btn.setEnabled(not busy)
        self._none_btn.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self.holding_table.setEnabled(not busy)
        if busy:
            self._import_btn.setEnabled(False)

    # ---- apply (threaded, writes Images/, gated) ----
    def _do_import(self):
        groups = self._selected_groups()
        ops = [o for g in groups for o in g.ops]
        if not ops:
            return
        n = len(ops)
        size = _fmt_size(sum(o.size_bytes for o in ops))
        new_objs = sorted({g.object for g in groups if g.new_object})
        msg = (f"Copy {n} file(s) ({size}) into the collection?\n\n"
               f"This writes into Images/ and cannot be undone from the app.\n"
               f"Files are copied; the source folder is left untouched.")
        if new_objs:
            msg += f"\n\nNew object folder(s) will be created for: {', '.join(new_objs)}."
        if QMessageBox.question(self, "Confirm import", msg,
                                QMessageBox.Yes | QMessageBox.Cancel,
                                QMessageBox.Cancel) != QMessageBox.Yes:
            return

        self._set_busy(True)
        self._make_progress("Copying files…", len(ops), "Importing")
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
        self.imported.emit(moved)
        self._groups = []
        self.table.setRowCount(0)
        self._import_btn.setEnabled(False)
        bits = [f"{moved} file(s) imported"]
        if skipped:
            bits.append(f"{skipped} already present")
        prefix = "Import cancelled — " if cancelled else ""
        self._summary.setText(prefix + ", ".join(bits)
                              + ".   Rescan to check for more.")
        self.refresh_holding()      # unclassified files may have landed in Inbox/

    def _on_apply_failed(self, msg):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        QMessageBox.warning(self, "Import failed", msg)
        self._summary.setText(f"Import failed: {msg}")

    # ---- progress + worker lifecycle ----
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

    def is_busy(self) -> bool:
        """True while a scan/import worker is running — the shell pauses its
        background refresh so `prepare_missing` can't race this page's autoprep
        on the same new sandbox."""
        return self._worker is not None

    def _stop_worker(self):
        if self._worker is not None:
            if self._cancel_event is not None:
                self._cancel_event.set()
            if self._worker.isRunning():
                self._worker.wait()
            self._worker.deleteLater()
            self._worker = None
