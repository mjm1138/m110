"""Processing page — the Siril queue, grouped by status, with stack metadata.
Mirrors the site's Processing page. Object rows double-click to the Catalog detail."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QTableWidgetItem,
)

from m110 import derived
from m110.ui.widgets import make_table

_GROUPS = [
    ("out_of_date", "Out of date — restack to incorporate new lights"),
    ("not_processed", "Not processed — first stack needed"),
    ("up_to_date", "Up to date"),
    ("dismissed", "Dismissed"),
]
_COLS = ["Object", "Raw integ", "In stack", "Rejected", "+ new", "Latest stack",
         "Last capture", "Star removal", "Note"]


class ProcessingPage(QScrollArea):
    open_object = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        self.setWidget(self._content)
        self.reload()

    def _clear(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()

    def _wire_open(self, table):
        def go(item):
            slug = table.item(item.row(), 0).data(Qt.UserRole)
            if slug:
                self.open_object.emit(slug)
        table.itemDoubleClicked.connect(go)

    def reload(self):
        self._clear()
        proc = derived.load_processing()
        counts = proc.get("counts", {})
        queue = proc.get("queue", [])

        title = QLabel("<h2>Processing Queue</h2>")
        title.setTextFormat(Qt.RichText)
        self._lay.addWidget(title)
        self._lay.addWidget(QLabel(
            f"{counts.get('out_of_date', 0)} out of date · "
            f"{counts.get('not_processed', 0)} not processed · "
            f"{counts.get('up_to_date', 0)} up to date"
            + (f" · {counts.get('dismissed')} dismissed" if counts.get("dismissed") else "")))

        for status, label in _GROUPS:
            rows = [f for f in queue if f.get("status") == status]
            if not rows:
                continue
            h = QLabel(f"<h3>{label}</h3>")
            h.setTextFormat(Qt.RichText)
            self._lay.addWidget(h)
            tbl = make_table(_COLS, stretch_last=True)
            tbl.setSortingEnabled(False)
            for f in rows:
                r = tbl.rowCount()
                tbl.insertRow(r)
                obj = QTableWidgetItem(f.get("folder", ""))
                if f.get("slugs"):
                    obj.setData(Qt.UserRole, f["slugs"][0])
                tbl.setItem(r, 0, obj)
                tbl.setItem(r, 1, QTableWidgetItem(
                    f"{f.get('integration_hms', '')} ({f.get('frames', 0)} fr)"))
                sm = f.get("stack_meta")
                tbl.setItem(r, 2, QTableWidgetItem(
                    f"{sm['stack_integration_hms']} ({sm['stack_frames']} fr)" if sm else "—"))
                tbl.setItem(r, 3, QTableWidgetItem(
                    f"{sm['stack_rejection_pct']}%" if sm and 'stack_rejection_pct' in sm else "—"))
                nl = f.get("new_lights_since_stack", 0)
                tbl.setItem(r, 4, QTableWidgetItem(f"+{nl}" if nl else "—"))
                latest = f.get("latest_processed")
                tbl.setItem(r, 5, QTableWidgetItem(
                    f"{latest} · {f.get('latest_processed_at', '')}" if latest else "—"))
                tbl.setItem(r, 6, QTableWidgetItem(f.get("last_capture") or "—"))
                tbl.setItem(r, 7, QTableWidgetItem("✓ yes" if f.get("star_removal") else "—"))
                tbl.setItem(r, 8, QTableWidgetItem(f.get("note") or ""))
            tbl.resizeColumnsToContents()
            tbl.setMinimumHeight(min(420, 28 * (len(rows) + 1) + 8))
            self._wire_open(tbl)
            self._lay.addWidget(tbl)

        if not queue:
            self._lay.addWidget(QLabel("<i>No captured targets yet.</i>"))
        self._lay.addStretch(1)
