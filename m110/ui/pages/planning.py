"""Planning page — the home of session planning + location profiles.

A **location selector** picks the active site profile the planner/prioritizer reads;
a **Priority targets** table shows the deterministic prioritizer's ranking with a
**strategy** toggle + factor-weight controls (the live tuning surface); and a
**Manage site profiles** collapsible wraps the :class:`SiteProfileEditor`.

The scorer's slow part (astropy observability over every goal member) is computed
**once/day on a background thread** and cached (`prioritize.write_contexts`); the
strategy/weight/pin controls **re-rank the cache instantly** without recomputing.

Persistent widgets (selector + controls + editor built once, table repopulated) so a
focus refresh doesn't rebuild the page or clobber in-progress profile edits.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QThread, QDate, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QComboBox,
    QTableWidget, QTableWidgetItem, QMenu, QFrame, QPushButton, QDoubleSpinBox,
    QApplication, QDateEdit, QInputDialog, QMessageBox, QSpinBox, QCheckBox,
)

from m110 import catalog, pins, prioritize
from m110 import planning_config as pc
from m110.ui.widgets import (
    make_table, fit_table_height, CollapsibleSection, connect_context_menu,
)
from m110.ui.site_profile_editor import SiteProfileEditor
from m110.ui.night_timeline import NightTimeline

_STRATEGY_LABELS = [("Capture many (breadth)", prioritize.STRATEGY_CAPTURE),
                    ("Go deep (depth)", prioritize.STRATEGY_DEEP)]
_FACTOR_LABELS = [("Goal", "goal"), ("Urgency", "urgency"),
                  ("Completion", "completion"), ("Tonight", "tonight")]


class _PrioritizerWorker(QThread):
    """Recompute + cache the (slow) prioritizer contexts off the UI thread."""
    done = Signal()

    def run(self):
        prioritize.refresh_prioritized()      # never raises; reads the active site
        self.done.emit()


class _PlannerWorker(QThread):
    """Build a night's plan (per-target astropy tracks) off the UI thread."""
    done = Signal(object)                     # plan dict, or None on failure

    def __init__(self, site, day, slugs, scores, filters, parent=None):
        super().__init__(parent)
        self._args = (site, day, slugs, scores, filters)

    def run(self):
        site, day, slugs, scores, filters = self._args
        try:
            from m110 import planning
            plan = planning.plan_night(site, day, slugs, scores=scores, filters=filters)
        except Exception:
            # Log the traceback so an engine failure (most often astropy not loading)
            # is diagnosable — the UI reports it truthfully rather than as "no darkness".
            import logging
            logging.getLogger("m110").warning(
                "plan_night failed — session plan unavailable", exc_info=True)
            plan = None
        self.done.emit(plan)


