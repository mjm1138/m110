"""Deep Sky's hover text: one tooltip per object — designation, common name,
capture state — shared by the list, the grid and the sky map."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from m110 import skymap  # noqa: E402
from tests._helpers import add_library, seed_capture, seed_root  # noqa: E402

needs_uranometria = pytest.mark.skipif(
    not skymap.available(), reason="uranometria (the optional skymap extra) not installed")

ORION = {"m42": {"id": "M42", "name": "Orion Nebula", "type": "emission_nebula",
                 "ra_deg": "83.8221", "dec_deg": "-5.3911"}}


def test_object_tooltip_text():
    from m110.ui.pages.catalog import object_tooltip
    t = {"status": "in_progress", "progress": 0.5, "integration_hms": "2h 0m",
         "session_count": 3}
    assert object_tooltip("M42", "Orion Nebula", t) == \
        "M42\nOrion Nebula\n50% · 2h 0m · 3 sessions"
    assert object_tooltip("M42", "Orion Nebula", None) == \
        "M42\nOrion Nebula\nNot captured yet"
    assert object_tooltip("M42", "", {"status": "initial", "session_count": 1}) == \
        "M42\nInitial · 1 session"
    # no common name → no blank line
    assert object_tooltip("NGC 7000", "", None) == "NGC 7000\nNot captured yet"


def _grid_tip(page, slug):
    from m110.ui.image_grid import KEY_ROLE
    m = page._grid_model
    for r in range(m.rowCount()):
        i = m.index(r)
        if i.data(KEY_ROLE) == slug:
            return i.data(Qt.ItemDataRole.ToolTipRole)
    raise AssertionError(f"{slug} not in the grid")


def _row_of(table, slug):
    for r in range(table.rowCount()):
        if table.item(r, 0).data(Qt.UserRole) == slug:
            return r
    raise AssertionError(f"{slug} not in the list")


def test_list_and_grid_share_one_tooltip_with_the_common_name(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, _ = seed_capture(root)
    add_library(root, ORION)
    from m110 import catalog
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        for s in (slug, "m42"):
            name = catalog.load_library()[s].get("name")
            grid = _grid_tip(page, s)
            assert name and name in grid.splitlines()
            row = _row_of(page.table, s)
            for c in range(page.table.columnCount()):
                tip = page.table.item(row, c).toolTip()
                # every cell hovers alike; the status cell may add its own detail below
                assert tip == grid if c != page._status_col else tip.startswith(grid)
        assert _grid_tip(page, "m42") == "M42\nOrion Nebula\nNot captured yet"
        captured = _grid_tip(page, slug).splitlines()
        assert "session" in captured[-1]
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_map_tooltip_defaults_to_designation_and_name(tmp_path):
    from m110.ui.sky_map import _tooltip
    assert _tooltip({"disp": "M42", "name": "Orion Nebula"}) == "M42<br>Orion Nebula"
    assert _tooltip({"disp": "M42"}) == "M42"
    # a host's text wins, escaped, its lines kept
    assert _tooltip({"disp": "M42"}, "M42\nA & B") == "M42<br>A &amp; B"


@needs_uranometria
def test_map_markers_say_what_the_list_says(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, ORION)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page._view_btns["map"].setChecked(True)
        page._render_map(force=True)
        markers = {m["slug"]: m for c in page.map_view.charts() for m in c["objects"]}
        assert markers["m42"]["name"] == "Orion Nebula"          # skymap carries it
        canvas = page.map_view.canvas
        assert canvas.describe is not None
        assert canvas._describe(markers["m42"]) == _grid_tip(page, "m42")
        # an unshot goal member outside the Library still gets its name
        assert "Andromeda Galaxy" in page._describe_slug("m31")
    finally:
        page.deleteLater()
        qapp.processEvents()
