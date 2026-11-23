"""Deep Sky grid: a click selects, a double-click opens the inspector.

Opening the inspector narrows the justified grid (8 columns → 4 at 1280 wide), so
every tile moves. When a single click opened it, a double-click's second click
landed on whatever tile had moved under the cursor. Now selecting never changes
the layout; a double-click, Return or Space opens the inspector, and once it is
open a click only retargets it (the splitter holds still).
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from m110 import catalog, config  # noqa: E402
from m110.ui.image_grid import KEY_ROLE  # noqa: E402
from tests._helpers import add_library, seed_root  # noqa: E402


def _page(tmp_path, monkeypatch, qapp, qtbot, n=40):
    root = seed_root(tmp_path, monkeypatch)
    config.save_setting("library_view_mode", "grid")
    members = list(catalog.load_bundled_catalog("messier")["members"].items())[:n]
    add_library(root, {s: {"name": d, "designation": d} for s, d in members})
    from m110.ui.pages.catalog import CatalogPage
    p = CatalogPage()
    qtbot.addWidget(p)
    p.resize(1280, 760)
    p.show()
    _settle(qapp)
    return p


@pytest.fixture
def page(tmp_path, monkeypatch, qapp, qtbot):
    return _page(tmp_path, monkeypatch, qapp, qtbot)


def _settle(qapp, n=20):
    for _ in range(n):
        qapp.processEvents()


def _layout(p):
    return p.splitter.sizes(), p.grid_view.columns()


def _click(p, qapp, pos, double=False):
    vp = p.grid_view.viewport()
    if double:
        QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, pos)
    else:
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, pos)
    _settle(qapp)


def _hit(p, pos):
    idx = p.grid_view.indexAt(pos)
    return idx.data(KEY_ROLE) if idx.isValid() else None


def test_two_clicks_at_one_point_hit_the_same_object(page, qapp):
    gv = page.grid_view
    assert page.detail.isHidden()
    before = _layout(page)
    pos = gv.visualRect(gv.model().index(5, 0)).center()
    target = _hit(page, pos)
    assert target

    _click(page, qapp, pos)                          # first click of a double-click
    assert page.selected_slug() == target
    assert page.detail.isHidden()                    # selecting alone moves nothing
    assert _layout(page) == before
    assert _hit(page, pos) == target                 # the second click's target

    _click(page, qapp, pos, double=True)
    assert not page.detail.isHidden()
    assert page.detail._current[0] == target
    assert page.selected_slug() == target


def test_open_inspector_follows_a_click_without_moving(page, qapp):
    gv = page.grid_view
    m = gv.model()
    page.select_object(m.index(2, 0).data(KEY_ROLE))
    _settle(qapp)
    assert not page.detail.isHidden()
    opened = _layout(page)

    pos = gv.visualRect(m.index(3, 0)).center()
    other = _hit(page, pos)
    _click(page, qapp, pos)
    assert page.detail._current[0] == other          # retargets at once…
    assert _layout(page) == opened                   # …and nothing reflows
    assert _hit(page, pos) == other


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space])
def test_return_or_space_opens_the_inspector(page, qapp, key):
    gv = page.grid_view
    slug = gv.model().index(1, 0).data(KEY_ROLE)
    page._select_slug(slug)
    _settle(qapp)
    assert page.detail.isHidden()
    QTest.keyClick(gv, key)
    _settle(qapp)
    assert not page.detail.isHidden()
    assert page.detail._current[0] == slug


def test_keys_do_nothing_without_a_selection(page, qapp):
    QTest.keyClick(page.grid_view, Qt.Key_Return)
    _settle(qapp)
    assert page.detail.isHidden()


def test_close_hides_but_keeps_the_selection(page, qapp):
    gv = page.grid_view
    slug = gv.model().index(4, 0).data(KEY_ROLE)
    page.select_object(slug)
    _settle(qapp)
    page.detail._close_btn.click()
    _settle(qapp)
    assert page.detail.isHidden()
    assert page.selected_slug() == slug              # the Object menu still has it
    assert gv.columns() == 8                         # full width again


def test_losing_the_selection_closes_it(tmp_path, monkeypatch, qapp, qtbot):
    page = _page(tmp_path, monkeypatch, qapp, qtbot, n=5)
    gv = page.grid_view
    page.select_object(gv.model().index(0, 0).data(KEY_ROLE))
    _settle(qapp)
    gv.clearSelection()
    _settle(qapp)
    assert page.selected_slug() is None
    assert page.detail.isHidden()


def test_a_click_on_empty_space_in_a_short_grid_changes_nothing(
        tmp_path, monkeypatch, qapp, qtbot):
    """QListView keeps a single selection on an empty click; the layout holds."""
    page = _page(tmp_path, monkeypatch, qapp, qtbot, n=5)
    gv = page.grid_view
    before = _layout(page)
    bottom = QPoint(gv.viewport().width() - 4, gv.viewport().height() - 4)
    assert _hit(page, bottom) is None
    _click(page, qapp, bottom)
    assert page.detail.isHidden()
    assert _layout(page) == before


def test_a_closed_inspector_reopens_on_the_current_selection(page, qapp):
    """A closed inspector isn't kept current, so View › Show Inspector rebuilds it
    for whatever is selected now."""
    gv = page.grid_view
    m = gv.model()
    page.select_object(m.index(0, 0).data(KEY_ROLE))
    _settle(qapp)
    page.detail._close_btn.click()
    later = m.index(6, 0).data(KEY_ROLE)
    _click(page, qapp, gv.visualRect(m.index(6, 0)).center())
    assert page.detail.isHidden()
    page.open_inspector()
    assert page.detail._current[0] == later
