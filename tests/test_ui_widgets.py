"""Shared widgets — status pill delegate + table helpers."""
from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QStyleOptionViewItem, QTableWidget, QTableWidgetItem,
)

from m110.ui import theme
from m110.ui.widgets import (
    STATUS_ROLE, StatusPillDelegate, make_table, status_label,
)


def _opt_index_for(qapp, status, captured):
    t = QTableWidget(1, 1)
    d = StatusPillDelegate(t)
    t.setItemDelegateForColumn(0, d)
    it = QTableWidgetItem(status_label(status, captured))
    it.setData(STATUS_ROLE, status if captured else None)
    t.setItem(0, 0, it)
    idx = t.model().index(0, 0)
    opt = QStyleOptionViewItem()
    d.initStyleOption(opt, idx)
    opt.rect = QRect(0, 0, 160, 28)
    return d, opt, idx, t


def test_pill_delegate_paints_captured(qapp):
    theme.install(qapp)
    d, opt, idx, _t = _opt_index_for(qapp, "deep_stack", True)
    pm = QPixmap(160, 28)
    p = QPainter(pm)
    d.paint(p, opt, idx)              # must not raise
    p.end()
    assert d.sizeHint(opt, idx).width() > opt.rect.width() - 160  # widened for the chip


def test_pill_delegate_paints_uncaptured_dash(qapp):
    theme.install(qapp)
    d, opt, idx, _t = _opt_index_for(qapp, None, False)
    pm = QPixmap(160, 28)
    p = QPainter(pm)
    d.paint(p, opt, idx)              # muted-dash path, must not raise
    p.end()


def test_make_table_has_alternating_rows(qapp):
    t = make_table(["A", "B"])
    assert t.alternatingRowColors() is True
