"""Overview page — the landing dashboard, merging the former Summary and Goals
pages into one pane of **collapsible sections** (the macOS disclosure pattern via
`widgets.CollapsibleSection`). Each section's open/closed state persists across
launches (settings key `overview_sections`), so each user keeps the layout they
want. Goal *progress* is the hero; goal *setup* (activate catalogs, custom goals)
is demoted to a collapsed "Manage goals" section.

Empty store → a welcome + guided-import CTA (goal progress still shows, since the
north-star is motivating even at 0%)."""
from __future__ import annotations

import re as _re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidgetItem,
    QHeaderView, QPushButton, QMenu, QCheckBox, QInputDialog, QMessageBox, QFrame,
)

from m110 import catalog, config, derived, pins, goals as goals_mod
from m110.ui.widgets import (
    NumItem, status_label, make_table, CollapsibleSection,
)
from m110.ui.theme import status_color

_URGENT = ("out_of_date", "not_processed")

# Manage-goals sub-groups (hemisphere), mirroring the former Goals page.
_GROUPS = [
    ("allsky", "All-sky"),
    ("northern", "Northern hemisphere"),
    ("southern", "Southern hemisphere"),
    ("custom", "Custom goals"),
]


def _priority_slug(p: dict) -> str | None:
    """Best-effort Library slug for a hand-edited priority entry (for pin + click)."""
    prog = p.get("progress")
    if prog and prog.get("source") in ("slug", "folder"):
        return prog.get("key")
    base = _re.sub(r"\s*\(.*?\)\s*", "", p.get("id", "")).strip()
    return base.lower().replace(" ", "-").replace("/", "-") or None


