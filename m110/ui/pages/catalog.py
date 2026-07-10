"""Catalog page — the catalog joined with capture status (master table +
grid), toggleable, + the shared per-object detail pane. Hosts object
selection; other pages route here via `select_object`. Sort persists across
in-session rebuilds; list/grid choice and grid zoom persist across launches."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QStackedWidget, QTableWidget,
    QTableWidgetItem, QMessageBox, QInputDialog, QLineEdit, QLabel, QComboBox,
    QMenu, QListView, QSlider, QToolButton,
)

from m110 import config, derived, objects, pins, siril, catalog as catalog_mod
from m110.catalog import (
    load_library, catalog_sort_key, season_sort_key, object_identifiers,
    object_label, list_bundled_catalogs,
)
from m110.ui.detail import DetailPane
from m110.ui.image_grid import TileItem, TileModel, TileDelegate, KEY_ROLE
from m110.ui.widgets import (
    NumItem, status_label, status_color, muted_color, targets_for_slug,
    StatusPillDelegate, STATUS_ROLE, make_numeric,
    ThumbnailLoader, RowThumbnails, ROW_THUMB_SIZE,
)

LIBRARY_VIEW_KEY = "library_view_mode"   # "list" | "grid"
LIBRARY_ZOOM_KEY = "library_grid_zoom"   # int px
GRID_ZOOM_MIN = 80
GRID_ZOOM_MAX = 220
GRID_ZOOM_DEFAULT = 140


class _EnrichOneWorker(QThread):
    """Online (Simbad) enrichment for a single object, off the UI thread."""
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, slug, parent=None):
        super().__init__(parent)
        self._slug = slug

    def run(self):
        try:
            self.done.emit(catalog_mod.fill_missing_metadata(self._slug, online=True))
        except catalog_mod.OnlineLookupError as e:
            self.failed.emit(str(e))
        except Exception as e:                           # pragma: no cover - defensive
            self.failed.emit(f"{type(e).__name__}: {e}")


class CatalogPage(QWidget):
    HEADERS = ["Object", "Name", "Type", "Season", "Mag", "Size", "Filter",
               "Status", "Integration", "Sessions"]

    editing_changed = Signal(bool)   # journal editor open/close (shell locks nav)
    dirty = Signal()                 # disk changed (import) → shell should refresh
    notes_saved = Signal(str)        # Object Notes saved → shell reloads other views
    pins_changed = Signal()          # Pin/Deprioritize override toggled → lightweight reload (#3)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cat = load_library()
        self._totals = derived.totals_by_slug()
        self._sort_col = 0
        self._sort_order = Qt.AscendingOrder
        self._catalog_filter = None       # None = all objects; else a catalog id
        self._catalogs = list_bundled_catalogs()
        self._enrich_worker = None        # in-flight online enrichment (single)
        self._thumb_loader = ThumbnailLoader(self)
        self._thumbs = RowThumbnails(self._thumb_loader)
        self._all_tile_items: list[TileItem] = []

        # Grid (thumbnail) is the default "home" view — the Lightroom-style wall of
        # objects. A user's explicit list/grid/feed choice persists and overrides this.
        view_mode = config.get_setting(LIBRARY_VIEW_KEY, "grid")
        self._view_mode = view_mode if view_mode in ("list", "grid", "feed") else "grid"
        zoom = config.get_setting(LIBRARY_ZOOM_KEY, GRID_ZOOM_DEFAULT)
        self._zoom = max(GRID_ZOOM_MIN, min(GRID_ZOOM_MAX, int(zoom)))

        self.table = self._build_table()
        self.table.itemSelectionChanged.connect(self._on_table_select)

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
        self.grid_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid_view.customContextMenuRequested.connect(self._on_context_menu)

        # Feed view = the reverse-chron object-card feed (absorbs the Journal pane).
        from m110.ui.pages.journal import JournalPage
        self.feed_view = JournalPage()
        self.feed_view.open_object.connect(self.select_object)   # card → detail

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self.table)          # 0
        self._view_stack.addWidget(self.grid_view)      # 1
        self._view_stack.addWidget(self.feed_view)      # 2
        self._view_stack.setCurrentWidget(self._view_widget(self._view_mode))

        self.detail = DetailPane()
        self.detail.editing_changed.connect(self._on_detail_editing)
        self.detail.import_requested.connect(self._on_import)
        self.detail.saved.connect(self.notes_saved)      # re-emit to the shell
        self.detail.closed.connect(self._on_detail_closed)
        self.detail.hide()                                # nothing selected yet

        # Left side: catalog selector + view segment + zoom + search + stat row.
        cat_row = QHBoxLayout()
        # The catalog filter (label + combo) only applies to the object views, so
        # it's wrapped for hide/show — the Feed view has its own search and no
        # catalog scoping.
        self._filter_bar = QWidget()
        fb = QHBoxLayout(self._filter_bar)
        fb.setContentsMargins(0, 0, 0, 0)
        fb.addWidget(QLabel("Catalog:"))
        self._catalog_combo = QComboBox()
        self._catalog_combo.addItem("All objects", None)
        for c in self._catalogs:
            self._catalog_combo.addItem(f"{c['name']} ({len(c['members'])})", c["id"])
        self._catalog_combo.currentIndexChanged.connect(self._on_catalog_changed)
        fb.addWidget(self._catalog_combo, 1)
        cat_row.addWidget(self._filter_bar, 1)

        # Its own bottom row (not cat_row) — a fixed-width slider appearing/
        # disappearing inline next to the stretchy catalog combo shifted every
        # widget after it (the toggle button included) each time grid mode
        # switched on/off. A status-bar-style row below the views is immune
        # to that: nothing else lives in it, so nothing else can move.
        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setMinimum(GRID_ZOOM_MIN)
        self._zoom_slider.setMaximum(GRID_ZOOM_MAX)
        self._zoom_slider.setValue(self._zoom)
        self._zoom_slider.setFixedWidth(120)
        self._zoom_slider.setToolTip("Tile size")
        self._zoom_slider.valueChanged.connect(self._on_zoom_changing)
        self._zoom_slider.sliderReleased.connect(self._on_zoom_released)
        zoom_row = QHBoxLayout()
        zoom_row.setContentsMargins(0, 2, 0, 2)   # a thin status-bar strip
        zoom_row.addStretch(1)
        zoom_row.addWidget(QLabel("Tile size:"))
        zoom_row.addWidget(self._zoom_slider)
        self._zoom_row_widget = QWidget()
        self._zoom_row_widget.setLayout(zoom_row)
        self._zoom_row_widget.setVisible(self._view_mode == "grid")

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        self._stat = QLabel()
        self._stat.setProperty("muted", True)

        left = QWidget()
        self._left_lay = QVBoxLayout(left)
        self._left_lay.setContentsMargins(0, 0, 0, 0)
        self._left_lay.addLayout(cat_row)
        self._left_lay.addWidget(self._search)
        self._left_lay.addWidget(self._stat)
        self._left_lay.addWidget(self._view_stack)
        self._left_lay.addWidget(self._zoom_row_widget)

        # Initial Feed-mode chrome (the button-sync guard short-circuits _set_view_mode
        # for the already-current mode, so set the Feed's control visibility here).
        if self._view_mode == "feed":
            self._filter_bar.hide()
            self._search.hide()
            self._stat.hide()
            self.detail.hide()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.detail)
        self.splitter.setSizes([560, 460])

        # Segmented scope: Deep sky (catalog objects) vs Media (lunar/planetary/
        # scenery/startrails) — the same page, two content stacks. Absorbs the
        # former Media pane; the deep-sky controls live inside the deep-sky stack
        # page, so switching to Media hides them without extra bookkeeping.
        from m110.ui.pages.media import MediaPage
        self.media_view = MediaPage(show_title=False)
        self._scope_stack = QStackedWidget()
        self._scope_stack.addWidget(self.splitter)      # 0 = deep sky
        self._scope_stack.addWidget(self.media_view)    # 1 = media

        # One control row: Deep sky · Media (left) + List · Grid · Feed (right), each
        # a joined segmented control. Fixed positions — the view segment no longer
        # rides on the (hideable) catalog filter, so it can't shift in Feed mode.
        self._scope_seg, self._scope_group, scope_btns = self._make_segment(
            [("deep", "Deep sky"), ("media", "Media")], "deep")
        self._deepsky_btn, self._media_btn = scope_btns["deep"], scope_btns["media"]
        self._deepsky_btn.toggled.connect(lambda on: on and self._set_scope(0))
        self._media_btn.toggled.connect(lambda on: on and self._set_scope(1))
        self._view_seg, self._view_group, self._view_btns = self._make_segment(
            [("list", "List"), ("grid", "Grid"), ("feed", "Feed")], self._view_mode)
        for mode, b in self._view_btns.items():
            b.toggled.connect(lambda on, m=mode: on and self._set_view_mode(m))

        controls = QHBoxLayout()
        controls.addWidget(self._scope_seg)
        controls.addStretch(1)
        controls.addWidget(self._view_seg)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(controls)
        lay.addWidget(self._scope_stack, 1)

        self._all_tile_items = self._build_tile_items()
        self._apply_filter()               # first grid population
        self._update_stat()

    @property
    def _status_col(self) -> int:
        return self.HEADERS.index("Status")

    # ---- shell hooks ----
    def is_editing(self) -> bool:
        return self.detail.is_editing()

    def set_locked(self, locked: bool):
        self.table.setEnabled(not locked)
        self.grid_view.setEnabled(not locked)

    def select_object(self, slug: str):
        # Route from another page (or a Feed card) → show the Deep-sky scope (not
        # Media), switch out of the Feed to a selectable view, and ensure the target
        # row isn't filtered out (clear search + catalog filter).
        self._deepsky_btn.setChecked(True)
        if self._view_mode == "feed":
            self._set_view_mode("grid")
        self._search.clear()
        if self._catalog_filter is not None:
            self._catalog_combo.setCurrentIndex(0)   # "All objects" → triggers rebuild
        self._select_slug(slug)

    def _on_catalog_changed(self, _idx: int):
        self._catalog_filter = self._catalog_combo.currentData()
        self._rebuild_views()
        self._update_stat()

    def restyle(self):
        """Theme changed — repaint views (status/muted colors) from new tokens."""
        self._rebuild_views()

    # ---- segmented controls (Deep sky|Media, List|Grid|Feed) ----
    def _make_segment(self, items, active_key):
        """A joined macOS-style segmented control: exclusive checkable buttons packed
        into a bordered frame (`#segControl` / `#segButton` in the QSS). `items` =
        [(key, label)]. Returns (frame, group, {key: button})."""
        from PySide6.QtWidgets import QButtonGroup, QFrame
        frame = QFrame()
        frame.setObjectName("segControl")
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        group = QButtonGroup(frame)
        group.setExclusive(True)
        btns: dict[str, QToolButton] = {}
        n = len(items)
        for i, (key, label) in enumerate(items):
            b = QToolButton()
            b.setObjectName("segButton")
            # Position so the QSS can round only the outer corners of the end buttons.
            b.setProperty("segpos", "solo" if n == 1 else
                          "first" if i == 0 else "last" if i == n - 1 else "mid")
            b.setText(label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            group.addButton(b)
            btns[key] = b
            row.addWidget(b)
        btns[active_key].setChecked(True)
        return frame, group, btns

    def _set_scope(self, idx: int):
        self._scope_stack.setCurrentIndex(idx)
        # Media has no List/Grid/Feed views (yet), so hide the segment in Media scope.
        # (When Media gains its own grid/list/journal views, show + enable it instead.)
        self._view_seg.setVisible(idx == 0)
        if idx == 1:                          # entering Media → refresh its contents
            self.media_view.reload()

    def reload(self):
        if self._scope_stack.currentIndex() == 1:   # keep the Media scope fresh
            self.media_view.reload()
        if self._view_mode == "feed":                # keep the Feed fresh when active
            self.feed_view.reload()
        new_cat = load_library()
        new_totals = derived.totals_by_slug()
        changed = (new_cat != self._cat) or (new_totals != self._totals)
        self._cat, self._totals = new_cat, new_totals
        if changed:
            self._rebuild_views()          # preserves selection + sort
            self._update_stat()
        else:
            self._refresh_open_detail()    # cheap: pick up image-only changes

    def _update_stat(self):
        members = self._filter_members()
        slugs = [s for s in self._cat if members is None or s in members]
        captured = sum(1 for s in slugs if s in self._totals)
        deep = sum(1 for s in slugs
                   if self._totals.get(s, {}).get("status") == "deep_stack")
        # Fresh, unfiltered Library with nothing in it → an orienting hint instead
        # of a bare "0 total" (#onboarding).
        if not self._cat and self._catalog_filter is None and not self._search.text().strip():
            self._stat.setText("Your Library is empty — Import from your telescope "
                               "(Ctrl+I) or add an object from the Library menu.")
            return
        prefix = ""
        if self._catalog_filter:
            name = next((c["name"] for c in self._catalogs
                         if c["id"] == self._catalog_filter), self._catalog_filter)
            prefix = f"{name} — "
        integ_min = sum(self._totals.get(s, {}).get("integration_min", 0)
                        for s in slugs if s in self._totals)
        integ = f" · {integ_min / 60:.1f}h integration" if integ_min else ""
        self._stat.setText(
            f"{prefix}{captured} captured · {deep} deep · {len(slugs)} total{integ}")

    def _apply_filter(self, *_):
        q = self._search.text().strip().lower()

        for r in range(self.table.rowCount()):
            hide = False
            if q:
                hay = " ".join(self.table.item(r, c).text() for c in (0, 1, 2)).lower()
                hide = q not in hay
            self.table.setRowHidden(r, hide)

        def keep(ti: TileItem) -> bool:
            if q:
                e = self._cat.get(ti.key, {})
                hay = f"{ti.title} {e.get('name', '')} " \
                      f"{str(e.get('type', '')).replace('_', ' ')}".lower()
                if q not in hay:
                    return False
            return True

        # QAbstractListModel.set_items() resets the model (Qt clears the
        # attached selection model's state on any reset, but does NOT
        # reliably re-emit selectionChanged for it) — QListView has no
        # setRowHidden equivalent, so narrowing the grid means rebuilding its
        # data, not hiding rows like the table. Preserve + restore the
        # selection across that reset so typing in the search box doesn't
        # silently drop it on every keystroke; if the selected object no
        # longer matches, explicitly hide the (now stale) detail pane rather
        # than relying on a selectionChanged signal that may not fire.
        prev = self._selected_slug() if self._view_mode == "grid" else None
        self._grid_model.set_items([ti for ti in self._all_tile_items if keep(ti)])
        self._grid_model.request_thumbnails(self._thumb_loader, self._zoom)
        if prev and not self._select_slug(prev):
            self._show_selection(None)

    def _filter_members(self) -> set | None:
        """Slugs of the selected catalog, or None for 'All objects'."""
        if not self._catalog_filter:
            return None
        for c in self._catalogs:
            if c["id"] == self._catalog_filter:
                return set(c["members"])
        return set()

    # ---- shared data (table + grid both build from this) ----
    def _current_items(self):
        """Catalog-filtered + naturally sorted (slug, entry) pairs, plus the
        per-slug identifier list — the source both views build from."""
        cat = self._cat
        self._pins = pins.load()          # slug → "pin"|"deprioritize", for the row markers
        members = self._filter_members()
        pc = self._catalog_filter
        items = [(slug, e) for slug, e in cat.items()
                 if members is None or slug in members]
        ids = {slug: object_identifiers(slug, e, primary_catalog=pc)
               for slug, e in items}
        items.sort(key=lambda kv: catalog_sort_key(ids[kv[0]][0] if ids[kv[0]] else ""))
        return items, ids

    def reload_pins(self):
        """Re-read Pin/Deprioritize state and refresh the row markers, preserving
        selection — used when a pin is toggled elsewhere (Goals / Summary, #3)."""
        prev = self._selected_slug()
        self._rebuild_views()
        if prev:
            self._select_slug(prev)

    def _pin_marker(self, slug: str) -> str:
        """A ▲ (pinned) / ▼ (muted) prefix for an object label, or '' (#3)."""
        st = getattr(self, "_pins", {}).get(slug)
        return "▲ " if st == pins.PIN else "▼ " if st == pins.DEPRIORITIZE else ""

    def _build_tile_items(self) -> list[TileItem]:
        totals = self._totals
        items, ids = self._current_items()
        out = []
        for slug, e in items:
            t = totals.get(slug, {})
            captured = bool(t)
            subtitle = (f"{t.get('integration_hms', '')} · "
                        f"{t.get('session_count', '')} sessions") if captured else ""
            out.append(TileItem(
                key=slug,
                thumb_path=objects.hero_path(slug) if captured else None,
                title=self._pin_marker(slug) + object_label(ids[slug]),
                subtitle=subtitle,
                status=t.get("status") if captured else None,
                muted=not captured,
            ))
        return out

    # ---- table ----
    def _build_table(self) -> QTableWidget:
        totals = self._totals
        items, ids = self._current_items()

        table = QTableWidget(len(items), len(self.HEADERS))
        table.setHorizontalHeaderLabels(self.HEADERS)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)
        table.setAlternatingRowColors(True)
        table.setItemDelegateForColumn(self._status_col, StatusPillDelegate(table))
        table.setIconSize(QSize(ROW_THUMB_SIZE, ROW_THUMB_SIZE))
        self._thumbs.reset()

        for row, (slug, e) in enumerate(items):
            t = totals.get(slug, {})
            captured = bool(t)

            oid = ids[slug]
            obj = NumItem(self._pin_marker(slug) + object_label(oid),
                          catalog_sort_key(oid[0] if oid else ""))
            obj.setData(Qt.UserRole, slug)
            table.setItem(row, 0, obj)
            if captured:
                self._thumbs.add(slug, obj)
            table.setItem(row, 1, QTableWidgetItem(str(e.get("name") or "")))
            table.setItem(row, 2, QTableWidgetItem(str(e.get("type") or "").replace("_", " ")))
            season = str(e.get("season") or "")
            table.setItem(row, 3, NumItem(season, season_sort_key(season)))

            mag = e.get("magnitude")
            table.setItem(row, 4, make_numeric(NumItem("" if mag is None else f"{mag}",
                                          float(mag) if mag is not None else 99.0)))
            table.setItem(row, 5, QTableWidgetItem(str(e.get("size") or "")))
            table.setItem(row, 6, QTableWidgetItem(str(e.get("filter") or "")))

            status_item = QTableWidgetItem(status_label(t.get("status"), captured))
            status_item.setForeground(status_color(t.get("status")) if captured else muted_color())
            status_item.setData(STATUS_ROLE, t.get("status") if captured else None)
            table.setItem(row, self._status_col, status_item)

            integ_min = float(t.get("integration_min", 0) or 0)
            table.setItem(row, 8, make_numeric(
                NumItem(t.get("integration_hms", "") if captured else "", integ_min)))
            sc = int(t.get("session_count", 0) or 0)
            table.setItem(row, 9, make_numeric(
                NumItem(str(sc) if captured else "", float(sc))))

            if not captured:
                for c in range(len(self.HEADERS)):
                    if c != self._status_col:
                        table.item(row, c).setForeground(muted_color())

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

    def _rebuild_views(self):
        prev = self._selected_slug()
        new_table = self._build_table()
        new_table.itemSelectionChanged.connect(self._on_table_select)
        self._view_stack.removeWidget(self.table)
        self.table.deleteLater()
        self.table = new_table
        self._view_stack.insertWidget(0, self.table)
        self._view_stack.setCurrentWidget(
            self.table if self._view_mode == "list" else self.grid_view)
        self._all_tile_items = self._build_tile_items()
        self._apply_filter()
        if not (prev and self._select_slug(prev)):
            self.detail.placeholder()
            self.detail.hide()

    # ---- view-agnostic selection ----
    def _selected_slug(self):
        if self._view_mode == "list":
            items = self.table.selectedItems()
            return self.table.item(items[0].row(), 0).data(Qt.UserRole) if items else None
        sel = self.grid_view.selectionModel().selectedIndexes()
        return sel[0].data(KEY_ROLE) if sel else None

    def _select_slug(self, slug) -> bool:
        if self._view_mode == "list":
            for r in range(self.table.rowCount()):
                if self.table.item(r, 0).data(Qt.UserRole) == slug:
                    self.table.selectRow(r)
                    self.table.scrollToItem(self.table.item(r, 0))
                    return True
            return False
        idx = self._grid_model.index_of(slug)
        if not idx.isValid():
            return False
        self.grid_view.setCurrentIndex(idx)
        self.grid_view.selectionModel().select(
            idx, self.grid_view.selectionModel().SelectionFlag.ClearAndSelect)
        self.grid_view.scrollTo(idx)
        return True

    def _on_table_select(self):
        if self._view_mode != "list":
            return
        self._show_selection(self._selected_slug())

    def _on_grid_select(self, *_args):
        if self._view_mode != "grid":
            return
        self._show_selection(self._selected_slug())

    def _show_selection(self, slug):
        if not slug:
            self.detail.hide()
            return
        self.detail.show_object(slug, self._cat[slug], self._totals.get(slug, {}))
        self.detail.show()

    def _on_detail_closed(self):
        if self._view_mode == "list":
            self.table.clearSelection()
        else:
            self.grid_view.clearSelection()

    def _refresh_open_detail(self):
        slug = self._selected_slug()
        if slug and slug in self._cat:
            self.detail.show_object(slug, self._cat[slug], self._totals.get(slug, {}))

    # ---- view toggle + zoom ----
    def _view_widget(self, mode: str) -> QWidget:
        return {"list": self.table, "grid": self.grid_view,
                "feed": self.feed_view}[mode]

    def _set_view_mode(self, mode: str):
        if mode == self._view_mode:
            return
        prev_slug = self._selected_slug()
        self._view_mode = mode
        feed = mode == "feed"
        self._view_stack.setCurrentWidget(self._view_widget(mode))
        self._zoom_row_widget.setVisible(mode == "grid")
        # Feed has its own search + no catalog scoping — hide the object-view chrome.
        self._filter_bar.setVisible(not feed)
        self._search.setVisible(not feed)
        self._stat.setVisible(not feed)
        config.save_setting(LIBRARY_VIEW_KEY, mode)
        # Keep the segment buttons in sync when the mode is set programmatically
        # (e.g. select_object switching Feed → Grid); setChecked only re-enters
        # _set_view_mode with the same mode, which the guard above no-ops.
        if not self._view_btns[mode].isChecked():
            self._view_btns[mode].setChecked(True)
        if feed:
            self.feed_view.reload()
            self.detail.hide()                 # no per-object detail in the feed
            return
        if prev_slug:
            self._select_slug(prev_slug)
        else:
            self._view_widget(mode).clearSelection()

    def _on_zoom_changing(self, value: int):
        self._zoom = value
        self._grid_delegate.set_tile_size(value)
        self.grid_view.doItemsLayout()

    def _on_zoom_released(self):
        self._grid_model.request_thumbnails(self._thumb_loader, self._zoom)
        config.save_setting(LIBRARY_ZOOM_KEY, self._zoom)

    # ---- editing lock ----
    def _on_detail_editing(self, editing: bool):
        self.table.setEnabled(not editing)
        self.grid_view.setEnabled(not editing)
        self.editing_changed.emit(editing)

    # ---- context menu: fill / enrich metadata ----
    def _slug_at(self, pos):
        if self._view_mode == "list":
            item = self.table.itemAt(pos)
            return self.table.item(item.row(), 0).data(Qt.UserRole) if item else None
        idx = self.grid_view.indexAt(pos)
        return idx.data(KEY_ROLE) if idx.isValid() else None

    def _on_context_menu(self, pos):
        slug = self._slug_at(pos)
        if slug is None:
            return
        entry = self._cat.get(slug, {})
        missing = bool(catalog_mod._compute_fill(entry, catalog_mod.load_reference().get(slug, {})))
        has_gaps = catalog_mod._has_gaps({**entry,
            **catalog_mod._compute_fill(entry, catalog_mod.load_reference().get(slug, {}))})
        menu = QMenu(self)
        fill_act = menu.addAction("Fill in missing metadata")
        fill_act.setEnabled(missing)
        online_act = menu.addAction("Enrich online")
        online_act.setEnabled(has_gaps and self._enrich_worker is None)
        menu.addSeparator()
        published = entry.get("publish", True) is not False
        publish_act = menu.addAction(
            "Exclude from publishing" if published else "Include in publishing")
        menu.addSeparator()
        state = pins.get_state(slug)
        pin_act = menu.addAction("Unpin from priorities" if state == pins.PIN
                                 else "Pin as priority")
        depri_act = menu.addAction("Un-deprioritize" if state == pins.DEPRIORITIZE
                                   else "Deprioritize")
        menu.addSeparator()
        remove_act = menu.addAction("Remove from Library")
        viewport = self.table.viewport() if self._view_mode == "list" else self.grid_view.viewport()
        chosen = menu.exec(viewport.mapToGlobal(pos))
        if chosen is fill_act and missing:
            self._fill_one(slug)
        elif chosen is online_act and has_gaps:
            self._enrich_one_online(slug)
        elif chosen is publish_act:
            self._toggle_publish(slug, not published)
        elif chosen is pin_act:
            self._set_pin(slug, None if state == pins.PIN else pins.PIN)
        elif chosen is depri_act:
            self._set_pin(slug, None if state == pins.DEPRIORITIZE else pins.DEPRIORITIZE)
        elif chosen is remove_act:
            self._remove_one(slug)

    def _set_pin(self, slug: str, state):
        """Apply a Pin/Deprioritize/clear override, refresh the marker, keep selection (#3)."""
        pins.set_state(slug, state)
        self._rebuild_views()
        self._select_slug(slug)
        self.pins_changed.emit()

    def _toggle_publish(self, slug: str, publish: bool):
        if catalog_mod.set_publish_flag(slug, publish):
            self._cat = load_library()
            self._rebuild_views()
            self._select_slug(slug)

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
        self._rebuild_views()
        self._select_slug(slug)
        fields = ", ".join(sorted(filled))
        QMessageBox.information(self, "Metadata filled",
                               f"Filled from the reference: {fields}.")

    def _remove_one(self, slug: str):
        oid = self._cat.get(slug, {}).get("id") or slug
        if slug in self._totals:
            # Captured objects ARE the collection — removing one is futile: the next
            # refresh re-promotes any capture folder (add_captured_objects). Explain
            # instead of removing-then-reappearing.
            QMessageBox.information(
                self, "Can't remove",
                f"{oid} has captures, so it's part of your collection and would "
                "reappear on the next refresh.\n\nTo drop it, remove its capture "
                "folders under Images/ first.")
            return
        if QMessageBox.question(
                self, "Remove from Library",
                f"Remove {oid} from your Library? Its journal/notes are kept.") \
                != QMessageBox.Yes:
            return
        if catalog_mod.remove_library_entry(slug):
            self._cat = load_library()
            self._rebuild_views()
            self._update_stat()

    def _enrich_one_online(self, slug: str):
        if self._enrich_worker is not None:
            return
        self._enrich_worker = _EnrichOneWorker(slug, self)
        self._enrich_worker.done.connect(lambda f: self._on_enrich_one(slug, f))
        self._enrich_worker.failed.connect(self._on_enrich_one_failed)
        self._enrich_worker.finished.connect(self._clear_enrich_worker)
        self._enrich_worker.start()

    def _on_enrich_one(self, slug: str, filled: dict):
        if not filled:
            QMessageBox.information(self, "Nothing to enrich",
                                   "Simbad had nothing to add for this object.")
            return
        self._cat = load_library()
        self._rebuild_views()
        self._select_slug(slug)
        QMessageBox.information(self, "Enriched online",
                               f"Filled from Simbad: {', '.join(sorted(filled))}.")

    def _on_enrich_one_failed(self, msg: str):
        QMessageBox.warning(self, "Online lookup unavailable", msg)

    def _clear_enrich_worker(self):
        self._enrich_worker = None

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
