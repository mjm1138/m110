"""Processing page — the Siril queue, grouped by status, with stack metadata.

One row = one capture **target** (an `Images/<target>/` folder = one stack to process),
*not* one catalog object — a combined "M81 M82" target covers two objects, and a solo
"M81" target is a separate, equally legitimate row. Double-click opens the Catalog
detail for the target's first object."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QTableWidgetItem, QMenu,
)

from m110 import derived, siril
from m110.ui.widgets import (
    make_table, make_numeric, NumItem, ThumbnailLoader, RowThumbnails,
    ROW_THUMB_SIZE, fit_table_height, process_target_in_siril,
)

# Status-keyed groups (Up to date is intentionally omitted — fully-processed objects
# with nothing waiting need no attention). "Ready to import" is a separate, flag-keyed
# group prepended in reload().
_GROUPS = [
    ("out_of_date", "Out of date — restack to incorporate new lights"),
    ("not_processed", "Not processed — first stack needed"),
    ("dismissed", "Dismissed"),
]
# "Target" (not "Object"): a row is a capture **target** (an Images/<target> folder =
# one stack to process), which may cover several catalog objects ("M81 M82"). Labelling
# it "Object" made solo captures alongside a combined one read as duplicate objects.
_COLS = ["Target", "Raw integ", "In stack", "Rejected", "+ new", "Latest stack",
         "Last capture", "Notes"]
# Default sort: most new-lights first — "what needs restacking most" on top.
_DEFAULT_SORT = (_COLS.index("+ new"), Qt.DescendingOrder)


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
        # Per-group sort choice, keyed by group id — survives reload() (the tables
        # are rebuilt on every sync, incl. the window-focus auto-sync).
        self._sort: dict[str, tuple[int, Qt.SortOrder]] = {}
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

    def _wire_context(self, table):
        table.setContextMenuPolicy(Qt.CustomContextMenu)

        def show(pos):
            item = table.itemAt(pos)
            if item is None:
                return
            folder = table.item(item.row(), 0).text()
            if not folder or not siril.working_dirs(folder):
                return
            menu = QMenu(self)
            act = menu.addAction("Process in Siril")
            if menu.exec(table.viewport().mapToGlobal(pos)) is act:
                process_target_in_siril(self, folder)
        table.customContextMenuRequested.connect(show)

    def reload(self):
        self._clear()
        proc = derived.load_processing()
        counts = proc.get("counts", {})
        queue = proc.get("queue", [])
        self._thumbs.reset()

        title = QLabel("<h2>Processing Queue</h2>")
        title.setTextFormat(Qt.RichText)
        self._lay.addWidget(title)
        n_ready = sum(1 for f in queue if f.get("ready_for_import"))
        self._lay.addWidget(QLabel(
            (f"{n_ready} ready to import · " if n_ready else "")
            + f"{counts.get('out_of_date', 0)} out of date · "
            f"{counts.get('not_processed', 0)} not processed"
            + (f" · {counts.get('dismissed')} dismissed" if counts.get("dismissed") else "")))

        # "Ready to import" (finished Siril output waiting) takes precedence over the
        # status groups, so an object with output to pull in shows once, at the top.
        ready = [f for f in queue if f.get("ready_for_import")]
        rest = [f for f in queue if not f.get("ready_for_import")]
        groups = ([("ready", "Ready to import — finished Siril output waiting", ready)]
                  if ready else [])
        groups += [(status, label, [f for f in rest if f.get("status") == status])
                   for status, label in _GROUPS]

        for key, label, rows in groups:
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
                tbl.setItem(r, 7, QTableWidgetItem(f.get("note") or ""))
            tbl.resizeColumnsToContents()
            # Sort by the remembered per-group choice (default: "+ new" desc), then
            # start recording header clicks so the choice survives the next reload.
            tbl.setSortingEnabled(True)
            col, order = self._sort.get(key, _DEFAULT_SORT)
            tbl.horizontalHeader().setSortIndicator(col, order)
            tbl.horizontalHeader().sortIndicatorChanged.connect(
                lambda c, o, k=key: self._sort.__setitem__(k, (c, o)))
            # Fit every row (the page scrolls, not each table) + a half-row pad so a
            # single-row group isn't clipped.
            fit_table_height(tbl)
            self._wire_open(tbl)
            self._wire_context(tbl)
            self._lay.addWidget(tbl)

        if not queue:
            self._lay.addWidget(QLabel("<i>No captured targets yet.</i>"))
        self._lay.addStretch(1)
