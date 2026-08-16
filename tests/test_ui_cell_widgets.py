"""A cell widget in a table must not be clipped by the stylesheet's item padding.

The app QSS pads table items, and Qt lays a cell **widget** out inside that padded
rect — but `resizeColumnsToContents` measures items and skips cell widgets, and the
row height is sized for one line of text. So a row of buttons got clipped in both
directions at once: the Saved-field-guides row read "View | Revea | Delete" with the
button tops shaved off, and the Import holding area had hit the same thing earlier
(#65, "Assign" clipped to "ssig") and papered over it with hand-tuned pixel widths.

These assert the arithmetic, not the painting — per the house rule that offscreen
(Fusion) can't validate what QMacStyle draws. `sizeHint` vs the assigned geometry is
style-independent: whatever the style asks for, the cell must be given it.
"""
import re

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QComboBox, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QWidget,
)

from m110.ui.widgets import (  # noqa: E402
    CELL_WIDGET_PAD_H, CELL_WIDGET_PAD_V, fit_cell_widgets, fit_table_height,
)


def _table_with_buttons(qtbot, labels=("View", "Reveal", "Delete"), rows=3):
    t = QTableWidget(rows, 2)
    qtbot.addWidget(t)
    for r in range(rows):
        t.setItem(r, 0, QTableWidgetItem(f"row {r}"))
        cell = QWidget()
        h = QHBoxLayout(cell)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        for text in labels:
            h.addWidget(QPushButton(text))
        t.setCellWidget(r, 1, cell)
    t.resizeColumnsToContents()          # the call that ignores cell widgets
    return t


def _grid(t):
    return 1 if t.showGrid() else 0


def test_qt_alone_does_not_size_the_column_for_a_cell_widget(qtbot):
    """Guards the guard. Every test below would pass vacuously if Qt sized these
    columns itself — so pin the premise: after `resizeColumnsToContents`, the column
    is still too narrow for its cell widget. If this ever fails, Qt learned to
    measure index widgets and `fit_cell_widgets` can be retired."""
    t = _table_with_buttons(qtbot)
    need = t.cellWidget(0, 1).sizeHint().width()
    assert t.columnWidth(1) < need + CELL_WIDGET_PAD_H + _grid(t)


def test_action_column_fits_the_buttons(qtbot):
    t = _table_with_buttons(qtbot)
    fit_cell_widgets(t, 1)
    need = t.cellWidget(0, 1).sizeHint().width()
    assert t.columnWidth(1) >= need + CELL_WIDGET_PAD_H + _grid(t)


def test_rows_grow_for_the_buttons(qtbot):
    """The vertical half — the one the old per-page width hacks never addressed."""
    t = _table_with_buttons(qtbot)
    need = t.cellWidget(0, 1).sizeHint().height()
    fit_cell_widgets(t, 1)
    for r in range(t.rowCount()):
        assert t.rowHeight(r) >= need + CELL_WIDGET_PAD_V + _grid(t)


def test_row_height_survives_fit_table_height(qtbot):
    """`fit_table_height` calls resizeRowsToContents, which re-measures from the
    *items* and would drop every row back to one line of text. The floor has to be
    a minimum section size, not a per-row height, or the fix silently undoes itself
    — which is exactly what happened on the first attempt."""
    t = _table_with_buttons(qtbot)
    need = t.cellWidget(0, 1).sizeHint().height()
    fit_cell_widgets(t, 1)
    fit_table_height(t, max_rows=10)
    for r in range(t.rowCount()):
        assert t.rowHeight(r) >= need + CELL_WIDGET_PAD_V + _grid(t)


def test_measures_the_widest_row_not_the_first(qtbot):
    t = _table_with_buttons(qtbot, rows=3)
    wide = QWidget()                      # a later row needs more room than row 0
    h = QHBoxLayout(wide)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(QPushButton("A considerably longer label"))
    t.setCellWidget(2, 1, wide)
    fit_cell_widgets(t, 1)
    assert t.columnWidth(1) >= wide.sizeHint().width() + CELL_WIDGET_PAD_H + _grid(t)


def test_a_combo_in_an_unlisted_column_still_raises_the_row(qtbot):
    """Rows are measured across every column — the Import preview's remap combo
    lives in a column whose *width* is left alone, but it still needs the height."""
    t = QTableWidget(1, 2)
    qtbot.addWidget(t)
    t.setItem(0, 0, QTableWidgetItem("x"))
    combo = QComboBox()
    combo.addItems(["M51", "M63"])
    t.setCellWidget(0, 1, combo)
    fit_cell_widgets(t)                   # no columns named at all
    assert t.rowHeight(0) >= combo.sizeHint().height() + CELL_WIDGET_PAD_V + _grid(t)


def test_no_cell_widgets_is_a_noop(qtbot):
    t = QTableWidget(2, 2)
    qtbot.addWidget(t)
    t.setItem(0, 0, QTableWidgetItem("x"))
    before = (t.columnWidth(1), t.rowHeight(0))
    fit_cell_widgets(t, 1)
    assert (t.columnWidth(1), t.rowHeight(0)) == before


def test_padding_constants_match_the_stylesheet():
    """The constants restate the QSS item padding. If someone retunes the padding
    and not these, every cell widget silently starts clipping again — so tie them
    together rather than trusting a comment."""
    from m110.ui.theme import qss, tokens
    css = qss.build_qss(tokens.LIGHT)
    m = re.search(r"QTableView::item[^{]*\{\s*padding:\s*(\d+)px\s+(\d+)px", css)
    assert m, "the QTableView::item padding rule moved — update fit_cell_widgets"
    assert 2 * int(m.group(1)) == CELL_WIDGET_PAD_V
    assert 2 * int(m.group(2)) == CELL_WIDGET_PAD_H
