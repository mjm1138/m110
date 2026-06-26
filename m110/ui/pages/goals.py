"""Goals page — select / create / edit the catalogs and custom object lists the
user is pursuing, and show per-goal progress. As of Phase 5d the Library is the
captured/annotated collection; this page is where uncaptured catalog members live
as a checklist (rather than being bulk-seeded into the Library).

Activating/deactivating a goal writes the per-store goals.toml (and a deactivation
prunes uncaptured/un-noted/not-in-another-goal members) — so a toggle emits
`dirty`, which the shell turns into a refresh + reload."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidgetItem,
    QCheckBox, QPushButton, QInputDialog, QMessageBox, QFrame,
)

from m110 import goals as goals_mod, derived, catalog
from m110.ui.widgets import make_table


class GoalsPage(QScrollArea):
    open_object = Signal(str)     # row → Catalog detail
    dirty = Signal()              # active set / custom goals changed → shell refresh

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        self.setWidget(self._content)
        self._building = False
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
        all_goals = goals_mod.list_goals()
        self._checks = {}
        for g in all_goals:
            row = QHBoxLayout()
            cb = QCheckBox(f"{g['name']}  ({g['total']})")
            cb.setChecked(g["active"])
            cb.toggled.connect(self._on_toggle)
            self._checks[g["id"]] = cb
            row.addWidget(cb)
            if g["kind"] == "custom":
                edit = QPushButton("Edit…")
                edit.clicked.connect(lambda _=False, gid=g["id"]: self._edit_custom(gid))
                delete = QPushButton("Delete")
                delete.clicked.connect(lambda _=False, gid=g["id"]: self._delete_custom(gid))
                row.addWidget(edit)
                row.addWidget(delete)
            row.addStretch(1)
            self._lay.addLayout(row)

        new_btn = QPushButton("New custom goal…")
        new_btn.clicked.connect(self._new_custom)
        self._lay.addWidget(new_btn)

    def _build_progress(self):
        goals_data = {g["id"]: g for g in derived.load_goals()}
        totals = derived.totals_by_slug()
        ref = catalog.load_reference()

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        self._lay.addWidget(line)

        active = [gid for gid in goals_mod.active_goal_ids()]
        if not active:
            self._lay.addWidget(QLabel("<i>No active goals.</i>"))
            return

        for gid in active:
            g = goals_data.get(gid)
            name = goals_mod.goal_name(gid)
            self._lay.addWidget(self._heading(name))
            if not g:
                self._lay.addWidget(QLabel("<i>No progress data yet — Refresh.</i>"))
                continue
            self._lay.addWidget(QLabel(
                f"{g['captured']} captured · {g['deep']} deep · {g['total']} total "
                f"({g['percent']}%)"))

            # In-progress captures (captured but below the deep-stack target).
            ip = g.get("in_progress", [])
            if ip:
                self._lay.addWidget(QLabel("<b>In progress</b> (below deep-stack target):"))
                self._lay.addWidget(self._object_table(
                    [(x["slug"], x.get("name", "")) for x in ip]))

            # Remaining (uncaptured) members — the checklist.
            members = goals_mod.goal_members(gid)
            remaining = [(s, (ref.get(s, {}).get("name") or members[s]))
                         for s in members if s not in totals]
            if remaining:
                self._lay.addWidget(QLabel(f"<b>Remaining</b> ({len(remaining)} uncaptured):"))
                self._lay.addWidget(self._object_table(remaining, clickable=False))

    def _object_table(self, rows, clickable: bool = True):
        tbl = make_table(["Object", "Name"], stretch_last=True)
        tbl.setSortingEnabled(False)
        # Resolve each label from the object's real entry (Library, else the bundled
        # reference) so the id shows as its proper designation — not the lowercase
        # slug fabricated as `{"id": slug}`, which rendered "M51 (m51)".
        try:
            lib = catalog.load_library()
        except Exception:
            lib = {}
        ref = catalog.load_reference()
        for slug, name in rows:
            r = tbl.rowCount()
            tbl.insertRow(r)
            entry = lib.get(slug) or ref.get(slug)
            label = catalog.object_label(catalog.object_identifiers(slug, entry))
            it = QTableWidgetItem(label or slug)
            it.setData(Qt.UserRole, slug)
            tbl.setItem(r, 0, it)
            tbl.setItem(r, 1, QTableWidgetItem(str(name or "")))
        tbl.resizeColumnsToContents()
        tbl.setMinimumHeight(min(280, 28 * (tbl.rowCount() + 1) + 8))
        if clickable:
            self._wire_open(tbl)
        return tbl

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
