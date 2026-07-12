"""Overview page — the landing dashboard, merging the former Summary and Goals
pages into one pane of **collapsible sections** (the macOS disclosure pattern via
`widgets.CollapsibleSection`). Each section's open/closed state persists across
launches (settings key `overview_sections`), so each user keeps the layout they
want. Goal *progress* is the hero; goal *setup* (activate catalogs, custom goals)
is demoted to a collapsed "Manage goals" section.

Empty store → a welcome + guided-import CTA (goal progress still shows, since the
north-star is motivating even at 0%)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidgetItem,
    QHeaderView, QPushButton, QMenu, QCheckBox, QInputDialog, QMessageBox, QFrame,
)

from m110 import catalog, config, derived, pins, goals as goals_mod
from m110.ui.widgets import (
    NumItem, status_label, make_table, CollapsibleSection, fit_table_height,
)
from m110.ui.theme import status_color

# Manage-goals sub-groups (hemisphere), mirroring the former Goals page.
_GROUPS = [
    ("allsky", "All-sky"),
    ("northern", "Northern hemisphere"),
    ("southern", "Southern hemisphere"),
    ("custom", "Custom goals"),
]


class OverviewPage(QScrollArea):
    open_object = Signal(str)
    go_to_import = Signal()        # empty-state CTA → shell switches to Import
    pins_changed = Signal()        # Pin/Deprioritize toggled from a priority/member row
    dirty = Signal()               # active goal set / custom goals changed → shell refresh

    # (key, title, default_expanded)
    SECTIONS = [
        ("goals",        "Goals",                       True),
        ("priority",     "Priority targets",            True),
        ("integrations", "Integration Time and Sessions", True),
        ("checklists",   "Goal checklists",             False),
        ("category",     "Progress by category",        False),
        ("manage",       "Manage goals",                False),
    ]
    SETTING = "overview_sections"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        self.setWidget(self._content)
        self._sec_state = dict(config.get_setting(self.SETTING, {}) or {})
        self._expanded: dict[str, bool] = {}   # manage-goals sub-groups (in-memory)
        self._building = False
        self.reload()

    # ---- section plumbing ----
    def _persist(self, key: str, on: bool):
        self._sec_state[key] = on
        config.save_setting(self.SETTING, self._sec_state)

    def _section(self, key: str, title: str, default: bool) -> CollapsibleSection:
        exp = self._sec_state.get(key, default)
        return CollapsibleSection(
            title, expanded=exp, on_toggle=lambda on, k=key: self._persist(k, on))

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

    def _wire_open(self, table):
        def go(item):
            slug = table.item(item.row(), 0).data(Qt.UserRole)
            if slug:
                self.open_object.emit(slug)
        table.itemDoubleClicked.connect(go)

    @staticmethod
    def _caption(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("caption", True)
        return lbl

    # ---- build ----
    def reload(self):
        self._building = True
        self._clear()
        title = QLabel("<h2>Overview</h2>")
        title.setTextFormat(Qt.RichText)
        self._lay.addWidget(title)

        goals = derived.load_goals()

        # Fresh store: welcome + guided-import CTA (goals still show — motivating),
        # plus Manage goals so a new user can pick a catalog before their first capture.
        if not derived.totals_by_slug():
            self._add_welcome()
            gsec = self._section("goals", "Goals", True)
            self._fill_goals(gsec.body, goals)
            self._lay.addWidget(gsec)
            msec = self._section("manage", "Manage goals", True)
            self._fill_manage(msec.body)
            self._lay.addWidget(msec)
            self._lay.addStretch(1)
            self._building = False
            return

        summary = derived.load_summary()
        by_slug = derived.totals_by_slug()

        for key, label, default in self.SECTIONS:
            sec = self._section(key, label, default)
            if key == "goals":
                self._fill_goals(sec.body, goals)
            elif key == "priority":
                self._fill_priority(sec.body)
            elif key == "integrations":
                self._fill_integrations(sec.body, by_slug)
            elif key == "category":
                self._fill_category(sec.body, summary)
            elif key == "checklists":
                self._fill_checklists(sec.body)
            elif key == "manage":
                self._fill_manage(sec.body)
            self._lay.addWidget(sec)

        self._lay.addStretch(1)
        self._building = False

    # ---- section fillers (each appends into a QVBoxLayout `body`) ----
    def _fill_goals(self, body, goals):
        if not goals:
            body.addWidget(QLabel("<i>No active goals. Pick one under "
                                  "“Manage goals”.</i>"))
            return
        g_tbl = make_table(["Goal", "Captured", "Deep", "Total", "Progress"],
                           stretch_last=True)
        g_tbl.setSortingEnabled(False)
        for g in goals:
            r = g_tbl.rowCount()
            g_tbl.insertRow(r)
            g_tbl.setItem(r, 0, QTableWidgetItem(g.get("name", g.get("id", ""))))
            g_tbl.setItem(r, 1, QTableWidgetItem(str(g.get("captured", 0))))
            g_tbl.setItem(r, 2, QTableWidgetItem(str(g.get("deep", 0))))
            g_tbl.setItem(r, 3, QTableWidgetItem(str(g.get("total", 0))))
            g_tbl.setItem(r, 4, QTableWidgetItem(
                f"{g.get('captured', 0)}/{g.get('total', 0)} "
                f"({g.get('percent', 0)}%)"))
        g_tbl.resizeColumnsToContents()
        fit_table_height(g_tbl)
        body.addWidget(g_tbl)

    def _fill_category(self, body, summary):
        # "Total" column dropped (item 21) — it read as confusing next to the Total
        # *row*; the per-category totals live in the Goal checklists instead.
        cats = summary.get("by_category", {})
        cat_tbl = make_table(["Category", "Captured", "Deep stack",
                              "Captured objects"], stretch_last=True)
        cat_tbl.setSortingEnabled(False)
        for cat, v in sorted(cats.items()):
            r = cat_tbl.rowCount()
            cat_tbl.insertRow(r)
            cat_tbl.setItem(r, 0, QTableWidgetItem(cat.replace("_", " ").title()))
            cat_tbl.setItem(r, 1, QTableWidgetItem(str(v.get("captured", 0))))
            cat_tbl.setItem(r, 2, QTableWidgetItem(str(v.get("deep_stack", 0))))
            cat_tbl.setItem(r, 3, QTableWidgetItem(", ".join(v.get("captured_ids", []))))
        grand = summary.get("grand", {})
        if grand:
            r = cat_tbl.rowCount()
            cat_tbl.insertRow(r)
            cat_tbl.setItem(r, 0, QTableWidgetItem("Total"))
            cat_tbl.setItem(r, 1, QTableWidgetItem(str(grand.get("captured", 0))))
            cat_tbl.setItem(r, 2, QTableWidgetItem(str(grand.get("deep_stack", 0))))
            cat_tbl.setItem(r, 3, QTableWidgetItem(""))
        cat_tbl.resizeColumnsToContents()
        fit_table_height(cat_tbl)
        body.addWidget(cat_tbl)

    def _fill_integrations(self, body, by_slug):
        row = QHBoxLayout()
        row.addStretch(1)
        all_btn = QPushButton("View all sessions…")
        all_btn.clicked.connect(self._open_all_sessions)
        row.addWidget(all_btn)
        body.addLayout(row)

        # Integration time by object (per catalog object, matching the detail pane —
        # a folder-keyed table showed 0-session rows for multi-object / stack-only
        # capture folders while the objects had plenty of data under their slugs).
        body.addWidget(self._caption("Integration time by object"))
        ci = make_table(["Object", "Sessions", "Frames", "Integration", "Filter",
                         "Status"], stretch_last=True)
        ci.setSortingEnabled(False)   # rows are pre-sorted; sorting-on-insert blanks cells
        rows = sorted(
            ((slug, t) for slug, t in by_slug.items() if t.get("session_count", 0)),
            key=lambda kv: kv[1].get("integration_min", 0), reverse=True)
        for slug, t in rows:
            r = ci.rowCount()
            ci.insertRow(r)
            obj = QTableWidgetItem(t.get("id") or slug)
            obj.setData(Qt.UserRole, slug)
            ci.setItem(r, 0, obj)
            ci.setItem(r, 1, NumItem(str(t.get("session_count", 0)), t.get("session_count", 0)))
            ci.setItem(r, 2, NumItem(str(t.get("frames", 0)), t.get("frames", 0)))
            ci.setItem(r, 3, NumItem(t.get("integration_hms", ""), t.get("integration_min", 0)))
            ci.setItem(r, 4, QTableWidgetItem("/".join(t.get("filters", []))))
            ci.setItem(r, 5, QTableWidgetItem(status_label(t.get("status"), True)))
        ci.resizeColumnsToContents()
        fit_table_height(ci, max_rows=10)
        self._wire_open(ci)
        body.addWidget(ci)

        # Last 5 sessions (most recent capture nights across the whole store).
        body.addWidget(self._caption("Last 5 sessions"))
        sessions = sorted(derived.load_sessions(),
                          key=lambda s: s.get("date", ""), reverse=True)[:5]
        ls = make_table(["Date", "Object", "Frames", "Exp (s)", "Filter",
                         "Integration"], stretch_last=True)
        ls.setSortingEnabled(False)
        for s in sessions:
            r = ls.rowCount()
            ls.insertRow(r)
            obj = QTableWidgetItem(s.get("object_dir", ""))
            if s.get("slugs"):
                obj.setData(Qt.UserRole, s["slugs"][0])
            ls.setItem(r, 0, QTableWidgetItem(s.get("date", "")))
            ls.setItem(r, 1, obj)
            ls.setItem(r, 2, NumItem(str(s.get("frames", 0)), s.get("frames", 0)))
            ls.setItem(r, 3, QTableWidgetItem(str(s.get("exposure_s", ""))))
            ls.setItem(r, 4, QTableWidgetItem(s.get("filter", "")))
            ls.setItem(r, 5, QTableWidgetItem(
                f"{s.get('integration_min', 0) / 60:.1f}h"
                if s.get("integration_min") else "—"))
        # wire open on the Object column (col 1)
        ls.itemDoubleClicked.connect(
            lambda item: self.open_object.emit(ls.item(item.row(), 1).data(Qt.UserRole))
            if ls.item(item.row(), 1) and ls.item(item.row(), 1).data(Qt.UserRole) else None)
        ls.resizeColumnsToContents()
        fit_table_height(ls)
        body.addWidget(ls)

    def _fill_priority(self, body):
        cap = QLabel("In development — an automatic prioritizer is coming. For now, "
                     "pin objects from your Library (right-click → Pin as priority).")
        cap.setProperty("caption", True)
        cap.setWordWrap(True)
        body.addWidget(cap)
        rows = self._priority_rows()
        if not rows:
            return
        pt = make_table(["Object", "Type", "Season", "Priority", "Filter",
                         "Target", "Progress"], stretch_last=True)
        pt.setSortingEnabled(False)
        for row in rows:
            r = pt.rowCount()
            pt.insertRow(r)
            obj = QTableWidgetItem(row["label"])
            obj.setData(Qt.UserRole, row.get("slug"))
            pt.setItem(r, 0, obj)
            pt.setItem(r, 1, QTableWidgetItem(row["type"]))
            pt.setItem(r, 2, QTableWidgetItem(row["season"]))
            pt.setItem(r, 3, QTableWidgetItem(row["priority"]))
            pt.setItem(r, 4, QTableWidgetItem(row["filter"]))
            pt.setItem(r, 5, QTableWidgetItem(row["target"]))
            pt.setItem(r, 6, QTableWidgetItem(row["progress"]))
        pt.resizeColumnsToContents()
        fit_table_height(pt, max_rows=12)
        self._wire_open(pt)
        pt.setContextMenuPolicy(Qt.CustomContextMenu)
        pt.customContextMenuRequested.connect(
            lambda pos, t=pt: self._priority_context_menu(t, pos))
        body.addWidget(pt)

    def _fill_checklists(self, body):
        """Per-active-goal membership checklists (green check per captured/deep)."""
        active = list(goals_mod.active_goal_ids())
        if not active:
            body.addWidget(QLabel("<i>No active goals.</i>"))
            return
        totals = derived.totals_by_slug()
        goals_data = {g["id"]: g for g in derived.load_goals()}
        for gid in active:
            g = goals_data.get(gid)
            head = QLabel(f"<b>{goals_mod.goal_name(gid)}</b>")
            head.setTextFormat(Qt.RichText)
            body.addWidget(head)
            if g:
                body.addWidget(QLabel(
                    f"{g['captured']} captured · {g['deep']} deep · {g['total']} total "
                    f"({g['percent']}%)"))
            body.addWidget(self._catalog_table(gid, totals))

    def _fill_manage(self, body):
        """Goal setup: activate/deactivate catalogs + custom-goal CRUD, grouped by
        hemisphere in nested disclosure sections (former Goals page). This is the only
        non-table section, so it's wrapped in a bordered frame to read as a group."""
        frame = QFrame()
        frame.setObjectName("manageGoalsBox")
        frame.setFrameShape(QFrame.StyledPanel)
        inner = QVBoxLayout(frame)
        _manage_intro = QLabel(
            "Catalogs and custom lists you're tracking. Uncaptured members show as a "
            "checklist above; capturing or annotating an object adds it to your Library.")
        _manage_intro.setWordWrap(True)   # wrap, so it doesn't demand a wide viewport
        inner.addWidget(_manage_intro)
        self._checks = {}
        by_group: dict[str, list[dict]] = {}
        for g in goals_mod.list_goals():
            by_group.setdefault(g["hemisphere"], []).append(g)
        for key, label in _GROUPS:
            goals_here = by_group.get(key, [])
            if not goals_here and key != "custom":
                continue
            default = key == "custom" or any(g["active"] for g in goals_here)
            expand = self._expanded.get(key, default)
            section = CollapsibleSection(
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
            inner.addWidget(section)
        body.addWidget(frame)

    # ---- goal-row + membership table (from the former Goals page) ----
    def _goal_row(self, g: dict) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 2, 0, 2)
        col.setSpacing(1)
        top = QHBoxLayout()
        cb = QCheckBox(f"{g['name']}  ({g['total']})")
        cb.setChecked(g["active"])
        cb.toggled.connect(self._on_goal_toggle)
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

    def _catalog_table(self, gid: str, totals: dict):
        members = goals_mod.goal_members(gid)
        try:
            lib = catalog.load_library()
        except Exception:
            lib = {}
        ref = catalog.load_reference()
        pin_state = pins.load()
        tbl = make_table(["Object", "Name", "Captured", "Deep stack"])
        tbl.setSortingEnabled(False)
        green = QBrush(status_color("deep_stack"))
        slugs = sorted(members, key=lambda s: catalog.catalog_sort_key(members[s]))
        for slug in slugs:
            entry = lib.get(slug) or ref.get(slug)
            label = catalog.object_label(catalog.object_identifiers(slug, entry)) or slug
            st = pin_state.get(slug)
            marker = "▲ " if st == pins.PIN else "▼ " if st == pins.DEPRIORITIZE else ""
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
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        fit_table_height(tbl, max_rows=12)      # long catalogs cap + scroll
        self._wire_open(tbl)
        tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        tbl.customContextMenuRequested.connect(
            lambda pos, t=tbl: self._member_context_menu(t, pos))
        return tbl

    @staticmethod
    def _check_item(on: bool, brush: QBrush) -> QTableWidgetItem:
        it = QTableWidgetItem("✓" if on else "")
        it.setTextAlignment(Qt.AlignCenter)
        if on:
            it.setForeground(brush)
        return it

    # ---- context menus ----
    def _priority_context_menu(self, tbl, pos):
        self._pin_menu(tbl, pos)

    def _member_context_menu(self, tbl, pos):
        self._pin_menu(tbl, pos)

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

    # ---- goal setup actions ----
    def _on_goal_toggle(self, _checked: bool):
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

    def _open_all_sessions(self):
        """The full capture-session log (the former Sessions pane) in a dialog; a
        row routes to the object and closes the dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout
        from m110.ui.pages.sessions import SessionsPage
        dlg = QDialog(self)
        dlg.setWindowTitle("All sessions")
        dlg.resize(760, 560)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        sp = SessionsPage()
        sp.open_object.connect(lambda slug: (dlg.accept(), self.open_object.emit(slug)))
        lay.addWidget(sp)
        dlg.exec()

    # ---- welcome (empty store) ----
    def _add_welcome(self):
        card = QLabel(
            "<b>Welcome to M110.</b><br>"
            "Your library is empty. Import images from your smart telescope to get "
            "started — M110 will organize them, track your catalog progress, and "
            "prepare them for processing.")
        card.setTextFormat(Qt.RichText)
        card.setWordWrap(True)
        self._lay.addWidget(card)
        row = QHBoxLayout()
        btn = QPushButton("Import images…")
        btn.setDefault(True)
        btn.clicked.connect(self.go_to_import.emit)
        row.addWidget(btn)
        row.addStretch(1)
        self._lay.addLayout(row)
        tip = QLabel("Tip: choose a goal under “Manage goals” below, or add an object "
                     "manually from the Library menu.")
        tip.setProperty("caption", True)
        tip.setWordWrap(True)
        self._lay.addWidget(tip)

    # ---- priority rows (manual pins only — the auto-prioritizer isn't shipped, so
    # the legacy priorities.toml source is intentionally not read here) ----
    def _priority_rows(self) -> list[dict]:
        cat = catalog.load_library()
        by_slug = derived.totals_by_slug()
        rows = []
        for slug in sorted(pins.pinned_slugs()):
            e = cat.get(slug)
            if not e:
                continue
            t = by_slug.get(slug)
            prog = t.get("integration_hms", "") if t else "not started"
            rows.append({
                "label": f"▲ {e.get('id') or slug}", "slug": slug,
                "type": (e.get("type") or "").replace("_", " "),
                "season": e.get("season") or "", "priority": "pinned",
                "filter": e.get("filter") or "", "target": "",
                "progress": prog or "not started",
            })
        return rows
