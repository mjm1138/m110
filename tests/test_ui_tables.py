"""Table conventions (UI 1.0 Phase 8, critique §1.5), checked on every page.

* A column of right-aligned cells (numbers) has a right-aligned header —
  `widgets.AlignedHeader`, installed by `compact_table`, reads it off the cells.
* A right-aligned column never stretches as the last section (it would push its
  numbers to the far edge, away from their row).
* Planning's rank column says "Rank", not "#".
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem  # noqa: E402

from m110.ui import widgets  # noqa: E402
from tests._helpers import seed_root, seed_capture  # noqa: E402

RIGHT = Qt.AlignmentFlag.AlignRight


def _right(flags) -> bool:
    return bool(Qt.AlignmentFlag(int(flags)) & RIGHT)


def test_header_follows_its_columns_cells(qapp):
    t = widgets.make_table(["Object", "Frames", "Filter"])
    t.insertRow(0)
    t.setItem(0, 0, QTableWidgetItem("M51"))
    t.setItem(0, 1, widgets.make_numeric(QTableWidgetItem("28")))
    t.setItem(0, 2, QTableWidgetItem("LP"))
    h = t.horizontalHeader()
    assert isinstance(h, widgets.AlignedHeader)
    assert not _right(h.section_alignment(0))
    assert _right(h.section_alignment(1))
    assert not _right(h.section_alignment(2))


def test_explicit_header_alignment_wins(qapp):
    t = widgets.make_table(["A", "B"])
    t.insertRow(0)
    t.setItem(0, 0, widgets.make_numeric(QTableWidgetItem("1")))
    t.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignLeft)
    assert not _right(t.horizontalHeader().section_alignment(0))


def test_sorted_right_aligned_title_leaves_room_for_the_arrow(qapp):
    from PySide6.QtWidgets import QStyleOptionHeader
    t = widgets.make_table(["Object", "+ new"])
    t.insertRow(0)
    t.setItem(0, 0, QTableWidgetItem("M51"))
    t.setItem(0, 1, widgets.make_numeric(QTableWidgetItem("+28")))
    h = t.horizontalHeader()
    h.setSortIndicator(1, Qt.SortOrder.DescendingOrder)
    opt = QStyleOptionHeader()
    h.initStyleOptionForIndex(opt, 1)
    assert opt.text.startswith("+ new") and len(opt.text) > len("+ new")
    h.initStyleOptionForIndex(opt, 0)       # a left-aligned title isn't padded
    assert opt.text == "Object"


def test_keep_identity_column_sizes_to_contents(qapp):
    from PySide6.QtWidgets import QHeaderView
    t = widgets.make_table(["Target", "Notes"])
    widgets.keep_identity_column(t, 0)
    assert (t.horizontalHeader().sectionResizeMode(0)
            == QHeaderView.ResizeMode.ResizeToContents)


def _all_tables(win):
    return [t for t in win.findChildren(QTableWidget) if t.rowCount()]


def test_every_page_aligns_number_headers(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False
    try:
        win.resize(1280, 800)
        win.show()
        for i in range(len(win.NAV)):
            win.go_to(i)
            qapp.processEvents()
        tables = _all_tables(win)
        assert tables, "the seeded store should populate some tables"
        checked = 0
        for t in tables:
            h = t.horizontalHeader()
            assert isinstance(h, widgets.AlignedHeader), t
            for c in range(t.columnCount()):
                cells = widgets.column_alignment(t.model(), c)
                if cells & RIGHT:
                    checked += 1
                    assert _right(h.section_alignment(c)), (
                        t.horizontalHeaderItem(c).text())
                    last = c == t.columnCount() - 1
                    assert not (last and h.stretchLastSection()), (
                        f"right-aligned last column "
                        f"{t.horizontalHeaderItem(c).text()!r} stretches")
        assert checked, "no numeric columns found — the sweep checked nothing"
    finally:
        win.close(); win.deleteLater(); qapp.processEvents()


def test_planning_rank_column(tmp_path, monkeypatch, qapp):
    """Planning's first column is "Rank" (critique §1.5: "#" read as a bug when
    "Visible tonight" leaves gaps), right-aligned, with a tooltip on the gaps."""
    import inspect
    from m110.ui.pages import planning
    src = inspect.getsource(planning.PlanningPage._render_ranking)
    assert '"Rank"' in src and '["#"' not in src
    assert 0 in planning._RANK_NUMERIC
