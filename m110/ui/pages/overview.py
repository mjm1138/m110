"""Overview page — the landing dashboard, merging the former Summary and Goals
pages into one pane of **collapsible sections** (the macOS disclosure pattern via
`widgets.CollapsibleSection`). Each section's open/closed state persists across
launches (settings key `overview_sections`), so each user keeps the layout they
want. The hero is the **catalog board** (UI 1.0 Phase 8 · C): one active goal
drawn as a wall of cells — every member, filled in as it's captured — with a
picker when more than one goal is active (`overview_board_goal`). Goal progress
follows as bars; goal *setup* (activate catalogs, custom goals) is demoted to a
collapsed "Manage goals" section.

Empty store → a welcome + guided-import CTA, then the (empty) board and goals —
the north star is motivating even at 0%."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidgetItem,
    QHeaderView, QPushButton, QMenu, QCheckBox, QInputDialog, QMessageBox, QFrame,
    QComboBox, QGridLayout,
)

from m110 import (catalog, config, derived, devices, integration_goals, objects, pins,
                  refresh, goals as goals_mod)
from m110.ui.catalog_board import (
    PROGRESS_ROLE, STATUS_KEY_ROLE, STATUS_OF, CatalogBoard, GoalBar, StatusBarDelegate,
)
from m110.ui.widgets import (
    clear_layout, make_numeric,
    NumItem, status_label, make_table, CollapsibleSection, fit_table_height,
    connect_context_menu, defer, serif_label, ThumbnailLoader, STATUS_TOOLTIP,
)
from m110.ui.theme import status_color
from m110.ui.theme.fonts import tabular
from m110.ui.theme.tokens import SPACE

BOARD_GOAL_KEY = "overview_board_goal"     # which active goal the board shows


def _num(value, text=None) -> NumItem:
    """A right-aligned, tabular, numerically-sorting cell."""
    return make_numeric(NumItem(str(value) if text is None else text, value))


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
    goals_changed = Signal()       # a goal's telescope changed; derived already rebuilt

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
        # Outlives each rebuild, so the board's thumbnails stay cached across syncs.
        self._thumb_loader = ThumbnailLoader(self)
        self.board: CatalogBoard | None = None
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
        # Hide, not just deleteLater: a modal opened right after a rebuild would
        # otherwise paint the old tables over the new ones (`clear_layout`).
        clear_layout(self._lay)

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
        self.__dict__.pop("_models_cache", None)     # telescopes may have changed
        self._clear()
        # The place's name is the header bar's title (one page-header rule).

        goals = derived.load_goals()
        self.board = None

        # Fresh store: welcome + guided-import CTA (the board and goals still show —
        # motivating), plus Manage goals so a new user can pick a catalog before
        # their first capture.
        if not derived.totals_by_slug():
            self._add_welcome()
            self._add_board_section({})
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

        self._add_board_section(by_slug)
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

    # ---- the catalog board (the hero) ----
    def board_goal(self) -> str | None:
        """The active goal the board shows: the saved choice while it's still
        active, else the first active goal."""
        active = list(goals_mod.active_goal_ids())
        if not active:
            return None
        saved = config.get_setting(BOARD_GOAL_KEY, None)
        return saved if saved in active else active[0]

    def _add_board_section(self, by_slug: dict):
        gid = self.board_goal()
        if gid is None:
            return
        cells = goals_mod.board(gid, by_slug)
        if not cells:
            return
        sec = self._section("board", goals_mod.goal_name(gid) + self._scope_suffix(gid),
                            True)
        self._fill_board(sec.body, gid, cells)
        self._lay.addWidget(sec)

    def _fill_board(self, body, gid: str, cells: list[dict]):
        n = goals_mod.board_counts(cells)
        head = QHBoxLayout()
        head.setSpacing(SPACE["sm"])
        count = serif_label(f"{n['captured']} / {n['total']}", "heading")
        count.setObjectName("boardCount")
        head.addWidget(count, 0, Qt.AlignBaseline)
        pct = round(100 * n["captured"] / n["total"]) if n["total"] else 0
        sub = QLabel(f"captured · {n['deep']} deep · {pct}%")
        sub.setProperty("muted", True)
        sub.setObjectName("boardSummary")
        head.addWidget(sub, 0, Qt.AlignBaseline)
        head.addStretch(1)
        head.addWidget(self._board_legend())
        active = list(goals_mod.active_goal_ids())
        if len(active) > 1:
            picker = QComboBox()
            picker.setObjectName("boardGoalPicker")
            picker.setAccessibleName("Goal shown on the board")
            picker.setToolTip("Which goal the board shows")
            for a in active:
                picker.addItem(goals_mod.goal_name(a), a)
            picker.setCurrentIndex(max(0, picker.findData(gid)))
            picker.currentIndexChanged.connect(
                lambda _i, box=picker: self._on_board_goal(box))
            head.addWidget(picker)
        body.addLayout(head)

        ref = catalog.load_reference()
        thumbs = {}
        for c in cells:
            if c["state"] != "missing":
                hp = objects.hero_path(c["slug"])
                if hp:
                    thumbs[c["slug"]] = hp
        names = {c["slug"]: (ref.get(c["slug"]) or {}).get("name") or "" for c in cells}
        self.board = CatalogBoard(loader=self._thumb_loader)
        self.board.set_cells(cells, thumbs, names)
        self.board.object_activated.connect(self.open_object.emit)
        body.addWidget(self.board)

    @staticmethod
    def _board_legend() -> QLabel:
        dots = []
        for state, word in (("deep", "Deep"), ("progress", "In progress"),
                            ("initial", "Initial")):
            c = status_color(STATUS_OF[state])
            dots.append(f"<span style='color:{c.name()}'>●</span>&nbsp;{word}")
        lbl = QLabel("&nbsp;&nbsp; ".join(dots))
        lbl.setTextFormat(Qt.RichText)
        lbl.setProperty("caption", True)
        lbl.setToolTip("A cell's foot fills toward its integration goal; "
                       "an empty slot isn't captured yet")
        return lbl

    def _on_board_goal(self, box: QComboBox):
        if self._building:
            return
        config.save_setting(BOARD_GOAL_KEY, box.currentData())
        # The rebuild tears down the combo whose signal is still running.
        defer(self, self.reload)

    # ---- section fillers (each appends into a QVBoxLayout `body`) ----
    def _fill_goals(self, body, goals):
        """Each active goal as a row: name · a two-segment bar (deep, then
        captured) · "11 / 110" · "1 deep" — progress you can see at a glance,
        where the old table read "11/110 (10.0%)"."""
        if not goals:
            body.addWidget(QLabel("<i>No active goals. Pick one under "
                                  "“Manage goals”.</i>"))
            return
        holder = QWidget()
        holder.setObjectName("goalBars")
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(SPACE["md"])
        grid.setVerticalSpacing(SPACE["sm"])
        grid.setColumnStretch(1, 1)
        for r, g in enumerate(goals):
            gid = g.get("id", "")
            name = QLabel(g.get("name", gid) + self._scope_suffix(gid))
            grid.addWidget(name, r, 0)
            grid.addWidget(GoalBar(g.get("captured", 0), g.get("deep", 0),
                                   g.get("total", 0)), r, 1, Qt.AlignVCenter)
            frac = QLabel(f"{g.get('captured', 0)} / {g.get('total', 0)}")
            frac.setFont(tabular(frac.font()))
            frac.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(frac, r, 2)
            deep = QLabel(f"{g.get('deep', 0)} deep")
            deep.setProperty("muted", True)
            deep.setFont(tabular(deep.font()))
            deep.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(deep, r, 3)
        body.addWidget(holder)

    def _fill_category(self, body, summary):
        # "Total" column dropped (item 21) — it read as confusing next to the Total
        # *row*; the per-category totals live in the Goal checklists instead.
        cats = summary.get("by_category", {})
        cat_tbl = make_table(["Category", "Captured", "Deep",
                              "Captured objects"], stretch_last=True)
        cat_tbl.setSortingEnabled(False)
        for cat, v in sorted(cats.items()):
            r = cat_tbl.rowCount()
            cat_tbl.insertRow(r)
            cat_tbl.setItem(r, 0, QTableWidgetItem(cat.replace("_", " ").title()))
            cat_tbl.setItem(r, 1, _num(v.get("captured", 0)))
            cat_tbl.setItem(r, 2, _num(v.get("deep_stack", 0)))
            cat_tbl.setItem(r, 3, QTableWidgetItem(", ".join(v.get("captured_ids", []))))
        grand = summary.get("grand", {})
        if grand:
            r = cat_tbl.rowCount()
            cat_tbl.insertRow(r)
            cat_tbl.setItem(r, 0, QTableWidgetItem("Total"))
            cat_tbl.setItem(r, 1, _num(grand.get("captured", 0)))
            cat_tbl.setItem(r, 2, _num(grand.get("deep_stack", 0)))
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
            ci.setItem(r, 1, _num(t.get("session_count", 0)))
            ci.setItem(r, 2, _num(t.get("frames", 0)))
            ci.setItem(r, 3, _num(t.get("integration_min", 0), t.get("integration_hms", "")))
            ci.setItem(r, 4, QTableWidgetItem("/".join(t.get("filters", []))))
            st = QTableWidgetItem(status_label(t.get("status"), True, t.get("progress")))
            st.setForeground(status_color(t.get("status")))
            st.setToolTip(STATUS_TOOLTIP.get(t.get("status"), ""))
            st.setData(STATUS_KEY_ROLE, t.get("status"))
            st.setData(PROGRESS_ROLE, 1.0 if t.get("status") == "deep_stack"
                       else float(t.get("progress") or 0.0))
            ci.setItem(r, 5, st)
        # The status as a mini bar toward the goal, then its word.
        ci.setItemDelegateForColumn(5, StatusBarDelegate(ci))
        ci.resizeColumnsToContents()
        fit_table_height(ci, max_rows=10)
        self._wire_open(ci)
        body.addWidget(ci)

        # Last 5 sessions (most recent capture nights across the whole store).
        body.addWidget(self._caption("Last 5 sessions"))
        sessions = sorted(derived.load_sessions(),
                          key=lambda s: s.get("date", ""), reverse=True)[:5]
        ls = make_table(["Date", "Object", "Frames", "Exp (s)", "Filter",
                         "Integration"])
        ls.setSortingEnabled(False)
        for s in sessions:
            r = ls.rowCount()
            ls.insertRow(r)
            obj = QTableWidgetItem(s.get("object_dir", ""))
            if s.get("slugs"):
                obj.setData(Qt.UserRole, s["slugs"][0])
            ls.setItem(r, 0, QTableWidgetItem(s.get("date", "")))
            ls.setItem(r, 1, obj)
            ls.setItem(r, 2, _num(s.get("frames", 0)))
            ls.setItem(r, 3, make_numeric(QTableWidgetItem(str(s.get("exposure_s", "")))))
            ls.setItem(r, 4, QTableWidgetItem(s.get("filter", "")))
            ls.setItem(r, 5, make_numeric(QTableWidgetItem(
                f"{s.get('integration_min', 0) / 60:.1f}h"
                if s.get("integration_min") else "—")))
        # wire open on the Object column (col 1)
        ls.itemDoubleClicked.connect(
            lambda item: self.open_object.emit(ls.item(item.row(), 1).data(Qt.UserRole))
            if ls.item(item.row(), 1) and ls.item(item.row(), 1).data(Qt.UserRole) else None)
        ls.resizeColumnsToContents()
        fit_table_height(ls)
        body.addWidget(ls)

    def _fill_priority(self, body):
        cap = QLabel("Targets you've pinned (Object › Pin as Priority). "
                     "For an automatic ranking of what to shoot next, see the Planning page.")
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
            pt.setItem(r, 5, make_numeric(QTableWidgetItem(row["target"])))
            pt.setItem(r, 6, make_numeric(QTableWidgetItem(row["progress"])))
        pt.resizeColumnsToContents()
        fit_table_height(pt, max_rows=12)
        self._wire_open(pt)
        connect_context_menu(
            pt, lambda pos, t=pt: self._priority_context_menu(t, pos))
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
            head = QLabel(f"<b>{goals_mod.goal_name(gid)}</b>{self._scope_suffix(gid)}")
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

    def _scope_suffix(self, gid: str) -> str:
        """" · <telescope>" for a goal scoped to one telescope; " · any telescope"
        only when some other active goal is scoped, so the contrast means something."""
        scope = goals_mod.goal_scope(gid)
        if scope:
            return f" · {integration_goals.model_label(scope)}"
        if any(goals_mod.goal_scope(o) for o in goals_mod.active_goal_ids()):
            return " · any telescope"
        return ""

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
        if g["active"]:
            # Which telescope's captures count toward this goal (#184).
            scope = QComboBox()
            scope.setToolTip("Count captures from any telescope, or from one only")
            scope.addItem("Any telescope", None)
            for model, label in self._models():
                scope.addItem(label, model)
            idx = scope.findData(g.get("scope"))
            scope.setCurrentIndex(idx if idx >= 0 else 0)
            scope.currentIndexChanged.connect(
                lambda _i, gid=g["id"], box=scope: self._on_scope_changed(gid, box))
            top.addWidget(scope)
            track = QPushButton("Track for another telescope…")
            track.setToolTip("A copy of this goal that counts only one telescope's "
                             "captures — e.g. Messier again on a new scope")
            track.clicked.connect(lambda _=False, gid=g["id"]: self._track_for(gid))
            top.addWidget(track)
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
        # A goal scoped to one telescope ticks only what that telescope captured.
        totals = goals_mod.scoped_totals(totals, goals_mod.goal_scope(gid))
        try:
            lib = catalog.load_library()
        except Exception:
            lib = {}
        ref = catalog.load_reference()
        pin_state = pins.load()
        tbl = make_table(["Object", "Name", "Captured", "Deep"])
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
        connect_context_menu(
            tbl, lambda pos, t=tbl: self._member_context_menu(t, pos))
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
        pin_act = menu.addAction("Unpin" if state == pins.PIN
                                 else "Pin as Priority")
        depri_act = menu.addAction("Un-deprioritize" if state == pins.DEPRIORITIZE
                                   else "Deprioritize")
        chosen = menu.exec(tbl.viewport().mapToGlobal(pos))
        if chosen is pin_act:
            new = None if state == pins.PIN else pins.PIN
        elif chosen is depri_act:
            new = None if state == pins.DEPRIORITIZE else pins.DEPRIORITIZE
        else:
            return
        from m110.ui import undo
        undo.run(undo.SetPinCommand(slug, new, self._after_pin_change))

    def _after_pin_change(self):
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

    def _models(self) -> list[tuple[str, str]]:
        if not hasattr(self, "_models_cache"):
            self._models_cache = integration_goals.known_models()
        return self._models_cache

    def _goal_scope_saved(self):
        """A goal's telescope moved what counts toward it: rebuild derived data (no
        scan) and let the shell reload everything — deferred, because the reload
        tears down the control whose signal is still running."""
        refresh.rederive()
        defer(self, self.goals_changed.emit)

    def _on_scope_changed(self, gid: str, box: QComboBox):
        if self._building:
            return
        goals_mod.set_goal_scope(gid, box.currentData())
        self._goal_scope_saved()

    def _track_for(self, gid: str):
        models = self._models()
        labels = [label for _m, label in models]
        label, ok = QInputDialog.getItem(
            self, "Track for another telescope",
            f"Track “{goals_mod.goal_name(gid)}” again, counting only captures from:",
            labels, 0, False)
        if not ok:
            return
        model = models[labels.index(label)][0]
        goals_mod.copy_for_telescope(gid, model, label)
        self._goal_scope_saved()

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
