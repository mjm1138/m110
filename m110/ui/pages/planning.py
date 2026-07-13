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

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QComboBox,
    QTableWidgetItem, QMenu, QFrame, QPushButton, QDoubleSpinBox, QApplication,
)

from m110 import catalog, pins, prioritize
from m110 import planning_config as pc
from m110.ui.widgets import make_table, fit_table_height, CollapsibleSection
from m110.ui.site_profile_editor import SiteProfileEditor

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


class PlanningPage(QScrollArea):
    open_object = Signal(str)
    pins_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._loading = False
        self._worker = None
        self._strategy = prioritize.load_strategy()
        self._weights = prioritize.load_weights()

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
        wrow = QHBoxLayout()
        for label, key in _FACTOR_LABELS:
            wrow.addWidget(QLabel(label))
            sp = QDoubleSpinBox()
            sp.setRange(0.0, 3.0)
            sp.setSingleStep(0.1)
            sp.setDecimals(1)
            sp.setValue(getattr(self._weights, key))
            sp.valueChanged.connect(self._on_weight_changed)
            self._weight_spins[key] = sp
            wrow.addWidget(sp)
        wrow.addStretch(1)
        tune.body.addLayout(wrow)
        body.addWidget(tune)

        self._ptable_holder = QVBoxLayout()
        body.addLayout(self._ptable_holder)

    # ---- refresh ----
    def reload(self):
        # Cheap: refresh the selector + re-rank the cached contexts. The heavy astropy
        # recompute is NOT triggered here — the shell calls `ensure_ranking()` when the
        # user navigates to Planning (an explicit, app-only action), so a background
        # refresh (or an offscreen test that builds the page) never spawns the worker.
        self._reload_selector()
        self._render_ranking()

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
        tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        tbl.customContextMenuRequested.connect(
            lambda pos, t=tbl: self._pin_menu(t, pos))
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
        self._status.setText("ranking up to date")
        self._render_ranking()

    def _stop_worker(self):
        w = self._worker
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
        prioritize.save_weights(self._weights)
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
