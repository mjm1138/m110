"""Catalog page — the catalog joined with capture status (master table) + the
shared per-object detail pane. Hosts object selection; other pages route here via
`select_object`. Sort persists across in-session rebuilds."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget, QTableWidgetItem,
    QMessageBox, QInputDialog, QLineEdit, QLabel, QComboBox, QCheckBox, QMenu,
)

from m110 import config, derived, siril, catalog as catalog_mod
from m110.catalog import (
    load_library, catalog_sort_key, season_sort_key, object_identifiers,
    object_label, list_bundled_catalogs,
)
from m110.ui.detail import DetailPane
from m110.ui.widgets import NumItem, status_label, STATUS_COLOR, MUTED, targets_for_slug


class CatalogPage(QWidget):
    HEADERS = ["Object", "Name", "Type", "Season", "Mag", "Size", "Filter",
               "Status", "Integration", "Sessions"]

    editing_changed = Signal(bool)   # journal editor open/close (shell locks nav)
    dirty = Signal()                 # disk changed (import) → shell should refresh

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cat = load_library()
        self._totals = derived.totals_by_slug()
        self._sort_col = 0
        self._sort_order = Qt.AscendingOrder
        self._catalog_filter = None       # None = all objects; else a catalog id
        self._catalogs = list_bundled_catalogs()

        self.table = self._build_table()
        self.table.itemSelectionChanged.connect(self._on_select)
        self.detail = DetailPane()
        self.detail.editing_changed.connect(self._on_detail_editing)
        self.detail.import_requested.connect(self._on_import)

        # Left side: catalog selector + search + stat row above the table.
        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("Catalog:"))
        self._catalog_combo = QComboBox()
        self._catalog_combo.addItem("All objects", None)
        for c in self._catalogs:
            self._catalog_combo.addItem(f"{c['name']} ({len(c['members'])})", c["id"])
        self._catalog_combo.currentIndexChanged.connect(self._on_catalog_changed)
        cat_row.addWidget(self._catalog_combo, 1)
        self._captured_chk = QCheckBox("Captured only")
        self._captured_chk.toggled.connect(self._apply_filter)
        cat_row.addWidget(self._captured_chk)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        self._stat = QLabel()
        self._stat.setStyleSheet("color:#8b949e")

        left = QWidget()
        self._left_lay = QVBoxLayout(left)
        self._left_lay.setContentsMargins(0, 0, 0, 0)
        self._left_lay.addLayout(cat_row)
        self._left_lay.addWidget(self._search)
        self._left_lay.addWidget(self._stat)
        self._left_lay.addWidget(self.table)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.detail)
        self.splitter.setSizes([560, 460])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.splitter)
        self._update_stat()

    @property
    def _status_col(self) -> int:
        return self.HEADERS.index("Status")

    # ---- shell hooks ----
    def is_editing(self) -> bool:
        return self.detail.is_editing()

    def set_locked(self, locked: bool):
        self.table.setEnabled(not locked)

    def select_object(self, slug: str):
        # Ensure the target row isn't filtered out (clear search + catalog filter).
        self._search.clear()
        if self._catalog_filter is not None:
            self._catalog_combo.setCurrentIndex(0)   # "All objects" → triggers rebuild
        self._select_slug(slug)

    def _on_catalog_changed(self, _idx: int):
        self._catalog_filter = self._catalog_combo.currentData()
        self._rebuild_table()
        self._update_stat()

    def reload(self):
        new_cat = load_library()
        new_totals = derived.totals_by_slug()
        changed = (new_cat != self._cat) or (new_totals != self._totals)
        self._cat, self._totals = new_cat, new_totals
        if changed:
            self._rebuild_table()          # preserves selection + sort
            self._update_stat()
        else:
            self._refresh_open_detail()    # cheap: pick up image-only changes

    def _update_stat(self):
        members = self._filter_members()
        slugs = [s for s in self._cat if members is None or s in members]
        captured = sum(1 for s in slugs if s in self._totals)
        deep = sum(1 for s in slugs
                   if self._totals.get(s, {}).get("status") == "deep_stack")
        prefix = ""
        if self._catalog_filter:
            name = next((c["name"] for c in self._catalogs
                         if c["id"] == self._catalog_filter), self._catalog_filter)
            prefix = f"{name} — "
        self._stat.setText(
            f"{prefix}{captured} captured · {deep} deep · {len(slugs)} total")

    def _apply_filter(self, *_):
        q = self._search.text().strip().lower()
        cap_only = self._captured_chk.isChecked()
        for r in range(self.table.rowCount()):
            slug = self.table.item(r, 0).data(Qt.UserRole)
            hide = cap_only and slug not in self._totals
            if not hide and q:
                hay = " ".join(self.table.item(r, c).text() for c in (0, 1, 2)).lower()
                hide = q not in hay
            self.table.setRowHidden(r, hide)

    def _filter_members(self) -> set | None:
        """Slugs of the selected catalog, or None for 'All objects'."""
        if not self._catalog_filter:
            return None
        for c in self._catalogs:
            if c["id"] == self._catalog_filter:
                return set(c["members"])
        return set()

    # ---- table ----
    def _build_table(self) -> QTableWidget:
        cat, totals = self._cat, self._totals
        members = self._filter_members()
        pc = self._catalog_filter
        items = [(slug, e) for slug, e in cat.items()
                 if members is None or slug in members]
        # primary identifier per row (context: the selected catalog)
        ids = {slug: object_identifiers(slug, e, primary_catalog=pc)
               for slug, e in items}
        items.sort(key=lambda kv: catalog_sort_key(ids[kv[0]][0] if ids[kv[0]] else ""))

        table = QTableWidget(len(items), len(self.HEADERS))
        table.setHorizontalHeaderLabels(self.HEADERS)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)

        for row, (slug, e) in enumerate(items):
            t = totals.get(slug, {})
            captured = bool(t)

            oid = ids[slug]
            obj = NumItem(object_label(oid), catalog_sort_key(oid[0] if oid else ""))
            obj.setData(Qt.UserRole, slug)
            table.setItem(row, 0, obj)
            table.setItem(row, 1, QTableWidgetItem(str(e.get("name") or "")))
            table.setItem(row, 2, QTableWidgetItem(str(e.get("type") or "").replace("_", " ")))
            season = str(e.get("season") or "")
            table.setItem(row, 3, NumItem(season, season_sort_key(season)))

            mag = e.get("magnitude")
            table.setItem(row, 4, NumItem("" if mag is None else f"{mag}",
                                          float(mag) if mag is not None else 99.0))
            table.setItem(row, 5, QTableWidgetItem(str(e.get("size") or "")))
            table.setItem(row, 6, QTableWidgetItem(str(e.get("filter") or "")))

            status_item = QTableWidgetItem(status_label(t.get("status"), captured))
            status_item.setForeground(STATUS_COLOR.get(t.get("status"), MUTED))
            table.setItem(row, self._status_col, status_item)

            integ_min = float(t.get("integration_min", 0) or 0)
            table.setItem(row, 8, NumItem(t.get("integration_hms", "") if captured else "", integ_min))
            sc = int(t.get("session_count", 0) or 0)
            table.setItem(row, 9, NumItem(str(sc) if captured else "", float(sc)))

            if not captured:
                for c in range(len(self.HEADERS)):
                    if c != self._status_col:
                        table.item(row, c).setForeground(MUTED)

        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
        table.sortByColumn(self._sort_col, self._sort_order)
        table.horizontalHeader().sortIndicatorChanged.connect(self._on_sort_changed)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_context_menu)
        return table

    def _on_sort_changed(self, col: int, order):
        self._sort_col = col
        self._sort_order = order

    def _rebuild_table(self):
        prev = self._selected_slug()
        new_table = self._build_table()
        new_table.itemSelectionChanged.connect(self._on_select)
        self._left_lay.replaceWidget(self.table, new_table)
        self.table.deleteLater()
        self.table = new_table
        self._apply_filter()
        if not (prev and self._select_slug(prev)):
            self.detail.placeholder()

    def _selected_slug(self):
        items = self.table.selectedItems()
        return self.table.item(items[0].row(), 0).data(Qt.UserRole) if items else None

    def _select_slug(self, slug) -> bool:
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.UserRole) == slug:
                self.table.selectRow(r)
                self.table.scrollToItem(self.table.item(r, 0))
                return True
        return False

    def _on_select(self):
        items = self.table.selectedItems()
        if not items:
            return
        slug = self.table.item(items[0].row(), 0).data(Qt.UserRole)
        self.detail.show_object(slug, self._cat[slug], self._totals.get(slug, {}))

    def _refresh_open_detail(self):
        slug = self._selected_slug()
        if slug and slug in self._cat:
            self.detail.show_object(slug, self._cat[slug], self._totals.get(slug, {}))

    # ---- editing lock ----
    def _on_detail_editing(self, editing: bool):
        self.table.setEnabled(not editing)
        self.editing_changed.emit(editing)

    # ---- context menu: fill missing metadata ----
    def _on_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if item is None:
            return
        slug = self.table.item(item.row(), 0).data(Qt.UserRole)
        entry = self._cat.get(slug, {})
        missing = bool(catalog_mod._compute_fill(entry, catalog_mod.load_reference().get(slug, {})))
        menu = QMenu(self)
        act = menu.addAction("Fill in missing metadata")
        act.setEnabled(missing)
        if menu.exec(self.table.viewport().mapToGlobal(pos)) is act and missing:
            self._fill_one(slug)

    def _fill_one(self, slug: str):
        try:
            filled = catalog_mod.fill_missing_metadata(slug)
        except catalog_mod.LibraryParseError as e:
            QMessageBox.warning(self, "Library file error", str(e))
            return
        if not filled:
            QMessageBox.information(self, "Nothing to fill",
                                   "This object already has all available metadata.")
            return
        self._cat = load_library()
        self._rebuild_table()
        self._select_slug(slug)
        fields = ", ".join(sorted(filled))
        QMessageBox.information(self, "Metadata filled",
                               f"Filled from the reference: {fields}.")

    # ---- import (prep is automatic on ingest) ----
    def _pick_target(self, targets: list[str], title: str) -> str | None:
        if len(targets) == 1:
            return targets[0]
        target, ok = QInputDialog.getItem(
            self, title, "This object maps to multiple capture targets:",
            sorted(targets), 0, False)
        return target if ok else None

    def _on_import(self, slug: str):
        targets = [t for t in targets_for_slug(slug)
                   if siril.has_unimported_output(t)]
        if not targets:
            QMessageBox.information(self, "Nothing to import",
                                   "No finished processing output found for this object.")
            return
        target = self._pick_target(targets, "Choose capture target")
        if target is None:
            return
        from m110.ui.import_dialog import ImportDialog
        dlg = ImportDialog(target, slug, parent=self)
        dlg.imported.connect(lambda _t: self.dirty.emit())
        dlg.exec()
