"""Media page — browse non-catalog media (lunar/planetary/scenery) that ingest
drops into `Media/<Category>_photo|_video/`.

Structurally a sibling of the Library's Deep-sky scope: one filtered item list
feeding a **List** (table + detail pane) and a **Grid** (tile wall) view, with the
view choice driven from the Library's shared segment. Photos open in the shared
`ImageViewer`; videos open in the OS player. Read-only.

Thumbnails go through `widgets.ThumbnailLoader`, which decodes off the UI thread
and — the part that matters — **center-crops to a square before scaling**. The
page previously built `QIcon(str(path))` against a 160x160 icon size, which
squashed a 1080x1920 lunar frame into 160x160 and turned the Moon into a wide
oval (measured: subject aspect 1.005 at source, 1.790 through QIcon).

The trap is that this is **format-dependent**: the JPEG handler advertises
`ScaledSize`, so Qt has it decode straight to the requested size and it obeys
literally, ignoring aspect; PNG advertises no such support, so Qt loads full-size
and scales with `KeepAspectRatio`. Identical code, right for a PNG and wrong for
a JPEG — and the Seestar writes JPEG. Never hand a raw source path to QIcon for a
fixed-size icon; `tests/test_thumbnail_aspect.py` enforces that across `m110/ui`.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListView, QMenu, QSlider, QSplitter, QStackedWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from m110 import config, media
from m110.ui.image_grid import (
    TileItem, TileModel, TileDelegate, KEY_ROLE,
    GRID_ZOOM_MIN, GRID_ZOOM_MAX, GRID_ZOOM_DEFAULT,
)
from m110.ui.image_viewer import ImageViewer
from m110.ui.media_detail import MediaDetailPane, fmt_date, fmt_size
from m110.ui.widgets import (
    NumItem, ROW_THUMB_SIZE, ThumbnailLoader, connect_context_menu, defer,
    drain_worker, make_numeric, make_segment, make_table, open_in_default,
    reveal_in_manager,
)

MEDIA_VIEW_KEY = "media_view_mode"      # "list" | "grid"
MEDIA_ZOOM_KEY = "media_grid_zoom"      # int px

VIDEO_BADGE = "▶"                  # ▶ — marks a tile that isn't a still

HEADERS = ["Name", "Category", "Kind", "Date", "Size"]


class _PosterWorker(QThread):
    """Generates the stills that FITS / astro-TIFF media need, off the UI thread.

    Each costs ~0.1 s, so rendering them inline while building tiles turns into a
    multi-second freeze on a store full of stacked results — and `reload()` runs
    on entering the Media scope. The views paint placeholders meanwhile and are
    refreshed when this finishes; the renders are content-hash cached on disk, so
    this is a one-off per file."""

    done = Signal(int)          # how many posters were generated

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self._items = list(items)
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            made = media.render_posters(self._items,
                                        should_cancel=self._cancel.is_set)
        except Exception:                    # a bad file must not kill the thread
            made = 0
        self.done.emit(made)


class MediaPage(QWidget):
    """The Media scope. `set_view_mode` is driven by the Library's view segment."""

    # The segment lives on the host (it shares a slot with the Deep-sky one), so a
    # mode change made any other way has to travel back or the buttons go stale.
    view_mode_changed = Signal(str)

    def __init__(self, parent=None, show_title=True):
        super().__init__(parent)
        self._items: list[media.MediaItem] = []
        self._visible: list[media.MediaItem] = []
        self._thumb_loader = ThumbnailLoader(self)
        self._row_items: dict[str, list[QTableWidgetItem]] = {}
        self._selected_key: str | None = None
        self._poster_worker = None

        mode = config.get_setting(MEDIA_VIEW_KEY, "grid")
        self._view_mode = mode if mode in ("list", "grid") else "grid"
        zoom = config.get_setting(MEDIA_ZOOM_KEY, GRID_ZOOM_DEFAULT)
        try:
            self._zoom = max(GRID_ZOOM_MIN, min(GRID_ZOOM_MAX, int(zoom)))
        except (TypeError, ValueError):
            self._zoom = GRID_ZOOM_DEFAULT

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        if show_title:      # suppressed when embedded under the Library's Media scope
            title = QLabel("<h2>Media</h2>")
            title.setTextFormat(Qt.RichText)
            outer.addWidget(title)

        # ---- filters -------------------------------------------------------
        filt = QHBoxLayout()
        filt.setContentsMargins(0, 0, 0, 0)
        filt.addWidget(QLabel("Category:"))
        self._cat_combo = QComboBox()
        self._cat_combo.currentIndexChanged.connect(lambda _i: self._apply_filter())
        # Not stretched: filling the row left it dominating the controls and
        # stranded the kind segment at the far edge.
        self._cat_combo.setMinimumWidth(180)
        filt.addWidget(self._cat_combo)
        filt.addStretch(1)
        self._kind_seg, self._kind_group, self._kind_btns = make_segment(
            [("all", "All"), ("photo", "Photos"), ("video", "Videos")], "all")
        for key, b in self._kind_btns.items():
            b.toggled.connect(lambda on, k=key: on and self._apply_filter())
        filt.addWidget(self._kind_seg)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)

        self._stat = QLabel()
        self._stat.setProperty("muted", True)
        self._stat.setWordWrap(True)

        # ---- views ---------------------------------------------------------
        self.table = make_table(HEADERS)
        self.table.setIconSize(QSize(ROW_THUMB_SIZE, ROW_THUMB_SIZE))
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)          # Name
        for col in range(1, len(HEADERS)):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.itemSelectionChanged.connect(self._on_table_select)
        self.table.itemDoubleClicked.connect(
            lambda item: self._open_item(self._item_for_row(item.row())))
        connect_context_menu(self.table, self._table_menu)

        self._grid_model = TileModel(self)
        self.grid_view = QListView()
        self.grid_view.setViewMode(QListView.IconMode)
        self.grid_view.setResizeMode(QListView.Adjust)
        self.grid_view.setMovement(QListView.Static)
        self.grid_view.setUniformItemSizes(True)
        self.grid_view.setModel(self._grid_model)
        self._grid_delegate = TileDelegate(self._zoom, self.grid_view)
        self.grid_view.setItemDelegate(self._grid_delegate)
        self.grid_view.selectionModel().selectionChanged.connect(self._on_grid_select)
        self.grid_view.doubleClicked.connect(
            lambda idx: self._open_item(self._item_for_key(idx.data(KEY_ROLE))))
        connect_context_menu(self.grid_view, self._grid_menu)

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self.table)        # 0
        self._view_stack.addWidget(self.grid_view)    # 1
        self._view_stack.setCurrentIndex(1 if self._view_mode == "grid" else 0)

        # Its own status-bar-style row below the views, so showing/hiding it can
        # never shift another control (the Library grid's lesson).
        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setMinimum(GRID_ZOOM_MIN)
        self._zoom_slider.setMaximum(GRID_ZOOM_MAX)
        self._zoom_slider.setValue(self._zoom)
        self._zoom_slider.setFixedWidth(120)
        self._zoom_slider.setToolTip("Tile size")
        self._zoom_slider.valueChanged.connect(self._on_zoom_changing)
        self._zoom_slider.sliderReleased.connect(self._on_zoom_released)
        zoom_row = QHBoxLayout()
        zoom_row.setContentsMargins(0, 2, 0, 2)
        zoom_row.addStretch(1)
        zoom_row.addWidget(QLabel("Tile size:"))
        zoom_row.addWidget(self._zoom_slider)
        self._zoom_row_widget = QWidget()
        self._zoom_row_widget.setLayout(zoom_row)
        self._zoom_row_widget.setVisible(self._view_mode == "grid")

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addLayout(filt)
        ll.addWidget(self._search)
        ll.addWidget(self._stat)
        ll.addWidget(self._view_stack, 1)
        ll.addWidget(self._zoom_row_widget)

        self.detail = MediaDetailPane()
        self.detail.open_requested.connect(self._open_item)
        self.detail.closed.connect(self._clear_selection)
        self.detail.hide()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.detail)
        self.splitter.setSizes([620, 400])
        outer.addWidget(self.splitter, 1)

        # A QThread still running when Qt tears down aborts the process, and a
        # page is not reliably closed on quit — so drain at aboutToQuit too, the
        # same belt-and-braces `drain_thumbnail_pool` gets in `main`.
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.aboutToQuit.connect(self._stop_poster_worker)

        self.reload()
        # Newest first, matching the grid. Without an explicit default the table
        # inherits whatever indicator the header starts with (Name), which for a
        # capture library is an arbitrary order. A user re-sort sticks from here:
        # `_fill_table` re-enables sorting, which re-applies the live indicator.
        self.table.sortByColumn(HEADERS.index("Date"), Qt.DescendingOrder)

    # ---- shell hooks ----------------------------------------------------
    def view_mode(self) -> str:
        return self._view_mode

    def set_view_mode(self, mode: str):
        if mode not in ("list", "grid") or mode == self._view_mode:
            return                      # re-entrancy guard (setChecked re-enters)
        self._view_mode = mode
        self._view_stack.setCurrentIndex(1 if mode == "grid" else 0)
        self._zoom_row_widget.setVisible(mode == "grid")
        config.save_setting(MEDIA_VIEW_KEY, mode)
        self.view_mode_changed.emit(mode)
        if self._selected_key:
            self._select_key(self._selected_key)

    def item_count(self) -> int:
        return len(self._items)

    def reload(self):
        self._items = media.list_media()
        self._start_poster_render()
        cats = sorted({i.category for i in self._items})
        prev = self._cat_combo.currentData()
        self._cat_combo.blockSignals(True)
        self._cat_combo.clear()
        self._cat_combo.addItem("All categories", None)
        for c in cats:
            self._cat_combo.addItem(c, c)
        if prev in cats:
            self._cat_combo.setCurrentIndex(cats.index(prev) + 1)
        self._cat_combo.blockSignals(False)
        self._apply_filter()

    def _start_poster_render(self):
        """Kick off (or restart) the background render for anything still missing
        a poster. A no-op — and importantly, no thread — when nothing is pending,
        which is the steady state once the cache is warm."""
        pending = media.pending_posters(self._items)
        if not pending:
            return
        self._stop_poster_worker()
        self._poster_worker = _PosterWorker(pending, self)
        self._poster_worker.done.connect(self._on_posters_rendered)
        self._poster_worker.start()

    def _on_posters_rendered(self, made: int):
        # Emitted from inside run() as it returns, so the thread is still
        # finishing: drop the reference through drain_worker (wait → deleteLater),
        # never a bare deleteLater — that leaves a live QThread parented here with
        # nobody holding it, and closing the window then qFatals (SIGABRT).
        self._poster_worker = drain_worker(self._poster_worker)
        if made:
            self._rebuild_views()

    def _stop_poster_worker(self):
        if self._poster_worker is not None:
            self._poster_worker.cancel()
            self._poster_worker = drain_worker(self._poster_worker)

    def closeEvent(self, event):
        self._stop_poster_worker()
        super().closeEvent(event)

    def restyle(self):
        self._rebuild_views()

    # ---- filtering ------------------------------------------------------
    def _kind_filter(self) -> str:
        for key, b in self._kind_btns.items():
            if b.isChecked():
                return key
        return "all"

    def _apply_filter(self):
        q = self._search.text().strip().lower()
        cat = self._cat_combo.currentData()
        kind = self._kind_filter()
        self._visible = [
            i for i in self._items
            if (cat is None or i.category == cat)
            and (kind == "all" or i.kind == kind)
            and (not q or q in i.name.lower() or q in i.category.lower()
                 or q in i.subfolder.lower())
        ]
        self._rebuild_views()
        self._update_stat()

    def _update_stat(self):
        if not self._items:
            self._stat.setText("<i>No media yet — import lunar/planetary/scenery "
                               "photos or videos.</i>")
            return
        photos = sum(1 for i in self._visible if i.kind == "photo")
        videos = len(self._visible) - photos
        total = sum(i.size_bytes for i in self._visible)
        self._stat.setText(f"{photos} photos · {videos} videos · {fmt_size(total)}")

    # ---- views ----------------------------------------------------------
    def _rebuild_views(self):
        prev = self._selected_key
        self._fill_table()
        self._fill_grid()
        if prev and not self._select_key(prev):
            self._show_selection(None)

    def _fill_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._row_items = {}
        self.table.setRowCount(len(self._visible))
        for row, it in enumerate(self._visible):
            label = f"{it.subfolder}/{it.name}" if it.subfolder else it.name
            name = NumItem(label, label.lower())
            name.setData(Qt.UserRole, it.key)
            name.setToolTip(str(it.path))
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(it.category))
            self.table.setItem(row, 2, QTableWidgetItem(
                "Video" if it.kind == "video" else "Photo"))
            self.table.setItem(row, 3, NumItem(fmt_date(it.captured), it.captured))
            self.table.setItem(row, 4, make_numeric(
                NumItem(fmt_size(it.size_bytes), float(it.size_bytes))))
            self._request_row_icon(it, name)
        self.table.setSortingEnabled(True)

    def _request_row_icon(self, item: media.MediaItem, cell: QTableWidgetItem):
        """Async row thumbnail.

        `RowThumbnails` can't serve here — it resolves `objects.hero_path(slug)`
        and media has no slug — but its safety shape is copied: the tracking dict
        is replaced on every rebuild, so a decode that lands after a rebuild finds
        either the current cell or nothing, never a deleted Qt item.
        """
        poster = media.poster_for(item, render=False)
        if poster is None:
            return
        self._row_items.setdefault(item.key, []).append(cell)
        self._thumb_loader.request(
            poster, ROW_THUMB_SIZE,
            lambda pm, key=item.key: self._apply_row_icon(key, pm))

    def _apply_row_icon(self, key: str, pm):
        if pm is None:
            return
        from PySide6.QtGui import QIcon
        for cell in self._row_items.get(key, []):
            cell.setIcon(QIcon(pm))

    def _fill_grid(self):
        tiles = []
        for it in self._visible:
            sub = f"{it.category} · {fmt_size(it.size_bytes)}"
            tiles.append(TileItem(
                key=it.key, thumb_path=media.poster_for(it, render=False),
                title=it.name, subtitle=sub,
                badge=VIDEO_BADGE if it.kind == "video" else ""))
        self._grid_model.set_items(tiles)
        self._grid_model.request_thumbnails(self._thumb_loader, self._zoom)

    def _on_zoom_changing(self, value: int):
        self._zoom = value
        self._grid_delegate.set_tile_size(value)
        self.grid_view.doItemsLayout()

    def _on_zoom_released(self):
        self._grid_model.request_thumbnails(self._thumb_loader, self._zoom)
        config.save_setting(MEDIA_ZOOM_KEY, self._zoom)

    # ---- selection ------------------------------------------------------
    def _item_for_key(self, key) -> media.MediaItem | None:
        return next((i for i in self._visible if i.key == key), None)

    def _item_for_row(self, row: int) -> media.MediaItem | None:
        cell = self.table.item(row, 0)
        return self._item_for_key(cell.data(Qt.UserRole)) if cell else None

    def _on_table_select(self):
        rows = self.table.selectionModel().selectedRows()
        self._show_selection(self._item_for_row(rows[0].row()) if rows else None)

    def _on_grid_select(self, *_):
        idxs = self.grid_view.selectionModel().selectedIndexes()
        self._show_selection(
            self._item_for_key(idxs[0].data(KEY_ROLE)) if idxs else None)

    def _show_selection(self, item: media.MediaItem | None):
        self._selected_key = item.key if item else None
        self.detail.show_item(item)
        self.detail.setVisible(item is not None)

    def _clear_selection(self):
        self.table.clearSelection()
        self.grid_view.clearSelection()
        self._show_selection(None)

    def _select_key(self, key: str) -> bool:
        item = self._item_for_key(key)
        if item is None:
            return False
        idx = self._grid_model.index_of(key)
        if idx.isValid():
            self.grid_view.selectionModel().select(
                idx, self.grid_view.selectionModel().SelectionFlag.ClearAndSelect)
        for row in range(self.table.rowCount()):
            cell = self.table.item(row, 0)
            if cell and cell.data(Qt.UserRole) == key:
                self.table.selectRow(row)
                break
        self._show_selection(item)
        return True

    # ---- opening --------------------------------------------------------
    def _open_item(self, item: media.MediaItem | None):
        """Photos open in the shared viewer, positioned within the currently
        filtered photo set so Prev/Next walks what the user is looking at;
        videos go to the OS player.

        Deferred: both entry points are item-view signals emitted from inside Qt's
        own C++ mouse handler, and a modal opened there keeps that frame alive
        across every event its nested loop pumps (`widgets.defer`).
        """
        if item is None:
            return
        if item.kind == "video":
            defer(self, lambda p=item.path: open_in_default(p))
            return
        photos = [i for i in self._visible if i.kind == "photo"]
        entries = [{"name": p.name, "path": str(p.path)} for p in photos]
        try:
            start = [p.key for p in photos].index(item.key)
        except ValueError:
            return
        defer(self, lambda: ImageViewer(entries, start, parent=self).exec())

    # ---- context menus ---------------------------------------------------
    def _table_menu(self, pos):
        row = self.table.rowAt(pos.y())
        self._item_menu(self._item_for_row(row) if row >= 0 else None,
                        self.table.viewport().mapToGlobal(pos))

    def _grid_menu(self, pos):
        idx = self.grid_view.indexAt(pos)
        self._item_menu(self._item_for_key(idx.data(KEY_ROLE)) if idx.isValid() else None,
                        self.grid_view.viewport().mapToGlobal(pos))

    def _item_menu(self, item: media.MediaItem | None, gpos):
        if item is None:
            return
        menu = QMenu(self)
        act_open = menu.addAction("Play" if item.kind == "video" else "Open")
        act_default = menu.addAction("Open in default app")
        act_reveal = menu.addAction("Reveal in file manager")
        act_export = menu.addAction("Export for sharing…") if item.kind == "photo" else None
        chosen = menu.exec(gpos)
        if chosen is None:
            return
        if chosen is act_open:
            self._open_item(item)
        elif chosen is act_default:
            open_in_default(item.path)
        elif chosen is act_reveal:
            reveal_in_manager(item.path)
        elif act_export is not None and chosen is act_export:
            self._show_selection(item)
            self.detail.export_current()
