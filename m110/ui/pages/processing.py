"""Processing page — the Siril queue, grouped by status, with stack metadata.
Mirrors the site's Processing page. Object rows double-click to the Catalog detail."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QTableWidgetItem,
)

from m110 import derived
from m110.ui.widgets import (
    make_table, make_numeric, NumItem, ThumbnailLoader, RowThumbnails, ROW_THUMB_SIZE,
)

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
        self._thumb_loader = ThumbnailLoader(self)
        self._thumbs = RowThumbnails(self._thumb_loader)
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
        self._thumbs.reset()

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
            tbl.setSortingEnabled(False)   # populate in queue order first
            tbl.setIconSize(QSize(ROW_THUMB_SIZE, ROW_THUMB_SIZE))
            for f in rows:
                r = tbl.rowCount()
                tbl.insertRow(r)
                obj = QTableWidgetItem(f.get("folder", ""))
                if f.get("slugs"):
                    slug = f["slugs"][0]
                    obj.setData(Qt.UserRole, slug)
                    self._thumbs.add(slug, obj)
                tbl.setItem(r, 0, obj)
                tbl.setItem(r, 1, make_numeric(NumItem(
                    f"{f.get('integration_hms', '')} ({f.get('frames', 0)} fr)",
                    f.get("integration_min", 0.0))))
                sm = f.get("stack_meta")
                tbl.setItem(r, 2, make_numeric(NumItem(
                    f"{sm['stack_integration_hms']} ({sm['stack_frames']} fr)" if sm else "—",
                    sm["stack_integration_min"] if sm else -1)))
                tbl.setItem(r, 3, make_numeric(NumItem(
                    f"{sm['stack_rejection_pct']}%" if sm and 'stack_rejection_pct' in sm else "—",
                    sm["stack_rejection_pct"] if sm and 'stack_rejection_pct' in sm else -1)))
                nl = f.get("new_lights_since_stack", 0)
                tbl.setItem(r, 4, make_numeric(NumItem(f"+{nl}" if nl else "—", nl)))
                latest = f.get("latest_processed")
                tbl.setItem(r, 5, NumItem(
                    f"{latest} · {f.get('latest_processed_at', '')}" if latest else "—",
                    f.get("latest_processed_at") or ""))
                tbl.setItem(r, 6, NumItem(
                    f.get("last_capture") or "—", f.get("last_capture") or ""))
                tbl.setItem(r, 7, QTableWidgetItem("✓ yes" if f.get("star_removal") else "—"))
                tbl.setItem(r, 8, QTableWidgetItem(f.get("note") or ""))
            tbl.resizeColumnsToContents()
            tbl.resizeRowsToContents()
            # Enable click-to-sort, but keep the meaningful queue order until the
            # user actually picks a column (no active sort indicator).
            tbl.setSortingEnabled(True)
            tbl.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
            # Size to fit every row — these grouped tables shouldn't scroll
            # internally (the page scrolls); a capped minimum truncated them.
            tbl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            h = tbl.horizontalHeader().height() + 2 * tbl.frameWidth()
            for i in range(tbl.rowCount()):
                h += tbl.rowHeight(i)
            tbl.setFixedHeight(h)
            self._wire_open(tbl)
            self._lay.addWidget(tbl)

        if not queue:
            self._lay.addWidget(QLabel("<i>No captured targets yet.</i>"))
        self._lay.addStretch(1)
