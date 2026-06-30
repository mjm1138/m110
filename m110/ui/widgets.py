"""Shared UI helpers used across the Library pages."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QTableWidget, QTableWidgetItem,
)

from m110 import derived
from m110.ui.theme import muted_color, status_color  # theme-driven (re-exported)

STATUS_LABEL = {"deep_stack": "Deep Stack", "initial": "Initial"}
# Per-cell role carrying the raw status key (e.g. "deep_stack") so the pill delegate
# can pick a theme color while the cell still sorts by its visible text.
STATUS_ROLE = Qt.ItemDataRole.UserRole + 7


def status_label(status: str | None, captured: bool) -> str:
    if not captured:
        return "—"
    return STATUS_LABEL.get(status, status or "—")


class StatusPillDelegate(QStyledItemDelegate):
    """Paints the capture status as a tasteful tinted rounded chip (color from the
    active theme via `STATUS_ROLE`), keeping the cell sortable by its plain text."""
    _HPAD = 10

    def paint(self, painter, option, index):
        # Let the base style paint the row/selection background (text suppressed).
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        status = index.data(STATUS_ROLE)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not text or text == "—" or not status:
            painter.setPen(muted_color())
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, text or "—")
            painter.restore()
            return
        color = status_color(status)
        fm = opt.fontMetrics
        h = fm.height() + 4
        w = fm.horizontalAdvance(text) + self._HPAD * 2
        rect = QRectF(option.rect.left() + 8, option.rect.center().y() - h / 2 + 1, w, h)
        bg = QColor(color); bg.setAlpha(38)
        painter.setBrush(bg); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, h / 2, h / 2)
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width() + self._HPAD * 2 + 16, max(s.height(), 24))


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
    t.setAlternatingRowColors(True)
    if stretch_last:
        t.horizontalHeader().setStretchLastSection(True)
    return t
