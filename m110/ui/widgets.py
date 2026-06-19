"""Shared UI helpers used across the Library pages."""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from m110 import derived

STATUS_LABEL = {"deep_stack": "Deep Stack", "initial": "Initial"}
STATUS_COLOR = {"deep_stack": QColor("#3fb950"), "initial": QColor("#d29922")}
MUTED = QColor("#8b949e")


def status_label(status: str | None, captured: bool) -> str:
    if not captured:
        return "—"
    return STATUS_LABEL.get(status, status or "—")


class NumItem(QTableWidgetItem):
    """Table item that sorts by an arbitrary key (number or tuple)."""

    def __init__(self, text: str, sort_key):
        super().__init__(text)
        self._key = sort_key

    def __lt__(self, other):
        if isinstance(other, NumItem):
            return self._key < other._key
        return super().__lt__(other)


def targets_for_slug(slug: str) -> list[str]:
    """Capture targets (Images/<target>/) that feed this catalog object."""
    by_folder = derived.load_totals().get("by_folder", {})
    return [f for f, info in by_folder.items() if slug in info.get("slugs", [])]


def make_table(headers: list[str], stretch_last: bool = False) -> QTableWidget:
    """A read-only, row-selectable, sortable table (vertical header hidden)."""
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setSelectionMode(QTableWidget.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.setSortingEnabled(True)
    if stretch_last:
        t.horizontalHeader().setStretchLastSection(True)
    return t
