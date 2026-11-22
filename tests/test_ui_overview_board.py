"""UI 1.0 Phase 8 · C — the Overview's catalog board, goal bars and mini bars.

The board is one custom-painted widget, so these drive it through its geometry
(`cell_rect` / `index_at`), real mouse clicks and a real pixmap paint (offscreen
can't catch a `paintEvent` that raises from model-state tests alone).
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from m110 import config, goals  # noqa: E402
from m110.ui import theme  # noqa: E402
from m110.ui.catalog_board import (  # noqa: E402
    CELL_TARGET, CatalogBoard, GoalBar, StatusBarDelegate, PROGRESS_ROLE,
    STATUS_KEY_ROLE,
)
from tests._helpers import seed_capture, seed_root  # noqa: E402


def _cells(n=110, captured=("m31",)):
    by_slug = {s: {"status": "in_progress", "progress": 0.5} for s in captured}
    return goals.board("messier", by_slug)[:n]


def _board(qapp, cells, width=900):
    b = CatalogBoard()
    b.set_cells(cells, {}, {c["slug"]: "Andromeda Galaxy" if c["slug"] == "m31" else ""
                            for c in cells})
    b.resize(width, b.heightForWidth(width))
    b.show()
    qapp.processEvents()
    return b


# ── geometry ────────────────────────────────────────────────────────────────
def test_board_reflows_with_width_and_keeps_a_small_minimum(qapp):
    b = _board(qapp, _cells())
    try:
        cols, cell = b.grid()
        assert cell >= CELL_TARGET
        rows = -(-110 // cols)
        assert b.heightForWidth(b.width()) == 2 * b._pad + rows * cell
        assert b.heightForWidth(400) > b.heightForWidth(1200)   # narrower → taller
        # The minimum is one row: a layout adds it to the page's own minimum, and
        # heightForWidth(min width) here made the Overview thousands of px tall.
        assert b.minimumSizeHint().height() < 2 * CELL_TARGET
        # every cell is inside the widget and the last row isn't cut
        last = b.cell_rect(len(b.cells()) - 1)
        assert last.bottom() <= b.height() and last.right() <= b.width()
    finally:
        b.close()


def test_index_at_maps_points_to_cells_and_gaps_to_nothing(qapp):
    b = _board(qapp, _cells())
    try:
        for i in (0, 17, 109):
            assert b.index_at(b.cell_rect(i).center().toPoint()) == i
        assert b.index_at(QPoint(1, 1)) == -1                  # the padding
        r0, r1 = b.cell_rect(0), b.cell_rect(1)
        gap = QPoint(int((r0.right() + r1.left()) / 2), int(r0.center().y()))
        assert b.index_at(gap) == -1
    finally:
        b.close()


# ── interaction ─────────────────────────────────────────────────────────────
def test_clicking_a_captured_cell_opens_it_and_a_missing_one_does_not(qapp, qtbot):
    cells = _cells()
    b = _board(qapp, cells)
    try:
        i31 = next(i for i, c in enumerate(cells) if c["slug"] == "m31")
        with qtbot.waitSignal(b.object_activated, timeout=1000) as sig:
            QTest.mouseClick(b, Qt.LeftButton, pos=b.cell_rect(i31).center().toPoint())
        assert sig.args == ["m31"]
        got = []
        b.object_activated.connect(got.append)
        QTest.mouseClick(b, Qt.LeftButton, pos=b.cell_rect(0).center().toPoint())  # M1
        qapp.processEvents()
        assert got == []
    finally:
        b.close()


def test_tooltips_name_the_object_and_its_state(qapp):
    cells = _cells()
    b = _board(qapp, cells)
    try:
        i31 = next(i for i, c in enumerate(cells) if c["slug"] == "m31")
        assert b.tooltip_for(i31) == "M31 — Andromeda Galaxy\n50%"
        assert b.tooltip_for(0) == "M1\nNot captured yet"
    finally:
        b.close()


# ── painting ────────────────────────────────────────────────────────────────
def test_board_paints_slots_and_status_feet(qapp):
    cells = goals.board("messier", {"m31": {"status": "deep_stack", "progress": 1.0}})
    b = _board(qapp, cells, width=700)
    try:
        pm = QPixmap(b.size())
        pm.fill(QColor("#ff00ff"))
        b.render(pm)
        img = pm.toImage()
        well = QColor(theme.on_well().well)
        assert QColor(img.pixel(2, b.height() // 2)).red() == well.red()   # the well
        i31 = next(i for i, c in enumerate(cells) if c["slug"] == "m31")
        r = b.cell_rect(i31)
        foot = QColor(img.pixel(int(r.center().x()), int(r.bottom()) - 1))
        assert foot == theme.status_color("deep_stack", well=True)        # full foot
        slot = QColor(img.pixel(int(b.cell_rect(0).center().x()),
                                int(b.cell_rect(0).top()) + 4))
        assert slot != foot and slot != QColor("#ff00ff")
    finally:
        b.close()


def test_goal_bar_segments_and_paint(qapp):
    bar = GoalBar(captured=11, deep=1, total=110)
    deep, cap = bar.segments(220)
    assert deep == pytest.approx(2.0) and cap == pytest.approx(20.0)
    assert GoalBar(5, 9, 3).segments(30) == (30.0, 0.0)        # clamps to the total
    assert GoalBar(0, 0, 0).segments(30) == (0.0, 0.0)
    bar.resize(220, bar.height())
    pm = QPixmap(bar.size())
    bar.render(pm)
    img = pm.toImage()
    y = bar.height() // 2
    assert QColor(img.pixel(1, y)) == QColor(theme.active_tokens().status_deep)
    assert QColor(img.pixel(12, y)) == QColor(theme.active_tokens().status_progress)
    assert QColor(img.pixel(200, y)) == QColor(theme.active_tokens().control)
    assert "11 of 110" in bar.toolTip()


def test_status_bar_delegate_paints_a_bar_then_the_label(qapp):
    from PySide6.QtWidgets import QStyleOptionViewItem, QTableWidget, QTableWidgetItem
    t = QTableWidget(1, 1)
    it = QTableWidgetItem("62%")
    it.setData(STATUS_KEY_ROLE, "in_progress")
    it.setData(PROGRESS_ROLE, 0.62)
    t.setItem(0, 0, it)
    d = StatusBarDelegate(t)
    pm = QPixmap(160, 24)
    pm.fill(QColor("#000000"))
    p = QPainter(pm)
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 160, 24)
    opt.widget = t
    opt.font = t.font()
    d.paint(p, opt, t.model().index(0, 0))
    p.end()
    img = pm.toImage()
    x0 = StatusBarDelegate.BAR_W * 0.3 + 6
    assert QColor(img.pixel(int(x0), 12)) == theme.status_color("in_progress")
    assert d.sizeHint(opt, t.model().index(0, 0)).width() > StatusBarDelegate.BAR_W


# ── the Overview page ───────────────────────────────────────────────────────
def test_overview_leads_with_the_board_for_the_first_active_goal(tmp_path, monkeypatch,
                                                                  qapp):
    from PySide6.QtWidgets import QComboBox, QLabel
    from m110.ui.pages.overview import OverviewPage
    from m110.ui.widgets import CollapsibleSection
    root = seed_root(tmp_path, monkeypatch)
    slug, _ = seed_capture(root)
    page = OverviewPage()
    try:
        assert page.board is not None and len(page.board.cells()) == 110
        assert page.board_goal() == "messier"
        first = page._content.findChildren(CollapsibleSection)[0]
        assert first.isAncestorOf(page.board)                      # the hero, on top
        count = page._content.findChild(QLabel, "boardCount").text()
        assert count == "1 / 110"
        assert page._content.findChild(QComboBox, "boardGoalPicker") is None  # one goal
        got = []
        page.open_object.connect(got.append)
        page.board.object_activated.emit(slug)
        assert got == [slug]
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_board_goal_picker_switches_and_remembers(tmp_path, monkeypatch, qapp, qtbot):
    from PySide6.QtWidgets import QComboBox
    from m110 import refresh
    from m110.ui.pages.overview import BOARD_GOAL_KEY, OverviewPage
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    goals.set_active_goals(["messier", "caldwell"])
    refresh.rederive()
    page = OverviewPage()
    try:
        picker = page._content.findChild(QComboBox, "boardGoalPicker")
        assert picker is not None and picker.count() == 2
        picker.setCurrentIndex(picker.findData("caldwell"))
        qtbot.waitUntil(lambda: page.board is not None and len(page.board.cells()) == 109,
                        timeout=2000)
        assert config.get_setting(BOARD_GOAL_KEY) == "caldwell"
        assert page.board_goal() == "caldwell"
        goals.set_active_goals(["messier"])                        # no longer active
        assert page.board_goal() == "messier"                      # falls back
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_empty_store_still_shows_the_board_and_goal_bars(tmp_path, monkeypatch, qapp):
    from m110 import refresh
    from m110.ui.pages.overview import OverviewPage
    seed_root(tmp_path, monkeypatch)
    refresh.rederive()                  # a fresh store's first sync: goals at 0/110
    page = OverviewPage()
    try:
        assert page.board is not None
        assert {c["state"] for c in page.board.cells()} == {"missing"}
        bars = page._content.findChildren(GoalBar)
        assert bars and bars[0].captured == 0 and bars[0].total == 110
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_goals_section_is_bars_not_a_table(tmp_path, monkeypatch, qapp):
    from PySide6.QtWidgets import QTableWidget
    from m110 import derived
    from m110.ui.pages.overview import OverviewPage
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    page = OverviewPage()
    try:
        bars = page._content.findChildren(GoalBar)
        assert len(bars) == len(derived.load_goals())
        for tbl in page._content.findChildren(QTableWidget):
            heads = [tbl.horizontalHeaderItem(c).text() for c in range(tbl.columnCount())]
            assert heads[:2] != ["Goal", "Captured"]               # the old table is gone
        integ = next(t for t in page._content.findChildren(QTableWidget)
                     if t.horizontalHeaderItem(0).text() == "Object"
                     and t.columnCount() == 6)
        assert isinstance(integ.itemDelegateForColumn(5), StatusBarDelegate)
        assert integ.item(0, 5).data(STATUS_KEY_ROLE)
    finally:
        page.deleteLater()
        qapp.processEvents()
