"""Ask before replacing a Naztronomy preset that differs from M110's proposal (#174).

Prep writes a preset only where none exists. When one is already there and
differs — the user saved their own from Naztronomy, or M110's suggestion moved on
because the frame count crossed a tier — `siril.apply_prep` reports it instead,
and this dialog puts the list to the user once per ingest. Ticked rows are
replaced (the old file is archived under ``presets/archive/``); the rest are kept,
and M110 does not ask about them again until its proposal changes.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidgetItem, QVBoxLayout,
)

from m110 import siril
from m110.ui.widgets import fit_table_height, make_table

_COLUMNS = ["Replace", "Object", "Job", "What changes"]


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def describe_changes(changes) -> str:
    """One line per changed key: ``roundness: 98 → 95``."""
    return "\n".join(f"{k}: {_fmt(old)} → {_fmt(new)}" for k, old, new in changes)


def preset_conflicts(result: dict) -> list:
    """Every `siril.PresetConflict` in a `processing.run_autoprep` result."""
    return [c for r in (result or {}).values() if isinstance(r, dict)
            for c in r.get("preset_conflicts", [])]


class PresetConflictDialog(QDialog):
    """Lists the conflicting presets; `replace_paths()` is what the user ticked."""

    def __init__(self, conflicts, parent=None):
        super().__init__(parent)
        self._conflicts = list(conflicts)
        self.setWindowTitle("Update Siril presets?")
        self.setMinimumWidth(720)

        lay = QVBoxLayout(self)
        n = len(self._conflicts)
        note = QLabel(
            f"{'A Naztronomy preset' if n == 1 else f'{n} Naztronomy presets'} "
            f"already in the Siril working folders "
            f"{'differs' if n == 1 else 'differ'} from what M110 would now suggest "
            "for the frames there. <b>Replace</b> moves the existing file to "
            "<code>presets/archive/</code> and writes M110's suggestion. "
            "<b>Keep existing</b> leaves the file as it is, and M110 won't ask "
            "again until its suggestion changes.")
        note.setWordWrap(True)
        lay.addWidget(note)

        self.table = make_table(_COLUMNS, stretch_last=True)
        self.table.setSortingEnabled(False)
        # Only the tick boxes are interactive; a selected/focused row adds nothing.
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setRowCount(n)
        for r, c in enumerate(self._conflicts):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            tick.setCheckState(Qt.Checked)
            self.table.setItem(r, 0, tick)
            self.table.setItem(r, 1, QTableWidgetItem(c.target))
            self.table.setItem(r, 2, QTableWidgetItem(c.job or "all frames"))
            self.table.setItem(r, 3, QTableWidgetItem(describe_changes(c.changes)))
        self.table.resizeColumnsToContents()
        fit_table_height(self.table, max_rows=8)
        lay.addWidget(self.table)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self._keep_btn = QPushButton("Keep existing")
        self._keep_btn.clicked.connect(self.reject)
        self._replace_btn = QPushButton("Replace selected")
        self._replace_btn.setDefault(True)
        self._replace_btn.clicked.connect(self.accept)
        btns.addWidget(self._keep_btn)
        btns.addWidget(self._replace_btn)
        lay.addLayout(btns)

    def reject(self):
        # Closing the window keeps every preset, the same as "Keep existing".
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Unchecked)
        super().reject()

    def replace_paths(self) -> set[str]:
        return {c.preset_path for r, c in enumerate(self._conflicts)
                if self.table.item(r, 0).checkState() == Qt.Checked}


def resolve_preset_conflicts(parent, result: dict) -> dict | None:
    """After an ingest's auto-prep: ask about any conflicting presets and apply
    the answer. Call from the worker's *done* slot, after its progress dialog has
    closed — never from inside an item-view handler. None when nothing differed."""
    conflicts = preset_conflicts(result.get("autoprep") if result else None)
    if not conflicts:
        return None
    dlg = PresetConflictDialog(conflicts, parent)
    dlg.exec()
    replace = dlg.replace_paths()
    dlg.deleteLater()
    return siril.apply_preset_choices(conflicts, replace)
