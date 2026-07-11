"""Planning page — the home of session planning + location profiles.

The location profile is conceptually subordinate to planning, so it lives here
(not as its own nav pane): a **location selector** at the top picks the active
site profile the planner/prioritizer will read, a **Priority targets** table
(pins-only for now — the deterministic prioritizer scorer arrives in a later
pass), and a **Manage site profiles** collapsible section wrapping the
:class:`~m110.ui.site_profile_editor.SiteProfileEditor`.

Structured with persistent widgets (the selector + editor are built once and
just reloaded) so switching profiles doesn't rebuild the whole page.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QComboBox,
    QTableWidgetItem, QMenu, QFrame,
)

from m110 import catalog, derived, pins
from m110 import planning_config as pc
from m110.ui.widgets import make_table, fit_table_height, CollapsibleSection
from m110.ui.site_profile_editor import SiteProfileEditor


class PlanningPage(QScrollArea):
    open_object = Signal(str)
    pins_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._loading = False

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setAlignment(Qt.AlignTop)
        self.setWidget(content)

        title = QLabel("<b>Session Planning</b>")
        title.setTextFormat(Qt.RichText)
        lay.addWidget(title)
        cap = QLabel("Pick the location you're observing from, then see your "
                     "priority targets. The automatic prioritizer is coming.")
        cap.setProperty("caption", True)
        cap.setWordWrap(True)
        lay.addWidget(cap)

        # Location selector.
        loc = QHBoxLayout()
        loc.addWidget(QLabel("Location:"))
        self.selector = QComboBox()
        self.selector.currentIndexChanged.connect(self._on_location_changed)
        loc.addWidget(self.selector, 1)
        lay.addLayout(loc)

        # Priority targets.
        self._priority_sec = CollapsibleSection("Priority targets", expanded=True)
        lay.addWidget(self._priority_sec)

        # Manage site profiles.
        prof_sec = CollapsibleSection("Manage site profiles", expanded=False)
        frame = QFrame()
        frame.setObjectName("manageGoalsBox")
        frame.setFrameShape(QFrame.StyledPanel)
        fl = QVBoxLayout(frame)
        self.editor = SiteProfileEditor()
        self.editor.saved.connect(self._on_profile_saved)
        self.editor.created.connect(self._on_profile_created)
        self.editor.deleted.connect(self._on_profile_deleted)
        fl.addWidget(self.editor)
        prof_sec.body.addWidget(frame)
        lay.addWidget(prof_sec)

        self.reload()

    # ---- refresh ----
    def reload(self):
        self._reload_selector()
        self._reload_priority()

    def _reload_selector(self):
        self._loading = True
        self.selector.clear()
        active = pc.active_profile()
        active_row = 0
        for i, stem in enumerate(pc.list_profiles()):
            site = pc.load_site(stem)
            self.selector.addItem(site.name or stem, stem)
            if stem == active:
                active_row = i
        self.selector.setCurrentIndex(active_row)
        self._loading = False
        # Load the editor for the active profile (selector signal was suppressed).
        stem = self.selector.currentData()
        if stem:
            self.editor.load(stem)

    def _reload_priority(self):
        body = self._priority_sec.body
        while body.count():
            it = body.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        rows = self._priority_rows()
        cap = QLabel("In development — an automatic prioritizer is coming. For now, "
                     "pin objects from your Library (right-click → Pin as priority).")
        cap.setProperty("caption", True)
        cap.setWordWrap(True)
        body.addWidget(cap)
        if not rows:
            return
        pt = make_table(["Object", "Type", "Season", "Filter", "Progress"],
                        stretch_last=True)
        pt.setSortingEnabled(False)
        for row in rows:
            r = pt.rowCount()
            pt.insertRow(r)
            obj = QTableWidgetItem(row["label"])
            obj.setData(Qt.UserRole, row["slug"])
            pt.setItem(r, 0, obj)
            pt.setItem(r, 1, QTableWidgetItem(row["type"]))
            pt.setItem(r, 2, QTableWidgetItem(row["season"]))
            pt.setItem(r, 3, QTableWidgetItem(row["filter"]))
            pt.setItem(r, 4, QTableWidgetItem(row["progress"]))
        pt.resizeColumnsToContents()
        fit_table_height(pt, max_rows=12)
        pt.itemDoubleClicked.connect(
            lambda item: self._open_row(pt, item.row()))
        pt.setContextMenuPolicy(Qt.CustomContextMenu)
        pt.customContextMenuRequested.connect(
            lambda pos, t=pt: self._pin_menu(t, pos))
        body.addWidget(pt)

    def _priority_rows(self) -> list[dict]:
        try:
            lib = catalog.load_library()
        except Exception:
            lib = {}
        by_slug = derived.totals_by_slug()
        rows = []
        for slug in sorted(pins.pinned_slugs()):
            e = lib.get(slug)
            if not e:
                continue
            t = by_slug.get(slug)
            prog = (t.get("integration_hms") if t else "") or "not started"
            rows.append({
                "label": f"▲ {e.get('id') or slug}", "slug": slug,
                "type": (e.get("type") or "").replace("_", " "),
                "season": e.get("season") or "",
                "filter": e.get("filter") or "",
                "progress": prog,
            })
        return rows

    # ---- routing / context menu ----
    def _open_row(self, tbl, row: int):
        item = tbl.item(row, 0)
        slug = item.data(Qt.UserRole) if item else None
        if slug:
            self.open_object.emit(slug)

    def _pin_menu(self, tbl, pos):
        item = tbl.itemAt(pos)
        if item is None:
            return
        slug = tbl.item(item.row(), 0).data(Qt.UserRole)
        if not slug:
            return
        state = pins.get_state(slug)
        menu = QMenu(self)
        pin_act = menu.addAction("Unpin from priorities" if state == pins.PIN
                                 else "Pin as priority")
        depri_act = menu.addAction("Un-deprioritize" if state == pins.DEPRIORITIZE
                                   else "Deprioritize")
        chosen = menu.exec(tbl.viewport().mapToGlobal(pos))
        if chosen is pin_act:
            pins.set_state(slug, None if state == pins.PIN else pins.PIN)
        elif chosen is depri_act:
            pins.set_state(slug, None if state == pins.DEPRIORITIZE else pins.DEPRIORITIZE)
        else:
            return
        self.pins_changed.emit()

    # ---- selector / editor wiring ----
    def _on_location_changed(self, _idx: int):
        if self._loading:
            return
        stem = self.selector.currentData()
        if not stem:
            return
        pc.set_active_profile(stem)
        self.editor.load(stem)

    def _on_profile_saved(self, stem: str):
        # Name may have changed → refresh the selector label, keep selection.
        self._reload_selector_keeping(stem)

    def _on_profile_created(self, stem: str):
        pc.set_active_profile(stem)
        self._reload_selector_keeping(stem)

    def _on_profile_deleted(self, _stem: str):
        # delete_profile already reset the active profile to default if needed.
        self._reload_selector()

    def _reload_selector_keeping(self, stem: str):
        pc.set_active_profile(stem)
        self._reload_selector()
