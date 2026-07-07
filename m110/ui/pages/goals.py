"""Goals page — select / create / edit the catalogs and custom object lists the
user is pursuing, and show per-goal progress. As of Phase 5d the Library is the
captured/annotated collection; this page is where uncaptured catalog members live
as a checklist (rather than being bulk-seeded into the Library).

Activating/deactivating a goal writes the per-store goals.toml (and a deactivation
prunes uncaptured/un-noted/not-in-another-goal members) — so a toggle emits
`dirty`, which the shell turns into a refresh + reload."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidgetItem,
    QCheckBox, QPushButton, QInputDialog, QMessageBox, QFrame, QToolButton,
    QHeaderView, QMenu,
)

from m110 import goals as goals_mod, derived, catalog, pins
from m110.ui.widgets import make_table
from m110.ui.theme import status_color


# Order + display label for the expandable goal groups. `hemisphere` values from
# goals.list_goals() ("northern"/"southern"/"allsky"/"custom") map onto these.
_GROUPS = [
    ("allsky", "All-sky"),
    ("northern", "Northern hemisphere"),
    ("southern", "Southern hemisphere"),
    ("custom", "Custom goals"),
]


class _CollapsibleSection(QWidget):
    """A titled group whose body can be toggled open/closed via its header.

    `on_toggle(expanded)` is invoked on every state change so the owning page can
    persist the open/closed state across a rebuild (the page reloads on window
    focus, which would otherwise reset every section to its default)."""

    def __init__(self, title: str, expanded: bool = True, on_toggle=None, parent=None):
        super().__init__(parent)
        self._on_toggle = on_toggle
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._btn = QToolButton()
        self._btn.setText(title)
        self._btn.setCheckable(True)
        self._btn.setChecked(expanded)
        self._btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._btn.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self._btn.toggled.connect(self._on_toggled)
        lay.addWidget(self._btn)
        self._body = QWidget()
        self.body = QVBoxLayout(self._body)
        self.body.setContentsMargins(18, 2, 0, 6)
        lay.addWidget(self._body)
        self._body.setVisible(expanded)

    def _on_toggled(self, on: bool):
        self._btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self._body.setVisible(on)
        if self._on_toggle is not None:
            self._on_toggle(on)


class GoalsPage(QScrollArea):
    open_object = Signal(str)     # row → Catalog detail
    dirty = Signal()              # active set / custom goals changed → shell refresh
    pins_changed = Signal()       # Pin/Mute override toggled on a member row (#3)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        self.setWidget(self._content)
        self._building = False
        self._expanded: dict[str, bool] = {}   # group key → open state, kept across reloads
        self.reload()

    # ---- helpers ----
    def _clear(self):
        while self._lay.count():
            it = self._lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            elif it.layout() is not None:
                self._drop_layout(it.layout())

    def _drop_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            elif it.layout() is not None:
                self._drop_layout(it.layout())
        lay.deleteLater()

    def _heading(self, text):
        lbl = QLabel(f"<h3>{text}</h3>")
        lbl.setTextFormat(Qt.RichText)
        return lbl

    def _wire_open(self, table):
        def go(item):
            slug = table.item(item.row(), 0).data(Qt.UserRole)
            if slug:
                self.open_object.emit(slug)
        table.itemDoubleClicked.connect(go)

    # ---- build ----
    def reload(self):
        self._building = True
        self._clear()

        title = QLabel("<h2>Goals</h2>")
        title.setTextFormat(Qt.RichText)
        self._lay.addWidget(title)
        self._lay.addWidget(QLabel(
            "Catalogs and custom lists you're tracking. Uncaptured members show "
            "here as a checklist; capturing or annotating an object adds it to "
            "your Library."))

        self._build_tracking()
        self._build_progress()
        self._building = False

    def _build_tracking(self):
        self._lay.addWidget(self._heading("Tracking"))
        self._checks = {}

        by_group: dict[str, list[dict]] = {}
        for g in goals_mod.list_goals():
            by_group.setdefault(g["hemisphere"], []).append(g)

        for key, label in _GROUPS:
            goals_here = by_group.get(key, [])
            if not goals_here and key != "custom":
                continue  # hide empty hemispheres; always show Custom (holds "New…")
            # Expand a group by default if it holds an active goal (or it's Custom);
            # a state the user has toggled since launch wins (survives focus reloads).
            default = key == "custom" or any(g["active"] for g in goals_here)
            expand = self._expanded.get(key, default)
            section = _CollapsibleSection(
                label, expanded=expand,
                on_toggle=lambda on, k=key: self._expanded.__setitem__(k, on))
            for g in goals_here:
                section.body.addWidget(self._goal_row(g))
            if key == "custom":
                new_btn = QPushButton("New custom goal…")
                new_btn.clicked.connect(self._new_custom)
                new_row = QHBoxLayout()
                new_row.addWidget(new_btn)
                new_row.addStretch(1)
                section.body.addLayout(new_row)
            self._lay.addWidget(section)

    def _goal_row(self, g: dict) -> QWidget:
        """One goal: checkbox + count, description caption, source link, and (for
        custom goals) Edit/Delete buttons."""
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 2, 0, 2)
        col.setSpacing(1)

        top = QHBoxLayout()
        cb = QCheckBox(f"{g['name']}  ({g['total']})")
        cb.setChecked(g["active"])
        cb.toggled.connect(self._on_toggle)
        self._checks[g["id"]] = cb
        top.addWidget(cb)
        top.addStretch(1)
        if g["kind"] == "custom":
            edit = QPushButton("Edit…")
            edit.clicked.connect(lambda _=False, gid=g["id"]: self._edit_custom(gid))
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda _=False, gid=g["id"]: self._delete_custom(gid))
            top.addWidget(edit)
            top.addWidget(delete)
        col.addLayout(top)

        desc = (g.get("description") or "").strip()
        url = (g.get("source_url") or "").strip()
        if desc or url:
            meta = QLabel()
            meta.setProperty("caption", True)
            meta.setWordWrap(True)
            meta.setOpenExternalLinks(True)
            meta.setTextFormat(Qt.RichText)
            parts = []
            if desc:
                parts.append(desc)
            if url:
                parts.append(f'<a href="{url}">Learn more ↗</a>')
            meta.setText(" &nbsp;".join(parts))
            col.addWidget(meta)
        return w

    def _build_progress(self):
        goals_data = {g["id"]: g for g in derived.load_goals()}
        totals = derived.totals_by_slug()

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        self._lay.addWidget(line)

        active = [gid for gid in goals_mod.active_goal_ids()]
        if not active:
            self._lay.addWidget(QLabel("<i>No active goals.</i>"))
            return

        for gid in active:
            g = goals_data.get(gid)
            self._lay.addWidget(self._heading(goals_mod.goal_name(gid)))
            if g:
                self._lay.addWidget(QLabel(
                    f"{g['captured']} captured · {g['deep']} deep · {g['total']} total "
                    f"({g['percent']}%)"))
            self._lay.addWidget(self._catalog_table(gid, totals))

    def _catalog_table(self, gid: str, totals: dict):
        """The catalog's full membership: Object · Name · Captured · Deep stack,
        with a green check where the object has been captured / deep-stacked.
        Double-click a row → open the object."""
        members = goals_mod.goal_members(gid)   # {slug: designation}
        try:
            lib = catalog.load_library()
        except Exception:
            lib = {}
        ref = catalog.load_reference()

        pin_state = pins.load()
        tbl = make_table(["Object", "Name", "Captured", "Deep stack"])
        tbl.setSortingEnabled(False)            # keep natural catalog order
        green = QBrush(status_color("deep_stack"))
        slugs = sorted(members, key=lambda s: catalog.catalog_sort_key(members[s]))
        for slug in slugs:
            entry = lib.get(slug) or ref.get(slug)
            label = catalog.object_label(catalog.object_identifiers(slug, entry)) or slug
            st = pin_state.get(slug)
            marker = "▲ " if st == pins.PIN else "▼ " if st == pins.MUTE else ""
            name = (entry or {}).get("name") or members[slug]
            t = totals.get(slug)
            captured = t is not None
            deep = captured and t.get("status") == "deep_stack"

            r = tbl.rowCount()
            tbl.insertRow(r)
            obj = QTableWidgetItem(marker + label)
            obj.setData(Qt.UserRole, slug)
            tbl.setItem(r, 0, obj)
            tbl.setItem(r, 1, QTableWidgetItem(str(name or "")))
            tbl.setItem(r, 2, self._check_item(captured, green))
            tbl.setItem(r, 3, self._check_item(deep, green))

        hdr = tbl.horizontalHeader()
        tbl.resizeColumnsToContents()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)   # Name fills the row
        h = min(380, 24 * (len(slugs) + 1) + 10)           # cap tall catalogs → scroll
        tbl.setMinimumHeight(h)
        tbl.setMaximumHeight(h)
        self._wire_open(tbl)
        tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        tbl.customContextMenuRequested.connect(
            lambda pos, t=tbl: self._member_context_menu(t, pos))
        return tbl

    def _member_context_menu(self, tbl, pos):
        """Right-click a membership row → Pin/Mute/clear the object (#3)."""
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
        mute_act = menu.addAction("Unmute" if state == pins.MUTE else "Mute")
        chosen = menu.exec(tbl.viewport().mapToGlobal(pos))
        if chosen is pin_act:
            pins.set_state(slug, None if state == pins.PIN else pins.PIN)
        elif chosen is mute_act:
            pins.set_state(slug, None if state == pins.MUTE else pins.MUTE)
        else:
            return
        self.pins_changed.emit()

    @staticmethod
    def _check_item(on: bool, brush: QBrush) -> QTableWidgetItem:
        it = QTableWidgetItem("✓" if on else "")
        it.setTextAlignment(Qt.AlignCenter)
        if on:
            it.setForeground(brush)
        return it

    # ---- actions ----
    def _on_toggle(self, _checked: bool):
        if self._building:
            return
        chosen = [gid for gid, cb in self._checks.items() if cb.isChecked()]
        result = goals_mod.set_active_goals(chosen)
        removed = result.get("removed", [])
        if removed:
            QMessageBox.information(
                self, "Goal deactivated",
                f"Removed {len(removed)} uncaptured object(s) from your Library.")
        self.dirty.emit()

    def _new_custom(self):
        name, ok = QInputDialog.getText(self, "New custom goal", "Goal name:")
        if not ok or not name.strip():
            return
        members = self._ask_members()
        if members is None:
            return
        goals_mod.create_custom_goal(name.strip(), members)
        self.dirty.emit()

    def _edit_custom(self, gid: str):
        cur_name = goals_mod.goal_name(gid)
        name, ok = QInputDialog.getText(self, "Edit goal", "Goal name:", text=cur_name)
        if not ok or not name.strip():
            return
        cur = ", ".join(goals_mod.goal_members(gid))
        members = self._ask_members(preset=cur)
        if members is None:
            return
        goals_mod.edit_custom_goal(gid, name=name.strip(), members=members)
        self.dirty.emit()

    def _delete_custom(self, gid: str):
        if QMessageBox.question(
                self, "Delete goal",
                f"Delete the custom goal “{goals_mod.goal_name(gid)}”?") != \
                QMessageBox.Yes:
            return
        result = goals_mod.delete_custom_goal(gid)
        removed = result.get("removed", [])
        if removed:
            QMessageBox.information(
                self, "Goal deleted",
                f"Removed {len(removed)} uncaptured object(s) from your Library.")
        self.dirty.emit()

    def _ask_members(self, preset: str = "") -> list[str] | None:
        """Prompt for a comma/space/newline-separated list of designations; resolve
        each to a slug via the offline reference cascade. Unknown identifiers are
        kept verbatim (they still work as custom members). None = cancelled."""
        text, ok = QInputDialog.getMultiLineText(
            self, "Goal members",
            "Object designations (one per line, or comma-separated):", preset)
        if not ok:
            return None
        idents = [t.strip() for t in text.replace(",", "\n").splitlines() if t.strip()]
        slugs, seen = [], set()
        for ident in idents:
            slug = catalog.resolve_new_object(ident).get("slug", ident)
            if slug not in seen:
                seen.add(slug)
                slugs.append(slug)
        return slugs
