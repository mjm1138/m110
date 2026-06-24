"""Sessions page — the capture-session log (one row per object/night/exposure).
Mirrors the site's Sessions page; a search box filters and object rows
double-click to the Catalog detail."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QTableWidgetItem,
)

from m110 import derived
from m110.ui.widgets import make_table, NumItem

_COLS = ["Date", "Object", "Frames", "Exp (s)", "Filter", "Integration", "Mount"]


class SessionsPage(QWidget):
    open_object = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignTop)

        self._title = QLabel("<h2>Sessions</h2>")
        self._title.setTextFormat(Qt.RichText)
        lay.addWidget(self._title)
        self._summary = QLabel()
        lay.addWidget(self._summary)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        lay.addWidget(self._search)

        self._table = make_table(_COLS)
        self._table.setSortingEnabled(True)
        self._table.itemDoubleClicked.connect(self._go)
        lay.addWidget(self._table, 1)

        self.reload()

    def _go(self, item):
        slug = self._table.item(item.row(), 1).data(Qt.UserRole)
        if slug:
            self.open_object.emit(slug)

    def reload(self):
        rows = derived.load_sessions()
        t = self._table
        t.setSortingEnabled(False)
        t.setRowCount(0)
        for s in rows:
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, NumItem(s.get("date", ""), s.get("date", "")))
            obj = QTableWidgetItem(s.get("object_dir", ""))
            if s.get("slugs"):
                obj.setData(Qt.UserRole, s["slugs"][0])
            t.setItem(r, 1, obj)
            t.setItem(r, 2, NumItem(str(s.get("frames", 0)), s.get("frames", 0)))
            exp = s.get("exposure_s", 0)
            t.setItem(r, 3, NumItem(str(exp), exp))
            t.setItem(r, 4, QTableWidgetItem(s.get("filter", "")))
            mins = s.get("integration_min", 0.0)
            t.setItem(r, 5, NumItem(_fmt_hm(mins), mins))
            t.setItem(r, 6, QTableWidgetItem(s.get("mount_mode", "")))
        t.resizeColumnsToContents()
        t.setSortingEnabled(True)
        t.sortItems(0, Qt.DescendingOrder)   # most recent first

        nights = len({s.get("date") for s in rows})
        targets = len({s.get("object_dir") for s in rows})
        self._summary.setText(
            f"{len(rows)} sessions · {targets} targets · {nights} nights"
            if rows else "No sessions yet — run Refresh (Ctrl+R).")
        self._apply_filter()

    def _apply_filter(self):
        q = self._search.text().strip().lower()
        t = self._table
        for r in range(t.rowCount()):
            if not q:
                t.setRowHidden(r, False)
                continue
            hay = " ".join(
                (t.item(r, c).text() if t.item(r, c) else "") for c in (0, 1, 4, 6)
            ).lower()
            t.setRowHidden(r, q not in hay)


def _fmt_hm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60}:{m % 60:02d}"