class PlanningPage(QScrollArea):
    open_object = Signal(str)
    pins_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._loading = False
        self._worker = None
        self._planner = None
        self._entries = []            # ordered night_track entries of the current plan
        self._included = set()        # slugs currently checked into the plan
        self._slots = []              # the sequenced schedule (Phase 4)
        self._excluded = set()        # slugs the user removed from the sequence
        self._plan_meta = {}          # {window, moon, ceiling, day} of the current plan
        self._strategy = prioritize.load_strategy()
        self._weights = prioritize.load_weights()
        self._visible_only = prioritize.load_visible_tonight()

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setAlignment(Qt.AlignTop)
        self.setWidget(content)

        title = QLabel("<b>Session Planning</b>")
        title.setTextFormat(Qt.RichText)
        lay.addWidget(title)
        cap = QLabel("Pick where you're observing from, then work your ranked "
                     "priority targets. Tune the ranking with the strategy + weights.")
        cap.setProperty("caption", True)
        cap.setWordWrap(True)
        lay.addWidget(cap)

        loc = QHBoxLayout()
        loc.addWidget(QLabel("Location:"))
        self.selector = QComboBox()
        self.selector.currentIndexChanged.connect(self._on_location_changed)
        loc.addWidget(self.selector, 1)
        lay.addLayout(loc)

        self._priority_sec = CollapsibleSection("Priority targets", expanded=True)
        self._build_priority_controls(self._priority_sec.body)
        lay.addWidget(self._priority_sec)

        self._plan_sec = CollapsibleSection("Plan a night", expanded=False)
        self._build_planner(self._plan_sec.body)
        lay.addWidget(self._plan_sec)

        self._guides_sec = CollapsibleSection("Saved field guides", expanded=False)
        self._build_guides(self._guides_sec.body)
        lay.addWidget(self._guides_sec)

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

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_worker)

        self.reload()

    # ---- priority controls (built once) ----
    def _build_priority_controls(self, body):
        row = QHBoxLayout()
        row.addWidget(QLabel("Strategy:"))
        self._strategy_combo = QComboBox()
        for label, val in _STRATEGY_LABELS:
            self._strategy_combo.addItem(label, val)
        i = self._strategy_combo.findData(self._strategy)
        self._strategy_combo.setCurrentIndex(i if i >= 0 else 0)
        self._strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)
        row.addWidget(self._strategy_combo)
        self._visible_chk = QCheckBox("Visible tonight")
        self._visible_chk.setChecked(self._visible_only)
        self._visible_chk.setToolTip(
            "Show only targets that are actually up tonight from this site. Uncheck "
            "to see the full ranking (e.g. to plan a future date).")
        self._visible_chk.toggled.connect(self._on_visible_toggled)
        row.addWidget(self._visible_chk)
        row.addStretch(1)
        self._status = QLabel("")
        self._status.setProperty("caption", True)
        row.addWidget(self._status)
        self._recompute_btn = QPushButton("Recompute")
        self._recompute_btn.setToolTip("Recompute tonight's observability from the "
                                       "active site (runs in the background).")
        self._recompute_btn.clicked.connect(lambda: self._maybe_recompute(force=True))
        row.addWidget(self._recompute_btn)
        body.addLayout(row)

        # Factor-weight tuning (live re-rank; persisted).
        tune = CollapsibleSection("Tuning weights", expanded=False)
        self._weight_spins = {}
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Factors:"))
        for label, key in _FACTOR_LABELS:
            frow.addWidget(QLabel(label))
            sp = QDoubleSpinBox()
            sp.setRange(0.0, 3.0)
            sp.setSingleStep(0.1)
            sp.setDecimals(1)
            sp.setValue(getattr(self._weights, key))
            sp.valueChanged.connect(self._on_weight_changed)
            self._weight_spins[key] = sp
            frow.addWidget(sp)
        frow.addStretch(1)
        tune.body.addLayout(frow)

        # Per-type multipliers — boost galaxies/nebulae, damp clusters (1.0 = neutral).
        groups = prioritize.groups_from_type_weights(self._weights.type_weights)
        self._type_spins = {}
        trow = QHBoxLayout()
        trow.addWidget(QLabel("Object types:"))
        for gid, label in prioritize.TYPE_GROUP_LABELS:
            trow.addWidget(QLabel(label))
            sp = QDoubleSpinBox()
            sp.setRange(0.0, 3.0)
            sp.setSingleStep(0.1)
            sp.setDecimals(1)
            sp.setValue(groups.get(gid, 1.0))
            sp.setToolTip(f"Relative weight for {label.lower()} (1.0 = neutral).")
            sp.valueChanged.connect(self._on_weight_changed)
            self._type_spins[gid] = sp
            trow.addWidget(sp)
        trow.addStretch(1)
        tune.body.addLayout(trow)
        body.addWidget(tune)

        self._ptable_holder = QVBoxLayout()
        body.addLayout(self._ptable_holder)

    # ---- plan a night (built once) ----
    def _build_planner(self, body):
        cap = QLabel("Generate an ordered plan for a night — targets that are up, "
                     "when, on an altitude timeline. Reorder as you like, then save a "
                     "field guide.")
        cap.setProperty("caption", True)
        cap.setWordWrap(True)
        body.addWidget(cap)

        row = QHBoxLayout()
        row.addWidget(QLabel("Night:"))
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("ddd d MMM yyyy")
        # A date change makes the current plan stale — clear it rather than let a
        # Jul-13 plan be relabelled (and saved) as Jul 18 (BUGS #36 root cause).
        self._date.dateChanged.connect(self._invalidate_plan)
        row.addWidget(self._date)
        row.addWidget(QLabel("Targets:"))
        self._count = QSpinBox()                       # how many slots (#42, default 4)
        self._count.setRange(1, 20)
        self._count.setValue(4)
        self._count.setToolTip("How many targets to sequence across the night.")
        self._count.valueChanged.connect(self._on_count_changed)
        row.addWidget(self._count)
        gen = QPushButton("Generate plan")
        gen.clicked.connect(self._on_generate)
        row.addWidget(gen)
        self._plan_status = QLabel("")
        self._plan_status.setProperty("caption", True)
        row.addWidget(self._plan_status, 1)
        body.addLayout(row)

        self._plan_summary = QLabel("")
        self._plan_summary.setWordWrap(True)
        body.addWidget(self._plan_summary)

        self._timeline = NightTimeline()
        body.addWidget(self._timeline)

        # Reorder + save controls above the table.
        ctl = QHBoxLayout()
        self._up_btn = QPushButton("↑ Move up")
        self._up_btn.clicked.connect(lambda: self._move_selected(-1))
        self._down_btn = QPushButton("↓ Move down")
        self._down_btn.clicked.connect(lambda: self._move_selected(1))
        ctl.addWidget(self._up_btn)
        ctl.addWidget(self._down_btn)
        ctl.addStretch(1)
        self._save_btn = QPushButton("Save field guide…")
        self._save_btn.clicked.connect(self._save_field_guide)
        ctl.addWidget(self._save_btn)
        body.addLayout(ctl)

        self._plan_table = QTableWidget(0, 6)
        self._plan_table.setHorizontalHeaderLabels(
            ["Include", "Object", "Start", "Duration", "Alt", "Moon"])
        self._plan_table.verticalHeader().setVisible(False)
        self._plan_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._plan_table.setSelectionMode(QTableWidget.SingleSelection)
        self._plan_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._plan_table.itemChanged.connect(self._on_include_toggled)
        self._plan_table.cellDoubleClicked.connect(
            lambda r, _c: self._open_plan_row(r))
        body.addWidget(self._plan_table)
        self._set_plan_controls_enabled(False)

    def _set_plan_controls_enabled(self, on: bool):
        for w in (self._up_btn, self._down_btn, self._save_btn):
            w.setEnabled(on)

    def _invalidate_plan(self, *_):
        """Clear a now-stale plan (date/location changed since it was generated)."""
        if not self._entries and not self._plan_meta:
            return
        self._entries = []
        self._included = set()
        self._slots = []
        self._excluded = set()
        self._plan_meta = {}
        self._plan_status.setText("Night changed — generate the plan again.")
        self._render_plan()

    def _on_generate(self):
        if self._planner is not None:
            return
        contexts = prioritize.load_contexts()
        if not contexts:
            self._plan_status.setText("No ranking yet — open Priority targets to "
                                      "compute it, then try again.")
            return
        ranked = prioritize.rank(contexts, self._weights, self._strategy, pins.load())
        cand = [r["slug"] for r in ranked][:30]        # bound the astropy work
        scores = {r["slug"]: r["score"] for r in ranked}
        filters = {r["slug"]: prioritize.filter_for_type(r.get("type", ""))
                   for r in ranked}
        # Each chosen target runs its full slot (max integration; the sequencer no
        # longer trims a primary to hit its deep-stack target — 2026-07-17).
        self._seq_args = {"scores": scores, "filters": filters}
        self._excluded = set()
        qd = self._date.date()
        day = date(qd.year(), qd.month(), qd.day())
        self._planner_day = day        # the day this plan is FOR (not the widget's later state)
        site = pc.load_active_site()
        self._plan_status.setText("Planning the night…")
        self._planner = _PlannerWorker(site, day, cand, scores, filters, self)
        self._planner.done.connect(self._on_plan_ready)
        self._planner.start()

    def _on_plan_ready(self, plan):
        self._planner = None
        if plan is None:
            # The worker hit an exception (most often astropy failing to load), NOT a
            # genuine "no astronomical darkness" — don't misreport an engine failure as
            # an astronomical fact. The traceback is in the log (Help → Report a problem).
            self._plan_status.setText(
                "Couldn't compute a plan — the astronomy engine isn't available. "
                "See Help → Report a problem for details.")
            self._entries = []
            self._included = set()
            self._slots = []
            self._render_plan()
            return
        if not (plan.get("window") or (None, None))[0]:
            # A real plan came back but the night has no astronomical darkness
            # (high-latitude summer) — this message is the truthful one here.
            self._plan_status.setText("No astronomical darkness for that night here.")
            self._entries = []
            self._included = set()
            self._slots = []
            self._render_plan()
            return
        self._entries = list(plan["entries"])
        self._included = {e["slug"] for e in self._entries}
        # `day` rides with the plan: the field-guide save must stamp the night the
        # astronomy was computed for, never the date widget's current value.
        self._plan_meta = {"window": plan["window"], "moon": plan["moon"],
                           "start_ceiling_deg": plan.get("start_ceiling_deg"),
                           "ceiling_is_hard": plan.get("ceiling_is_hard", True),
                           "day": getattr(self, "_planner_day", None)}
        self._resequence()
        n = len(self._slots)
        self._plan_status.setText(
            f"{n} target(s) scheduled ({len(self._entries)} up)." if n
            else "Nothing up that night.")
        self._render_plan()

    def _on_count_changed(self, _n: int):
        if self._entries and self._plan_meta:          # live re-sequence (no astropy)
            self._excluded = set()
            self._resequence()
            self._render_plan()

    def _resequence(self, forced_order=None):
        """(Re)build the night schedule from the current plan — auto priority order,
        or the user's forced order after a manual move/exclusion."""
        from m110 import planning
        args = getattr(self, "_seq_args", {}) or {}
        excluded = getattr(self, "_excluded", set())
        plan = {**self._plan_meta,
                "entries": [e for e in self._entries if e["slug"] not in excluded]}
        self._slots = planning.sequence_plan(
            plan, count=self._count.value(), forced_order=forced_order, **args)

    def _render_plan(self):
        from datetime import datetime
        from m110 import fieldguide

        def hm(t):
            return t.strftime("%H:%M") if isinstance(t, datetime) else "—"

        window = self._plan_meta.get("window") or (None, None)
        moon = self._plan_meta.get("moon") or {}
        dusk, dawn = window
        if dusk and dawn:
            moon_txt = (f" · <b>Moon:</b> {fieldguide.moon_headline(moon)}"
                        if moon.get("illum") is not None else "")
            self._plan_summary.setText(
                f"<b>Astro dark:</b> {hm(dusk)}–{hm(dawn)}{moon_txt}")
        else:
            self._plan_summary.setText("")

        try:
            lib = catalog.load_library()
        except Exception:
            lib = {}

        def obj_name(slug):
            entry = lib.get(slug) or catalog.load_reference().get(slug) or {}
            return catalog.object_label(catalog.object_identifiers(slug, entry)) or slug

        def moon_item(row):
            it = QTableWidgetItem(fieldguide.moon_cell(row))
            it.setToolTip("Separation from the moon at this slot's start, with its "
                          "impact (illumination × proximity; narrowband LP is "
                          "largely immune). \"—\" = moon below the horizon then — "
                          "no impact.")
            return it

        self._plan_table.blockSignals(True)
        if self._slots:
            # The sequenced schedule (#40–41): one row per slot, contiguous starts.
            self._plan_table.setRowCount(len(self._slots))
            for r, s in enumerate(self._slots):
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                             | Qt.ItemIsSelectable)
                chk.setCheckState(Qt.Checked)
                chk.setData(Qt.UserRole, s["slug"])
                self._plan_table.setItem(r, 0, chk)
                self._plan_table.setItem(r, 1, QTableWidgetItem(obj_name(s["slug"])))
                start_item = QTableWidgetItem(hm(s["start"]))
                start_item.setToolTip("Slot start (10-minute aligned; under the "
                                      "device's start-altitude ceiling — the capture "
                                      "may climb past it once running).")
                self._plan_table.setItem(r, 2, start_item)
                dur_item = QTableWidgetItem(
                    f"{s['duration_min']} min" + (" ⚠" if s.get("marginal") else ""))
                if s.get("marginal"):
                    dur_item.setToolTip("Last-chance slot: cut short by the target's "
                                        "closing window while it descends — expect "
                                        "heavy frame rejection; keep or drop knowingly.")
                self._plan_table.setItem(r, 3, dur_item)
                flag = "^" if s.get("over_ceiling") else ""
                self._plan_table.setItem(r, 4, QTableWidgetItem(
                    f"{s['alt_start']:.0f}°{flag}"))
                self._plan_table.setItem(r, 5, moon_item(s))
        else:
            # No sequence (pre-Phase-4 state / nothing schedulable): per-target rows.
            self._plan_table.setRowCount(len(self._entries))
            for r, e in enumerate(self._entries):
                slug = e["slug"]
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                             | Qt.ItemIsSelectable)
                chk.setCheckState(Qt.Checked if slug in self._included
                                  else Qt.Unchecked)
                chk.setData(Qt.UserRole, slug)
                self._plan_table.setItem(r, 0, chk)
                self._plan_table.setItem(r, 1, QTableWidgetItem(obj_name(slug)))
                st, sa = fieldguide.start_cells(e)   # startable slot, not transit (#37)
                self._plan_table.setItem(r, 2, QTableWidgetItem(st))
                self._plan_table.setItem(r, 3, QTableWidgetItem(
                    f"{hm(e['up_start'])}–{hm(e['up_end'])}"))
                self._plan_table.setItem(r, 4, QTableWidgetItem(sa))
                self._plan_table.setItem(r, 5, moon_item(e))
        self._plan_table.blockSignals(False)
        self._plan_table.resizeColumnsToContents()
        fit_table_height(self._plan_table, max_rows=15)
        self._set_plan_controls_enabled(bool(self._slots or self._entries))
        self._refresh_timeline()

    def _refresh_timeline(self):
        if self._slots:
            keep = {s["slug"] for s in self._slots}
            shown = [e for e in self._entries if e["slug"] in keep]
        else:
            shown = [e for e in self._entries if e["slug"] in self._included]
        self._timeline.set_plan({**self._plan_meta, "entries": shown,
                                 "schedule": self._slots})

    def _on_include_toggled(self, item):
        if item.column() != 0:
            return
        slug = item.data(Qt.UserRole)
        if self._slots:
            if item.checkState() != Qt.Checked:
                # Removing a slot excludes the target and reflows the sequence —
                # a replacement target may take its place (regenerate to reset).
                self._excluded.add(slug)
                self._resequence()
                self._render_plan()
            return
        if item.checkState() == Qt.Checked:
            self._included.add(slug)
        else:
            self._included.discard(slug)
        self._refresh_timeline()

    def _move_selected(self, delta: int):
        r = self._plan_table.currentRow()
        if self._slots:
            if r < 0 or not (0 <= r + delta < len(self._slots)):
                return
            order = [s["slug"] for s in self._slots]
            order[r], order[r + delta] = order[r + delta], order[r]
            # Reflow with the user's order: starts re-chain from dusk, durations
            # and moon impact recompute for the new slot times.
            self._resequence(forced_order=order)
            self._render_plan()
            self._plan_table.selectRow(r + delta)
            return
        if r < 0 or not (0 <= r + delta < len(self._entries)):
            return
        self._entries[r], self._entries[r + delta] = \
            self._entries[r + delta], self._entries[r]
        self._render_plan()
        self._plan_table.selectRow(r + delta)

    def _open_plan_row(self, r: int):
        item = self._plan_table.item(r, 0)
        slug = item.data(Qt.UserRole) if item else None
        if slug:
            self.open_object.emit(slug)

    def _save_field_guide(self):
        if self._slots:
            keep = {s["slug"] for s in self._slots}
            included = [e for e in self._entries if e["slug"] in keep]
        else:
            included = [e for e in self._entries if e["slug"] in self._included]
        if not included:
            QMessageBox.information(self, "Save field guide",
                                   "Include at least one target first.")
            return
        # The plan's own day — NOT the date widget, which the user may have moved
        # since Generate (that desync produced a "Sat 18 Jul" guide with Jul-13
        # astronomy: new-moon 0% / −17°, the BUGS #36 report).
        day = self._plan_meta.get("day")
        if day is None:
            qd = self._date.date()
            day = date(qd.year(), qd.month(), qd.day())
        default = f"{pc.load_active_site().name} — {day.strftime('%a %d %b')}"
        title, ok = QInputDialog.getText(self, "Save field guide", "Title:", text=default)
        if not ok or not title.strip():
            return
        from m110 import fieldguide
        plan = {**self._plan_meta, "entries": included, "schedule": self._slots}
        md = fieldguide.render_markdown(pc.load_active_site(), day, plan, title=title.strip())
        path = fieldguide.save(day, title.strip(), md)
        self._plan_status.setText(f"Saved: {path.name}")
        self._reload_guides()          # refresh the browser (B3)

    # ---- saved field guides (browser) ----
    def _build_guides(self, body):
        self._guides_table = QTableWidget(0, 3)
        self._guides_table.setHorizontalHeaderLabels(["Date", "Title", ""])
        self._guides_table.verticalHeader().setVisible(False)
        self._guides_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._guides_table.cellDoubleClicked.connect(
            lambda r, _c: self._view_guide(r))
        from PySide6.QtWidgets import QHeaderView
        self._guides_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        body.addWidget(self._guides_table)
        self._guides = []

    def _reload_guides(self):
        from m110 import fieldguide
        self._guides = fieldguide.list_guides()
        self._guides_table.setRowCount(len(self._guides))
        for r, g in enumerate(self._guides):
            self._guides_table.setItem(r, 0, QTableWidgetItem(g["date"]))
            self._guides_table.setItem(r, 1, QTableWidgetItem(g["title"]))
            cell = QWidget()
            h = QHBoxLayout(cell)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            view = QPushButton("View")
            view.clicked.connect(lambda _=False, i=r: self._view_guide(i))
            reveal = QPushButton("Reveal")
            reveal.clicked.connect(lambda _=False, i=r: self._reveal_guide(i))
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda _=False, i=r: self._delete_guide(i))
            for b in (view, reveal, delete):
                h.addWidget(b)
            self._guides_table.setCellWidget(r, 2, cell)
        self._guides_table.resizeColumnsToContents()
        from PySide6.QtWidgets import QHeaderView
        self._guides_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        fit_table_height(self._guides_table, max_rows=10)

    def _view_guide(self, r: int):
        if 0 <= r < len(self._guides):
            from m110.ui.field_guide_dialog import FieldGuideDialog
            FieldGuideDialog(self._guides[r]["path"], self).exec()

    def _reveal_guide(self, r: int):
        if 0 <= r < len(self._guides):
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._guides[r]["path"])))

    def _delete_guide(self, r: int):
        if not (0 <= r < len(self._guides)):
            return
        g = self._guides[r]
        if QMessageBox.question(self, "Delete field guide",
                                f"Delete “{g['title']}”?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            g["path"].unlink()
        except OSError:
            pass
        self._reload_guides()

    # ---- refresh ----
    def reload(self):
        # Cheap: refresh the selector + re-rank the cached contexts. The heavy astropy
        # recompute is NOT triggered here — the shell calls `ensure_ranking()` when the
        # user navigates to Planning (an explicit, app-only action), so a background
        # refresh (or an offscreen test that builds the page) never spawns the worker.
        self._reload_selector()
        self._render_ranking()
        self._reload_guides()

    def ensure_ranking(self):
        """Compute tonight's ranking if the cache is stale (called by the shell when
        the user opens the Planning pane). Safe to call repeatedly — gated by
        `is_stale` + a single in-flight worker."""
        self._maybe_recompute()

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
        stem = self.selector.currentData()
        if stem and not (self.editor.is_dirty() and stem == self.editor.current_stem()):
            self.editor.load(stem)

    # ---- ranking (instant re-rank of the cached contexts) ----
    def _render_ranking(self):
        while self._ptable_holder.count():
            it = self._ptable_holder.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        contexts = prioritize.load_contexts()
        if not contexts:
            hint = QLabel("No ranking yet — computing tonight's observability from "
                          "your site… (this runs in the background).")
            hint.setProperty("caption", True)
            hint.setWordWrap(True)
            self._ptable_holder.addWidget(hint)
            return
        rows = prioritize.rank(contexts, self._weights, self._strategy, pins.load())
        total = len(rows)
        if self._visible_only:
            rows = prioritize.filter_visible_tonight(rows)
        hidden = total - len(rows)
        if self._visible_only and hidden:
            cap = QLabel(f"{hidden} more target(s) not up tonight — uncheck "
                         "“Visible tonight” to see the full ranking.")
            cap.setProperty("caption", True)
            cap.setWordWrap(True)
            self._ptable_holder.addWidget(cap)
        try:
            lib = catalog.load_library()
        except Exception:
            lib = {}
        tbl = make_table(["#", "Object", "Type", "Integ", "Score", "Season", "Closes"],
                         stretch_last=True)
        tbl.setSortingEnabled(False)
        pin_state = pins.load()
        for row in rows[:40]:
            r = tbl.rowCount()
            tbl.insertRow(r)
            slug = row["slug"]
            e = lib.get(slug) or {}
            st = pin_state.get(slug)
            marker = "▲ " if st == pins.PIN else ""
            label = marker + (e.get("id") or slug)
            n2c = row.get("nights_to_close")
            closes = f"{n2c}d" if isinstance(n2c, int) and n2c < 60 else ""
            integ = row["integration_min"]
            cells = [str(row["rank"]), label, (row.get("type") or "").replace("_", " "),
                     (f"{integ/60:.1f}h" if integ >= 60 else f"{integ:.0f}m") if integ else "—",
                     f"{row['score']:.2f}", row.get("season") or "", closes]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 1:
                    item.setData(Qt.UserRole, slug)
                tbl.setItem(r, c, item)
        tbl.resizeColumnsToContents()
        fit_table_height(tbl, max_rows=15)
        tbl.itemDoubleClicked.connect(lambda item: self._open_row(tbl, item.row()))
        connect_context_menu(tbl, lambda pos, t=tbl: self._pin_menu(t, pos))
        self._ptable_holder.addWidget(tbl)

    def _maybe_recompute(self, force: bool = False):
        if self._worker is not None:
            return
        if not force and not prioritize.is_stale():
            self._status.setText("ranking up to date")
            return
        self._status.setText("computing observability…")
        self._recompute_btn.setEnabled(False)
        self._worker = _PrioritizerWorker(self)
        self._worker.done.connect(self._on_worker_done)
        self._worker.start()

    def _on_worker_done(self):
        self._worker = None
        self._recompute_btn.setEnabled(True)
        contexts = prioritize.load_contexts()
        if contexts and all(c.obs is None for c in contexts):
            # Not one target got an observability result — the astronomy engine is
            # unavailable. Say so plainly; "up to date" would read as everything's fine.
            self._status.setText("ranking degraded — astronomy engine unavailable")
        else:
            self._status.setText("ranking up to date")
        self._render_ranking()

    def _stop_worker(self):
        for w in (self._worker, self._planner):
            if w is not None and w.isRunning():
                w.wait()

    # ---- routing / context menu ----
    def _open_row(self, tbl, row: int):
        item = tbl.item(row, 1)
        slug = item.data(Qt.UserRole) if item else None
        if slug:
            self.open_object.emit(slug)

    def _pin_menu(self, tbl, pos):
        item = tbl.itemAt(pos)
        if item is None:
            return
        slug = tbl.item(item.row(), 1).data(Qt.UserRole)
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
        self._render_ranking()          # instant re-rank
        self.pins_changed.emit()

    # ---- tuning controls (persist + instant re-rank) ----
    def _on_strategy_changed(self, _idx: int):
        self._strategy = self._strategy_combo.currentData()
        prioritize.save_strategy(self._strategy)
        self._render_ranking()

    def _on_weight_changed(self, *_):
        for key, sp in self._weight_spins.items():
            setattr(self._weights, key, sp.value())
        self._weights.type_weights = prioritize.type_weights_from_groups(
            {gid: sp.value() for gid, sp in self._type_spins.items()})
        prioritize.save_weights(self._weights)
        self._render_ranking()

    def _on_visible_toggled(self, on: bool):
        self._visible_only = on
        prioritize.save_visible_tonight(on)
        self._render_ranking()

    # ---- selector / editor wiring ----
    def _on_location_changed(self, _idx: int):
        if self._loading:
            return
        stem = self.selector.currentData()
        if not stem:
            return
        pc.set_active_profile(stem)
        self.editor.load(stem)
        self._invalidate_plan()               # a plan is site-specific
        self._maybe_recompute(force=True)     # a new site → observability changes

    def _on_profile_saved(self, stem: str):
        self._reload_selector_keeping(stem)
        self._maybe_recompute(force=True)     # coords/horizon/glow may have changed

    def _on_profile_created(self, stem: str):
        pc.set_active_profile(stem)
        self._reload_selector_keeping(stem)

    def _on_profile_deleted(self, _stem: str):
        self._reload_selector()

    def _reload_selector_keeping(self, stem: str):
        pc.set_active_profile(stem)
        self._reload_selector()