class OverviewPage(QScrollArea):
    open_object = Signal(str)
    go_to_import = Signal()        # empty-state CTA → shell switches to Import
    pins_changed = Signal()        # Pin/Deprioritize toggled from a priority/member row
    dirty = Signal()               # active goal set / custom goals changed → shell refresh

    # (key, title, default_expanded)
    SECTIONS = [
        ("goals",        "Goals",               True),
        ("priority",     "Priority targets",    True),
        ("integrations", "Current integrations", True),
        ("processing",   "Processing queue",    True),
        ("category",     "Progress by category", False),
        ("checklists",   "Goal checklists",     False),
        ("manage",       "Manage goals",        False),
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
        proc = derived.load_processing()
        by_folder = derived.load_totals().get("by_folder", {})
        priorities = derived.load_priorities()

        for key, label, default in self.SECTIONS:
            sec = self._section(key, label, default)
            if key == "goals":
                self._fill_goals(sec.body, goals)
            elif key == "priority":
                self._fill_priority(sec.body, priorities)
            elif key == "integrations":
                self._fill_integrations(sec.body, by_folder)
            elif key == "processing":
                self._fill_processing(sec.body, proc)
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
        g_tbl.setMinimumHeight(min(220, 28 * (len(goals) + 1) + 8))
        body.addWidget(g_tbl)

    def _fill_category(self, body, summary):
        cats = summary.get("by_category", {})
        cat_tbl = make_table(["Category", "Captured", "Deep stack", "Total",
                              "Captured objects"], stretch_last=True)
        cat_tbl.setSortingEnabled(False)
        for cat, v in sorted(cats.items()):
            r = cat_tbl.rowCount()
            cat_tbl.insertRow(r)
            cat_tbl.setItem(r, 0, QTableWidgetItem(cat.replace("_", " ").title()))
            cat_tbl.setItem(r, 1, QTableWidgetItem(str(v.get("captured", 0))))
            cat_tbl.setItem(r, 2, QTableWidgetItem(str(v.get("deep_stack", 0))))
            cat_tbl.setItem(r, 3, QTableWidgetItem(str(v.get("total", 0))))
            cat_tbl.setItem(r, 4, QTableWidgetItem(", ".join(v.get("captured_ids", []))))
        grand = summary.get("grand", {})
        if grand:
            r = cat_tbl.rowCount()
            cat_tbl.insertRow(r)
            cat_tbl.setItem(r, 0, QTableWidgetItem("Total"))
            cat_tbl.setItem(r, 1, QTableWidgetItem(str(grand.get("captured", 0))))
            cat_tbl.setItem(r, 2, QTableWidgetItem(str(grand.get("deep_stack", 0))))
            cat_tbl.setItem(r, 3, QTableWidgetItem(str(grand.get("total", 0))))
            cat_tbl.setItem(r, 4, QTableWidgetItem(""))
        cat_tbl.resizeColumnsToContents()
        cat_tbl.setMinimumHeight(min(360, 28 * (cat_tbl.rowCount() + 1) + 8))
        body.addWidget(cat_tbl)

    def _fill_processing(self, body, proc):
        counts = proc.get("counts", {})
        body.addWidget(QLabel(
            f"{counts.get('out_of_date', 0)} out of date · "
            f"{counts.get('not_processed', 0)} not processed · "
            f"{counts.get('up_to_date', 0)} up to date"))
        urgent = [f for f in proc.get("queue", []) if f.get("status") in _URGENT][:8]
        if not urgent:
            body.addWidget(QLabel("<i>All caught up.</i>"))
            return
        ut = make_table(["Object", "Status", "Integration", "+ since stack",
                         "Last stack"], stretch_last=True)
        ut.setSortingEnabled(False)
        for f in urgent:
            r = ut.rowCount()
            ut.insertRow(r)
            obj = QTableWidgetItem(f.get("folder", ""))
            if f.get("slugs"):
                obj.setData(Qt.UserRole, f["slugs"][0])
            ut.setItem(r, 0, obj)
            ut.setItem(r, 1, QTableWidgetItem(f.get("status", "").replace("_", " ")))
            ut.setItem(r, 2, QTableWidgetItem(f.get("integration_hms", "")))
            ut.setItem(r, 3, QTableWidgetItem(f"+{f.get('new_lights_since_stack', 0)}"))
            ut.setItem(r, 4, QTableWidgetItem(f.get("latest_processed_at") or "—"))
        ut.resizeColumnsToContents()
        ut.setMinimumHeight(min(280, 28 * (len(urgent) + 1) + 8))
        self._wire_open(ut)
        body.addWidget(ut)

    def _fill_integrations(self, body, by_folder):
        row = QHBoxLayout()
        row.addStretch(1)
        all_btn = QPushButton("View all sessions…")
        all_btn.clicked.connect(self._open_all_sessions)
        row.addWidget(all_btn)
        body.addLayout(row)
        ci = make_table(["Object", "Sessions", "Frames", "Integration", "Filter",
                         "Status"], stretch_last=True)
        rows = sorted(by_folder.items(),
                      key=lambda kv: kv[1].get("integration_min", 0), reverse=True)
        for fname, t in rows:
            r = ci.rowCount()
            ci.insertRow(r)
            obj = QTableWidgetItem(fname)
            if t.get("slugs"):
                obj.setData(Qt.UserRole, t["slugs"][0])
            ci.setItem(r, 0, obj)
            ci.setItem(r, 1, NumItem(str(t.get("session_count", 0)), t.get("session_count", 0)))
            ci.setItem(r, 2, NumItem(str(t.get("frames", 0)), t.get("frames", 0)))
            ci.setItem(r, 3, NumItem(t.get("integration_hms", ""), t.get("integration_min", 0)))
            ci.setItem(r, 4, QTableWidgetItem("/".join(t.get("filters", []))))
            ci.setItem(r, 5, QTableWidgetItem(status_label(t.get("status"), True)))
        ci.resizeColumnsToContents()
        ci.setMinimumHeight(min(400, 28 * (len(rows) + 1) + 8))
        self._wire_open(ci)
        body.addWidget(ci)

    def _fill_priority(self, body, priorities):
        rows = self._priority_rows(priorities)
        if not rows:
            hint = QLabel("No priority targets yet. Pin an object from your Library "
                          "(right-click → Pin as priority) to build your list.")
            hint.setProperty("caption", True)
            hint.setWordWrap(True)
            body.addWidget(hint)
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
        pt.setMinimumHeight(min(480, 28 * (len(rows) + 1) + 8))
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
        hemisphere in nested disclosure sections (former Goals page)."""
        body.addWidget(QLabel(
            "Catalogs and custom lists you're tracking. Uncaptured members show as a "
            "checklist above; capturing or annotating an object adds it to your Library."))
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
            body.addWidget(section)

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
        h = min(380, 24 * (len(slugs) + 1) + 10)
        tbl.setMinimumHeight(h)
        tbl.setMaximumHeight(h)
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

    # ---- priority rows (from the former Summary page) ----
    def _priority_rows(self, priorities) -> list[dict]:
        deprioritized = pins.deprioritized_slugs()
        pinned = pins.pinned_slugs()
        cat = catalog.load_library()
        by_slug = derived.totals_by_slug()
        rows, shown = [], set()
        for p in priorities:
            slug = _priority_slug(p)
            if slug and slug in deprioritized:
                continue
            if p.get("progress"):
                prog = (f"{p['progress'].get('integration_hms', '')} "
                        f"({p.get('percent_complete', 0)}%)")
            elif not p.get("track", True):
                prog = "campaign — see strategy"
            else:
                prog = "not started"
            rows.append({
                "label": p.get("id", ""), "slug": slug,
                "type": p.get("type_hint", "") or "", "season": p.get("season", "") or "",
                "priority": str(p.get("priority", "") or ""),
                "filter": p.get("filter", "") or "", "target": str(p.get("target", "") or ""),
                "progress": prog,
            })
            if slug:
                shown.add(slug)
        for slug in sorted(pinned):
            if slug in shown:
                continue
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
