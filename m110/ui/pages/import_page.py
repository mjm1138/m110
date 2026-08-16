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

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QProgressDialog,
    QFileDialog, QSplitter, QGroupBox,
)

from m110 import catalog, config, ingest
from m110.ui import theme
from m110.ui.ingest_dialog import (
    _ScanWorker, _ApplyWorker, _fmt_size, KIND_LABEL, ASSIGNABLE_KINDS,
)
from m110.ui.widgets import fit_cell_widgets

RECENTS_KEY = "import_recents"
MAX_RECENTS = 8


class ImportPage(QWidget):
    imported = Signal(int)   # number of files copied in (the shell refreshes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = None            # the chosen source directory (str) or None
        self._groups = []
        self._holding_groups = []    # Inbox/ holding-area groups (6c)
        self._holding_info = []      # per-group identification aids (#26)
        self._cat = {}               # catalog cache for the remap dropdown
        self._loading = False        # guards itemChanged while (re)populating
        self._worker = None
        self._progress = None
        self._cancel_event = None
        self._post_import_msg = None   # confirmation shown after the post-import rescan

        outer = QVBoxLayout(self)

        title = QLabel("<h2>Import</h2>")
        title.setTextFormat(Qt.RichText)
        outer.addWidget(title)

        # Top block (source picker + scan preview) and the holding-area panel share
        # a vertical splitter so the panel is always visible (6c).
        s = theme.tokens.SPACE
        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, s["sm"])   # keep the button row off the splitter handle

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
        self._path_lbl.setProperty("muted", True)
        self._path_lbl.setWordWrap(True)       # a long path mustn't force window width (#63)
        tv.addWidget(self._path_lbl)

        # A persistent scan-result headline (what the recursive scan found), set on
        # each scan and independent of the selection-driven `_summary` below — so
        # "where did my files go?" is always answerable, incl. files sent to holding
        # (#32).
        self._scan_note = QLabel()
        self._scan_note.setProperty("caption", True)
        self._scan_note.setWordWrap(True)
        tv.addWidget(self._scan_note)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["", "Object", "Kind", "Files", "Size", "Pointing", "→ Destination"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        tv.addWidget(self.table, 1)

        self._summary = QLabel()
        self._summary.setWordWrap(True)        # don't let a long line force window width (#63)
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
        # Give the holding panel a real default height (it was cramped) and keep it
        # from collapsing on resize. setSizes scales proportionally to actual height.
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        split.setSizes([480, 320])
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
        plan_fn = (lambda should_cancel=None, progress=None, r=root:
                   ingest.scan_directory_plan(r, should_cancel=should_cancel,
                                              progress=progress))
        self._worker = _ScanWorker(plan_fn, self._cancel_event, self)
        self._worker.done.connect(self._on_scan_done)
        self._worker.cancelled.connect(self._on_scan_cancelled)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.progressed.connect(self._on_scan_progress)
        self._worker.start()
        self._progress.show()

    def _on_scan_progress(self, text: str):
        if self._progress is not None:
            self._progress.setLabelText(text)

    def _on_scan_done(self, groups):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        self._groups = groups
        self._populate()
        self._set_scan_note(groups)
        if self._post_import_msg:    # confirm the import, then show what's left
            tail = (f"  {self._summary.text()}" if self._groups
                    else "  Nothing left to import.")
            self._summary.setText(self._post_import_msg + tail)
            self._post_import_msg = None

    def _set_scan_note(self, groups):
        """Headline what the (recursive) scan found — object/file counts, and how
        many files couldn't be identified and will go to the holding area — so a
        surprising result (nothing found, or everything held) is explained (#32)."""
        ops = [o for g in groups for o in g.ops]
        summ = ingest.scan_summary(ops)
        if summ["total"] == 0:
            self._scan_note.setText(
                "No importable files were found in this folder or its subfolders. "
                "M110 scans every subfolder for FITS (.fit/.fits) and images; check "
                "that the source contains capture files.")
            return
        bits = [f"Found {summ['objects']} object(s), {summ['to_import']} file(s) "
                f"to import"]
        if summ["to_holding"]:
            bits.append(
                f"{summ['to_holding']} file(s) couldn't be identified → sent to the "
                f"holding area below for manual assignment")
        self._scan_note.setText(".  ".join(bits) + ".")

    def _on_scan_cancelled(self):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        self._post_import_msg = None
        self._set_empty("Scan cancelled.")

    def _on_scan_failed(self, msg):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        self._post_import_msg = None
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
        # Column 1 carries a remap combo on mis-pointed rows (#12) — measure it, or
        # it's clipped the same way the holding-area buttons were.
        fit_cell_widgets(self.table, 1)
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
        self._holding_header.setProperty("muted", True)
        self._holding_header.setWordWrap(True)   # don't let the (now longer) header
                                                 # force the window minimum width
        v.addWidget(self._holding_header)
        self.holding_table = QTableWidget(0, 6)
        self.holding_table.setHorizontalHeaderLabels(
            ["Source folder", "Files", "Size", "Object", "Kind", "Actions"])
        self.holding_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.holding_table.verticalHeader().setVisible(False)
        self.holding_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        # Row multi-select (#33): click the Source/Files/Size cells; Ctrl/Shift extend.
        # (The Object/Kind/Actions cells host widgets, so selection is driven from the
        # left cells — the bulk bar below assigns every selected row at once.)
        self.holding_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.holding_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.holding_table.itemSelectionChanged.connect(self._update_bulk_bar)
        self.holding_table.cellDoubleClicked.connect(self._on_holding_inspect)   # #26
        v.addWidget(self.holding_table, 1)
        v.addLayout(self._build_bulk_bar())
        return box

    def _build_bulk_bar(self) -> QHBoxLayout:
        """A row to assign **all selected** held rows to one object/kind at once
        (#33 — working the holding area row-by-row is tedious)."""
        from PySide6.QtWidgets import QCompleter
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Selected →"))
        self._bulk_obj = QComboBox()
        self._bulk_obj.setEditable(True)
        self._bulk_obj.setInsertPolicy(QComboBox.NoInsert)
        self._bulk_obj.setCurrentIndex(-1)
        self._bulk_obj.lineEdit().setPlaceholderText("Object — type a name or pick…")
        self._bulk_obj.setToolTip(
            "Object to assign every selected row to — pick from the list or type any "
            "name (a new library entry is created for an off-catalog name).")
        comp = self._bulk_obj.completer()
        if comp is not None:
            comp.setCompletionMode(QCompleter.PopupCompletion)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            comp.setFilterMode(Qt.MatchContains)
        self._bulk_obj.setMinimumWidth(180)
        self._bulk_obj.editTextChanged.connect(self._update_bulk_bar)
        bar.addWidget(self._bulk_obj)
        self._bulk_kind = QComboBox()
        for k in ASSIGNABLE_KINDS:
            self._bulk_kind.addItem(KIND_LABEL.get(k, k), k)
        bar.addWidget(self._bulk_kind)
        self._bulk_btn = QPushButton("Assign selected")
        self._bulk_btn.clicked.connect(self._on_bulk_assign)
        bar.addWidget(self._bulk_btn)
        bar.addStretch(1)
        self._update_bulk_bar()
        return bar

    def _selected_holding_rows(self) -> list[int]:
        """Unique selected row indices, in order (bounded to current groups)."""
        rows = {ix.row() for ix in self.holding_table.selectionModel().selectedRows()} \
            if self.holding_table.selectionModel() else set()
        return sorted(r for r in rows if r < len(self._holding_groups))

    def _update_bulk_bar(self, *_):
        rows = self._selected_holding_rows()
        n = len(rows)
        self._bulk_btn.setText(f"Assign {n} selected" if n else "Assign selected")
        has_obj = bool(self._bulk_obj.currentText().strip())
        self._bulk_btn.setEnabled(n > 0 and has_obj and not self.is_busy())

    def _refresh_bulk_obj_items(self, ids):
        """Keep the bulk Object combo's catalog list current without clobbering an
        in-progress typed value."""
        cur = self._bulk_obj.currentText()
        self._bulk_obj.blockSignals(True)
        self._bulk_obj.clear()
        self._bulk_obj.addItems(ids)
        self._bulk_obj.setCurrentIndex(-1)
        self._bulk_obj.setEditText(cur)
        self._bulk_obj.blockSignals(False)

    def _on_bulk_assign(self):
        """Assign every selected held row to one object + kind at once (#33)."""
        if self.is_busy():
            return
        rows = self._selected_holding_rows()
        obj = self._bulk_obj.currentText().strip()
        kind = self._bulk_kind.currentData()
        if not rows or not obj:
            return
        groups = [self._holding_groups[r] for r in rows]
        assigned = [ingest.assign(g, obj, kind) for g in groups]
        ops = [o for a in assigned for o in a.ops]
        if not ops:
            QMessageBox.information(
                self, "Assign", "Those files are already present at the destination.")
            return
        dest = assigned[0].dest_dir
        if QMessageBox.question(
                self, "Confirm assign",
                f"Move {len(ops)} file(s) from {len(groups)} holding folder(s) into "
                f"{dest}?\n\nThis writes into the collection and moves the files out "
                f"of Inbox/.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Yes:
            return
        self._set_busy(True)
        self._make_progress("Moving files…", len(ops), "Assigning")
        self._worker = _ApplyWorker(ops, self._cancel_event, self)
        self._worker.progressed.connect(self._on_apply_progress)
        self._worker.done.connect(self._on_bulk_assign_done)
        self._worker.failed.connect(self._on_apply_failed)
        self._worker.start()
        self._progress.show()

    def _on_bulk_assign_done(self, result: dict):
        self._finish_worker()
        self._close_progress()
        self._set_busy(False)
        moved = result.get("moved", 0)
        self.imported.emit(moved)
        self.refresh_holding()

    def _on_holding_inspect(self, row: int, _col: int):
        """Double-click a held row → the FITS-header/thumbnail/suggestion inspector (#26)."""
        if row >= len(self._holding_groups):
            return
        info = self._holding_info[row] if row < len(self._holding_info) else {}
        from m110.ui.holding_inspect_dialog import HoldingInspectDialog
        HoldingInspectDialog(self._holding_groups[row], info, parent=self).exec()

    def refresh_holding(self):
        """Rescan the Inbox/ holding area and repopulate the panel (synchronous —
        the holding area is local + small). Surviving rows **keep their in-progress
        Object/Kind picks** across the rebuild, so a benign refresh (window focus, a
        modal closing) can't wipe them (#66); the object dropdown is rebuilt from a
        fresh catalog read so a just-imported object shows up (#64)."""
        self._cat = {}                      # refresh so a just-imported object lists (#64)
        prev = self._capture_holding_selections()
        try:
            self._holding_groups = ingest.group_ops(ingest.scan_holding())
        except Exception:
            self._holding_groups = []
        try:
            self._holding_info = ingest.annotate_holding(self._holding_groups)   # #26
        except Exception:
            self._holding_info = [{} for _ in self._holding_groups]
        self._populate_holding(prev)

    def _capture_holding_selections(self) -> dict:
        """Current per-row (object text, kind id) picks, so a rebuild can restore
        them for rows that survive. Keyed on (source folder, detected object) since a
        folder can now split into several object rows."""
        out = {}
        for r in range(self.holding_table.rowCount()):
            if r >= len(self._holding_groups):
                break
            obj_w = self.holding_table.cellWidget(r, 3)
            kind_w = self.holding_table.cellWidget(r, 4)
            if obj_w is not None and kind_w is not None:
                g = self._holding_groups[r]
                out[(g.group, g.object)] = (
                    obj_w.currentText().strip(), kind_w.currentData())
        return out

    def _populate_holding(self, prev: dict | None = None):
        prev = prev or {}
        groups = self._holding_groups
        n = sum(g.frames for g in groups)
        if not groups:
            self._holding_header.setText(
                "Nothing held. Files the importer can't classify land here for "
                "manual assignment.")
        else:
            self._holding_header.setText(
                f"{n} file(s) awaiting assignment — double-click a row to inspect it. "
                "Set the Object by picking from the list <b>or typing any name</b> "
                "(including an object not yet in your library); suggested object/kind "
                "are pre-filled where M110 could read a header.")
        self._holding_header.setTextFormat(Qt.RichText)
        from pathlib import Path
        ids = self._catalog_ids()
        self._refresh_bulk_obj_items(ids)
        self.holding_table.setRowCount(len(groups))
        for r, g in enumerate(groups):
            aid = self._holding_info[r] if r < len(self._holding_info) else {}
            names = [Path(op.src).name for op in g.ops]
            tip = "\n".join(names[:40])
            if len(names) > 40:
                tip += f"\n… +{len(names) - 40} more"
            folder_item = QTableWidgetItem(g.group)
            folder_item.setToolTip(tip)
            self.holding_table.setItem(r, 0, folder_item)
            files_item = QTableWidgetItem(str(g.frames))
            files_item.setToolTip(tip)
            self.holding_table.setItem(r, 1, files_item)
            self.holding_table.setItem(r, 2, QTableWidgetItem(_fmt_size(g.size_bytes)))
            prev_obj, prev_kind = prev.get((g.group, g.object), ("", None))
            obj = self._make_object_combo(ids)
            sug_id, reason = aid.get("suggested_id"), aid.get("reason")
            if prev_obj and prev_obj != "— choose —":
                obj.setCurrentText(prev_obj)    # restore an in-progress pick (#66)
            elif sug_id:
                obj.setCurrentText(sug_id)      # #26: pre-fill the suggestion
                obj.setToolTip(f"Suggested from {reason}. You can change it — type any name.")
            self.holding_table.setCellWidget(r, 3, obj)
            kind = QComboBox()
            for k in ASSIGNABLE_KINDS:
                kind.addItem(KIND_LABEL.get(k, k), k)
            sug_kind = aid.get("suggested_kind")
            if prev_kind is not None:
                ki = kind.findData(prev_kind)
                if ki >= 0:
                    kind.setCurrentIndex(ki)
            elif sug_kind:
                ki = kind.findData(sug_kind)    # #26: pre-fill the suggested kind
                if ki >= 0:
                    kind.setCurrentIndex(ki)
            self.holding_table.setCellWidget(r, 4, kind)
            self.holding_table.setCellWidget(r, 5, self._holding_actions(r))
        # resizeColumnsToContents ignores cell *widgets*, so Object/Kind/Actions
        # would collapse (the "Assign" button clipped to "ssig", #65). This used to
        # carry hand-tuned pixel widths, which fixed that one row and went stale on
        # any label/font/padding change — and never addressed the row *height*, so
        # the same widgets were clipped vertically the whole time. Measure them.
        self.holding_table.resizeColumnsToContents()
        hdr = self.holding_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        fit_cell_widgets(self.holding_table, 3, 4, 5)   # Object · Kind · Actions
        # …then a floor for the two pickers. Fitting alone would size the Object
        # combo to its longest *existing* id (~98px), but it's editable and you
        # type new names into it (#34) — that wants elbow room the content can't
        # imply. The old hardcoded 150/130 encoded this without saying so; keeping
        # it as an explicit minimum keeps the intent and still can't clip, since
        # fit_cell_widgets has already guaranteed the lower bound.
        for col, floor in ((3, 150), (4, 130)):
            hdr.resizeSection(col, max(hdr.sectionSize(col), floor))

    def _make_object_combo(self, ids) -> QComboBox:
        """An editable Object picker for a held row. Starts **empty** (so the
        placeholder shows and it reads as type-or-pick, not a fixed dropdown) and
        accepts **any** name — including an object not yet in the library, which is
        created on import (#34: the drop-down looked mandatory to a beta tester)."""
        from PySide6.QtWidgets import QCompleter
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)   # typing doesn't mutate the list
        combo.addItems(ids)
        combo.setCurrentIndex(-1)                    # empty → placeholder visible
        le = combo.lineEdit()
        le.setPlaceholderText("Type a name or pick…")
        combo.setToolTip(
            "Pick a catalog object, or type any name — including an object not yet "
            "in your library (a new entry is created for it when you assign).")
        comp = combo.completer()
        if comp is not None:                         # match anywhere, case-insensitive
            comp.setCompletionMode(QCompleter.PopupCompletion)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            comp.setFilterMode(Qt.MatchContains)
        return combo

    def _holding_actions(self, row: int) -> QWidget:
        """The per-row action cluster: Assign (route into the collection), Reveal
        (open the folder in the OS file manager), Discard (delete the held files)."""
        cell = QWidget()
        h = QHBoxLayout(cell)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        assign = QPushButton("Assign")
        assign.clicked.connect(lambda _=False, idx=row: self._on_assign(idx))
        reveal = QPushButton("Reveal")
        reveal.setToolTip("Show this folder in the file manager")
        reveal.clicked.connect(lambda _=False, idx=row: self._on_reveal(idx))
        discard = QPushButton("Discard")
        discard.setToolTip("Permanently delete these held files")
        discard.clicked.connect(lambda _=False, idx=row: self._on_discard(idx))
        for b in (assign, reveal, discard):
            h.addWidget(b)
        return cell

    def _holding_folder(self, group) -> "Path":
        """The Inbox/ folder a held group lives in (Inbox itself for loose files)."""
        from pathlib import Path
        base = config.STAGING_DIR
        return base if group.group == "(loose)" else base / group.group

    def _on_reveal(self, row):
        if row >= len(self._holding_groups):
            return
        folder = self._holding_folder(self._holding_groups[row])
        if not folder.is_dir():
            QMessageBox.information(self, "Reveal", f"Folder no longer exists:\n{folder}")
            self.refresh_holding()
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_discard(self, row):
        if row >= len(self._holding_groups) or self.is_busy():
            return
        g = self._holding_groups[row]
        if QMessageBox.question(
                self, "Discard held files",
                f"Permanently delete {g.frames} held file(s) from “{g.group}”?\n\n"
                f"This removes them from the Inbox/ holding area and cannot be "
                f"undone.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel) != QMessageBox.Yes:
            return
        res = ingest.discard_holding(g)
        self.refresh_holding()
        n = res.get("deleted", 0)
        self._holding_header.setText(f"Discarded {n} file(s).  "
                                     + self._holding_header.text())

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
                           "bias", "finished", "media", "unassigned")
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
        self._scan_note.setText("")
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
        self._bulk_obj.setEnabled(not busy)
        self._bulk_kind.setEnabled(not busy)
        self._update_bulk_bar()
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
        self.refresh_holding()      # unclassified files may have landed in Inbox/
        bits = [f"{moved} file(s) imported"]
        if skipped:
            bits.append(f"{skipped} already present")
        prefix = "Import cancelled — " if cancelled else ""
        self._post_import_msg = prefix + ", ".join(bits) + "."
        # Re-scan the source so the view shows true remaining state (imported groups
        # drop out via dedup; unselected ones stay) instead of going blank.
        self.scan()

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
