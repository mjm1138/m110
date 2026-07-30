"""Offscreen tests for the Library's Map view (ROADMAP item 12).

The chart itself is uranometria's; what matters here is the wiring — that the
map draws what the object views are showing, that a click on a marker lands on
the right object, and that a missing chart library is a message rather than a
crash. Geometry is asserted through the widget's own coordinate mapping, since
offscreen painting proves nothing about a native style (see CLAUDE.md).
"""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QPointF, Qt  # noqa: E402

from m110 import skymap  # noqa: E402
from tests._helpers import add_library, seed_capture, seed_root  # noqa: E402

needs_uranometria = pytest.mark.skipif(
    not skymap.available(), reason="uranometria (the optional skymap extra) not installed"
)

TWO = {
    "m31": {"id": "M31", "name": "Andromeda Galaxy", "type": "galaxy",
            "ra_deg": "10.6847", "dec_deg": "41.2688"},
    "m81": {"id": "M81", "name": "Bode's Galaxy", "type": "galaxy",
            "ra_deg": "148.8882", "dec_deg": "69.0653"},
}


def _page(tmp_path, monkeypatch, entries=None):
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, entries if entries is not None else TWO)
    from m110.ui.pages.catalog import CatalogPage
    return CatalogPage()


@needs_uranometria
def test_switching_to_map_renders_the_visible_objects(tmp_path, monkeypatch, qapp):
    page = _page(tmp_path, monkeypatch)
    try:
        assert page.map_view._charts == []          # not rendered until shown
        page._view_btns["map"].setChecked(True)
        assert page._view_mode == "map"
        charts = page.map_view._charts
        assert [c["hemisphere"] for c in charts] == ["north"]
        assert {m["slug"] for m in charts[0]["objects"]} == {"m31", "m81"}
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_search_narrows_the_map(tmp_path, monkeypatch, qapp):
    # The map draws the object views' filtered set, so search reaches it without
    # the map knowing search exists.
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["map"].setChecked(True)
        page._search.setText("Bode")
        assert {m["slug"] for m in page.map_view._charts[0]["objects"]} == {"m81"}
        page._search.clear()
        assert len(page.map_view._charts[0]["objects"]) == 2
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_render_is_deferred_while_the_map_is_hidden(tmp_path, monkeypatch, qapp):
    # A render costs ~0.1s; typing in a search the user cannot see must not pay it.
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["grid"].setChecked(True)
        page._search.setText("Bode")
        assert page.map_view._charts == []          # nothing rendered
        assert page._map_dirty
        page._view_btns["map"].setChecked(True)     # picks up the pending filter
        assert {m["slug"] for m in page.map_view._charts[0]["objects"]} == {"m81"}
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_clicking_a_marker_selects_that_object(tmp_path, monkeypatch, qapp):
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["map"].setChecked(True)
        canvas = page.map_view.canvas
        canvas.resize(600, 600)
        marker = next(m for m in page.map_view._charts[0]["objects"] if m["slug"] == "m81")
        pos = canvas._to_widget(marker["x"], marker["y"])

        seen = []
        page.map_view.object_clicked.connect(seen.append)
        canvas.mousePressEvent(_press(pos))
        canvas.mouseReleaseEvent(_press(pos))
        assert seen == ["m81"]
        assert page._selected_slug() == "m81"
        assert canvas.selected() == "m81"
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_a_drag_pans_instead_of_selecting(tmp_path, monkeypatch, qapp):
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["map"].setChecked(True)
        canvas = page.map_view.canvas
        canvas.resize(600, 600)
        marker = page.map_view._charts[0]["objects"][0]
        start = canvas._to_widget(marker["x"], marker["y"])
        before = QPointF(canvas._centre)

        seen = []
        page.map_view.object_clicked.connect(seen.append)
        canvas.mousePressEvent(_press(start))
        canvas.mouseMoveEvent(_press(QPointF(start.x() + 60, start.y() + 40)))
        canvas.mouseReleaseEvent(_press(QPointF(start.x() + 60, start.y() + 40)))
        assert seen == []                       # a drag is not a click
        assert canvas._centre != before         # the view moved
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_wheel_zoom_keeps_the_sky_under_the_cursor(tmp_path, monkeypatch, qapp):
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["map"].setChecked(True)
        canvas = page.map_view.canvas
        canvas.resize(600, 600)
        cursor = QPointF(400, 250)
        before = canvas._to_doc(cursor)
        canvas.wheelEvent(_wheel(cursor, 120))
        after = canvas._to_doc(cursor)
        assert canvas._zoom > 1.0
        assert after.x() == pytest.approx(before.x(), abs=0.5)
        assert after.y() == pytest.approx(before.y(), abs=0.5)
        canvas.mouseDoubleClickEvent(_press(cursor))
        assert canvas._zoom == 1.0               # double-click resets
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_hemisphere_toggle_appears_only_with_a_southern_disc(tmp_path, monkeypatch, qapp):
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["map"].setChecked(True)
        assert page.map_view._hemi_seg.isHidden()
    finally:
        page.deleteLater()
        qapp.processEvents()

    entries = dict(TWO)
    entries["ngc104"] = {"id": "NGC 104", "type": "globular",
                         "ra_deg": "6.02", "dec_deg": "-72.08"}
    page = _page(tmp_path / "south", monkeypatch, entries)
    try:
        page._view_btns["map"].setChecked(True)
        assert not page.map_view._hemi_seg.isHidden()
        # Selecting the southern object flips the visible disc to find it.
        page.select_object("ngc104")
        assert page.map_view._hemi_btns["south"].isChecked()
        assert page.map_view.canvas.selected() == "ngc104"
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_objects_without_coordinates_are_reported_not_dropped_silently(
        tmp_path, monkeypatch, qapp):
    entries = dict(TWO)
    entries["unknown"] = {"id": "Unknown", "type": "unknown"}
    page = _page(tmp_path, monkeypatch, entries)
    try:
        page._view_btns["map"].setChecked(True)
        assert not page.map_view._note.isHidden()
        note = page.map_view._note.text()
        assert "Unknown" in note          # the designation, not the internal slug
        assert "unknown" not in note.replace("Unknown", "")
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_missing_chart_library_shows_a_hint_not_a_crash(tmp_path, monkeypatch, qapp):
    page = _page(tmp_path, monkeypatch)
    try:
        def _boom(*a, **k):
            raise skymap.SkymapDepsMissing("pip install uranometria")
        monkeypatch.setattr(skymap, "render", _boom)
        page._view_btns["map"].setChecked(True)
        assert page._view_mode == "map"
        assert not page.map_view._note.isHidden()
        assert "uranometria" in page.map_view._note.text()
        assert page.map_view._legend.isHidden()
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_map_colors_follow_capture_status(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    shot, _tid = seed_capture(root)            # promoted into the Library by refresh
    add_library(root, {"m81": TWO["m81"]})
    from m110.ui.pages.catalog import CatalogPage
    from m110.ui.sky_map import status_colors
    page = CatalogPage()
    try:
        page._view_btns["map"].setChecked(True)
        colors = status_colors()
        svg = page.map_view._charts[0]["svg"]
        assert colors[skymap.STATUS_INITIAL] in svg      # the captured one
        assert colors[skymap.STATUS_UNCAPTURED] in svg   # m81, never shot
    finally:
        page.deleteLater()
        qapp.processEvents()


def _press(pos):
    from PySide6.QtGui import QMouseEvent

    return QMouseEvent(QMouseEvent.Type.MouseButtonPress, pos, pos, pos,
                       Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)


def _wheel(pos, delta):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent

    return QWheelEvent(pos, pos, QPoint(0, 0), QPoint(0, delta), Qt.NoButton,
                       Qt.NoModifier, Qt.ScrollUpdate, False)


@needs_uranometria
def test_catalog_filter_keeps_the_map_on_screen(tmp_path, monkeypatch, qapp):
    """Regression: any rebuild while on the map (a catalog-filter change, a pin
    toggle, a theme switch) used to swap the grid in underneath while the segment
    still read Map — `_rebuild_views` hardcoded list-or-grid."""
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["map"].setChecked(True)
        assert page._view_stack.currentWidget() is page.map_view

        page._catalog_combo.setCurrentIndex(1)          # a real catalog
        assert page._view_mode == "map"
        assert page._view_btns["map"].isChecked()
        assert page._view_stack.currentWidget() is page.map_view   # not the grid

        page.restyle()                                  # the other rebuild path
        assert page._view_stack.currentWidget() is page.map_view
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_clicking_a_marker_leaves_the_filters_alone(tmp_path, monkeypatch, qapp):
    """Regression: the marker click was wired to `select_object`, the routing
    entry point, which clears the search and resets the catalog filter to
    guarantee the target is visible — on the map it is visibly right there, and
    resetting the filter bounced the view back to the grid."""
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["map"].setChecked(True)
        # Messier explicitly — the fixture objects are Messier, and the combo's
        # first entries are other catalogs entirely.
        page._catalog_combo.setCurrentIndex(page._catalog_combo.findData("messier"))
        chosen = page._catalog_combo.currentIndex()
        page._search.setText("M")
        drawn = [m["slug"] for c in page.map_view.charts() for m in c["objects"]]
        assert drawn, "the Messier filter should still chart the fixture objects"

        page._on_map_click(drawn[0])
        assert page._view_mode == "map"
        assert page._view_stack.currentWidget() is page.map_view
        assert page._catalog_combo.currentIndex() == chosen   # filter untouched
        assert page._search.text() == "M"                     # search untouched
        assert page._selected_slug() == drawn[0]
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_a_filtered_out_selection_closes_the_detail(tmp_path, monkeypatch, qapp):
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["map"].setChecked(True)
        page._on_map_click("m81")
        assert page._selected_slug() == "m81"
        page._search.setText("Andromeda")               # m81 drops off the chart
        assert not page._map_has("m81")
        assert page._select_slug("m81") is False        # a miss, like list/grid
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_a_catalog_with_nothing_in_it_shows_an_empty_sky(tmp_path, monkeypatch, qapp):
    """A filter that matches nothing draws the sky with a line saying why,
    rather than a blank pane."""
    page = _page(tmp_path, monkeypatch)
    try:
        page._view_btns["map"].setChecked(True)
        page._search.setText("nothing matches this")
        assert page.map_view.charts()                     # the sky is still drawn
        assert sum(len(c["objects"]) for c in page.map_view.charts()) == 0
        assert page.map_view.canvas._message == "Nothing matches your search."
        assert page.map_view._legend.isHidden()           # no colours to explain
        page._search.clear()
        assert page.map_view.canvas._message == ""        # and it goes away again
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_catalog_filter_only_offers_goals_or_catalogs_you_have(tmp_path, monkeypatch, qapp):
    from m110 import goals

    root = seed_root(tmp_path, monkeypatch)
    add_library(root, TWO)                     # M31 + M81: Messier objects
    goals.set_active_goals(["messier"])
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        offered = {page._catalog_combo.itemData(i)
                   for i in range(page._catalog_combo.count())}
        assert None in offered                 # "All objects" always
        assert "messier" in offered            # an active goal
        # Catalogs that are neither a goal nor represented in the Library would
        # only ever filter to nothing, so they are not offered at all.
        assert "bennett" not in offered
        assert "lacaille" not in offered
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_a_non_goal_catalog_is_not_offered_even_if_you_have_its_objects(
        tmp_path, monkeypatch, qapp):
    """Most Messier objects also sit in one of the Popular lists, so offering
    every catalog you happen to have an object from filled the filter with lists
    the user isn't working. Goals only."""
    from m110 import goals

    root = seed_root(tmp_path, monkeypatch)
    # NGC 7023 is a Caldwell object; track only Messier.
    add_library(root, {"ngc-7023": {"id": "NGC 7023", "type": "reflection",
                                    "ra_deg": "315.39", "dec_deg": "68.16"}})
    goals.set_active_goals(["messier"])
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        offered = {page._catalog_combo.itemData(i)
                   for i in range(page._catalog_combo.count())}
        assert offered == {None, "messier"}
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_a_goal_filter_also_charts_what_you_have_not_shot(tmp_path, monkeypatch, qapp):
    """Filtering to a goal is asking about progress *against the list*, so the
    gaps belong on the chart too — dim, in the not-yet-shot tier."""
    from m110 import goals
    from m110.ui.sky_map import status_colors

    root = seed_root(tmp_path, monkeypatch)
    add_library(root, TWO)                     # two Messier objects
    goals.set_active_goals(["messier"])
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page._view_btns["map"].setChecked(True)
        mine = {m["slug"] for c in page.map_view.charts() for m in c["objects"]}
        assert mine == {"m31", "m81"}          # unfiltered: what you have

        page._catalog_combo.setCurrentIndex(page._catalog_combo.findData("messier"))
        plotted = {m["slug"] for c in page.map_view.charts() for m in c["objects"]}
        assert {"m31", "m81"} <= plotted
        assert len(plotted) > 50               # the rest of Messier joins them
        assert "m1" in plotted and "m1" not in page._cat
        # …and they're drawn in the tier the legend names.
        assert status_colors()[skymap.STATUS_UNCAPTURED] in page.map_view.charts()[0]["svg"]
    finally:
        page.deleteLater()
        qapp.processEvents()


@needs_uranometria
def test_tooltip_shows_the_hero(tmp_path, monkeypatch, qapp):
    from m110 import config as cfg
    from m110.ui.sky_map import _tooltip

    page = _page(tmp_path, monkeypatch)
    try:
        cfg.HERO_DIR.mkdir(parents=True, exist_ok=True)
        (cfg.HERO_DIR / "m81.jpg").write_bytes(b"\xff\xd8fake")
        page._view_btns["map"].setChecked(True)
        page._render_map(force=True)
        by_slug = {m["slug"]: m for c in page.map_view.charts() for m in c["objects"]}

        tip = _tooltip(by_slug["m81"])
        assert "<img" in tip and "m81.jpg" in tip and "M81" in tip
        # No hero rendered for M31, so it falls back to the plain designation.
        assert _tooltip(by_slug["m31"]) == "M31"
        # A hero path that has since gone away must not produce a broken image.
        assert _tooltip({"disp": "X", "image": str(tmp_path / "gone.jpg")}) == "X"
    finally:
        page.deleteLater()
        qapp.processEvents()
