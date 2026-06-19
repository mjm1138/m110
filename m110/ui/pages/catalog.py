"""Catalog page — the catalog joined with capture status (master table) + the
shared per-object detail pane. Hosts object selection; other pages route here via
`select_object`. Sort persists across in-session rebuilds."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QTableWidget, QTableWidgetItem,
    QMessageBox, QInputDialog,
)

from m110 import config, derived, siril
from m110.catalog import load_catalog, catalog_sort_key, season_sort_key
from m110.ui.detail import DetailPane
from m110.ui.widgets import NumItem, status_label, STATUS_COLOR, MUTED, targets_for_slug


class CatalogPage(QWidget):
    HEADERS = ["Object", "Name", "Type", "Season", "Mag",
               "Status", "Integration", "Sessions"]

    editing_changed = Signal(bool)   # journal editor open/close (shell locks nav)
    dirty = Signal()                 # disk changed (import) → shell should refresh

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cat = load_catalog()
        self._totals = derived.totals_by_slug()
        self._sort_col = 0
        self._sort_order = Qt.AscendingOrder

        self.table = self._build_table()
        self.table.itemSelectionChanged.connect(self._on_select)
        self.detail = DetailPane()
        self.detail.editing_changed.connect(self._on_detail_editing)
        self.detail.import_requested.connect(self._on_import)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.detail)
        self.splitter.setSizes([520, 440])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.splitter)

    # ---- shell hooks ----
    def is_editing(self) -> bool:
        return self.detail.is_editing()

    def set_locked(self, locked: bool):
        self.table.setEnabled(not locked)

    def select_object(self, slug: str):
        self._select_slug(slug)

    def reload(self):
        new_cat = load_catalog()
        new_totals = derived.totals_by_slug()
        changed = (new_cat != self._cat) or (new_totals != self._totals)
        self._cat, self._totals = new_cat, new_totals
        if changed:
            self._rebuild_table()          # preserves selection + sort
        else:
            self._refresh_open_detail()    # cheap: pick up image-only changes

    # ---- table ----
    def _build_table(self) -> QTableWidget:
        cat, totals = self._cat, self._totals
        table = QTableWidget(len(cat), len(self.HEADERS))
        table.setHorizontalHeaderLabels(self.HEADERS)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)

        rows = sorted(cat.items(), key=lambda kv: catalog_sort_key(kv[1].get("id", "")))
        for row, (slug, e) in enumerate(rows):
            t = totals.get(slug, {})
            captured = bool(t)

            obj = NumItem(str(e.get("id", "")), catalog_sort_key(e.get("id", "")))
            obj.setData(Qt.UserRole, slug)
            table.setItem(row, 0, obj)
            table.setItem(row, 1, QTableWidgetItem(str(e.get("name") or "")))
            table.setItem(row, 2, QTableWidgetItem(str(e.get("type") or "").replace("_", " ")))
            season = str(e.get("season") or "")
            table.setItem(row, 3, NumItem(season, season_sort_key(season)))

            mag = e.get("magnitude")
            table.setItem(row, 4, NumItem("" if mag is None else f"{mag}",
                                          float(mag) if mag is not None else 99.0))

            status_item = QTableWidgetItem(status_label(t.get("status"), captured))
            status_item.setForeground(STATUS_COLOR.get(t.get("status"), MUTED))
            table.setItem(row, 5, status_item)

            integ_min = float(t.get("integration_min", 0) or 0)
            table.setItem(row, 6, NumItem(t.get("integration_hms", "") if captured else "", integ_min))
            sc = int(t.get("session_count", 0) or 0)
            table.setItem(row, 7, NumItem(str(sc) if captured else "", float(sc)))

            if not captured:
                for c in range(len(self.HEADERS)):
                    if c != 5:
                        table.item(row, c).setForeground(MUTED)

        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
        table.sortByColumn(self._sort_col, self._sort_order)
        table.horizontalHeader().sortIndicatorChanged.connect(self._on_sort_changed)
        return table

    def _on_sort_changed(self, col: int, order):
        self._sort_col = col
        self._sort_order = order

    def _rebuild_table(self):
        prev = self._selected_slug()
        new_table = self._build_table()
        new_table.itemSelectionChanged.connect(self._on_select)
        old = self.splitter.replaceWidget(0, new_table)
        self.table = new_table
        if old is not None:
            old.deleteLater()
        self.splitter.setSizes([520, 440])
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
