"""Summary page — the landing dashboard: category progress, processing-queue
snapshot, current integrations, and priority targets. Object rows double-click
through to the Catalog detail."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidgetItem,
    QHeaderView, QPushButton,
)

from m110 import catalog, derived, pins
from m110.ui.widgets import NumItem, status_label, make_table

import re as _re


def _priority_slug(p: dict) -> str | None:
    """Best-effort Library slug for a hand-edited priority entry (for mute + click)."""
    prog = p.get("progress")
    if prog and prog.get("source") in ("slug", "folder"):
        return prog.get("key")
    base = _re.sub(r"\s*\(.*?\)\s*", "", p.get("id", "")).strip()
    return base.lower().replace(" ", "-").replace("/", "-") or None

_URGENT = ("out_of_date", "not_processed")


class SummaryPage(QScrollArea):
    open_object = Signal(str)
    go_to_import = Signal()       # empty-state CTA → shell switches to the Import page

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        self.setWidget(self._content)
        self.reload()

    def _clear(self):
        while self._lay.count():
            it = self._lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            elif it.layout() is not None:
                lay = it.layout()
                while lay.count():
                    c = lay.takeAt(0).widget()
                    if c is not None:
                        c.deleteLater()
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

    def reload(self):
        self._clear()
        summary = derived.load_summary()
        proc = derived.load_processing()
        by_folder = derived.load_totals().get("by_folder", {})
        priorities = derived.load_priorities()

        title = QLabel("<h2>Summary</h2>")
        title.setTextFormat(Qt.RichText)
        self._lay.addWidget(title)

        goals = derived.load_goals()

        # Fresh store (nothing captured yet): a welcome + guided first-import CTA
        # instead of a page of empty tables (#onboarding). Goals still show — the
        # north-star progress is motivating even at 0%.
        if not derived.totals_by_slug():
            self._add_welcome()
            self._add_goals_section(goals)
            self._lay.addStretch(1)
            return

        self._add_goals_section(goals)

        # ── Progress by category ───────────────────────────────────────────
        self._lay.addWidget(self._heading("Progress by category"))
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
        self._lay.addWidget(cat_tbl)

        # ── Processing-queue snapshot ──────────────────────────────────────
        counts = proc.get("counts", {})
        self._lay.addWidget(self._heading("Processing queue"))
        self._lay.addWidget(QLabel(
            f"{counts.get('out_of_date', 0)} out of date · "
            f"{counts.get('not_processed', 0)} not processed · "
            f"{counts.get('up_to_date', 0)} up to date"))
        urgent = [f for f in proc.get("queue", []) if f.get("status") in _URGENT][:8]
        if urgent:
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
            self._lay.addWidget(ut)
        else:
            self._lay.addWidget(QLabel("<i>All caught up.</i>"))

        # ── Current integrations (by capture target) ───────────────────────
        self._lay.addWidget(self._heading("Current integrations"))
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
        self._lay.addWidget(ci)

        # ── Priority targets (hand-edited priorities + manual pins; #3) ─────
        self._lay.addWidget(self._heading("Priority targets"))
        rows = self._priority_rows(priorities)
        if not rows:
            hint = QLabel("No priority targets yet. Pin an object from your Library "
                          "(right-click → Pin as priority) to build your list.")
            hint.setProperty("caption", True)
            hint.setWordWrap(True)
            self._lay.addWidget(hint)
            self._lay.addStretch(1)
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
        self._lay.addWidget(pt)

        self._lay.addStretch(1)

    def _add_welcome(self):
        """First-run welcome card + guided-import CTA (shown until first capture)."""
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

        tip = QLabel("Tip: choose a goal on the Goals page, or add an object "
                     "manually from the Library menu.")
        tip.setProperty("caption", True)
        tip.setWordWrap(True)
        self._lay.addWidget(tip)

    def _add_goals_section(self, goals):
        # ── Goals (active catalogs) ─────────────────────────────────────────
        if not goals:
            return
        self._lay.addWidget(self._heading("Goals"))
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
        self._lay.addWidget(g_tbl)

    def _priority_rows(self, priorities) -> list[dict]:
        """Merge hand-edited priorities with manually pinned Library objects, drop
        muted ones, into uniform display rows (#3)."""
        muted = pins.muted_slugs()
        pinned = pins.pinned_slugs()
        cat = catalog.load_library()
        by_slug = derived.totals_by_slug()
        rows, shown = [], set()

        for p in priorities:
            slug = _priority_slug(p)
            if slug and slug in muted:
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
