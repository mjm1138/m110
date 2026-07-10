"""Offscreen UI gaps for the Library/detail area (§B/C): status label+colour
mapping, NumItem ordering, and the detail-pane gallery presence (captured object
shows thumbnails + a hero; uncaptured shows none). Natural M/NGC + season sort
keys themselves are unit-tested in test_catalog.py."""
import pytest

pytest.importorskip("PySide6")
PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from m110 import catalog, config, derived, refresh  # noqa: E402
from tests._helpers import add_library, messier_member, seed_root, seed_sandbox  # noqa: E402


def _png(path, color=(40, 80, 160)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 120), color).save(path)


# ── status label + colours (widgets.status_label / theme status_color) ───────

def test_status_label_and_colours():
    from m110.ui import widgets
    from m110.ui.theme import tokens
    assert widgets.status_label("deep_stack", True) == "Deep Stack"
    assert widgets.status_label("initial", True) == "Initial"
    assert widgets.status_label("deep_stack", False) == "—"      # uncaptured → muted dash
    assert widgets.status_label(None, True) == "—"
    # status_color now follows the active theme palette
    tokens.set_active(tokens.DARK)
    assert widgets.status_color("deep_stack").name() == tokens.DARK.status_deep
    tokens.set_active(tokens.LIGHT)
    assert widgets.status_color("deep_stack").name() == tokens.LIGHT.status_deep
    assert widgets.status_color("initial").name() == tokens.LIGHT.status_initial


def test_numitem_sorts_by_key_not_lexically():
    from m110.ui.widgets import NumItem
    # natural M-number order: M2 before M10 (lexical would put M10 first)
    a = NumItem("M2", catalog.catalog_sort_key("M2"))
    b = NumItem("M10", catalog.catalog_sort_key("M10"))
    assert a < b and not (b < a)


# ── detail-pane gallery presence ─────────────────────────────────────────────

def test_detail_gallery_present_when_captured(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    # a light (→ capture status) + a finished render (→ a gallery thumbnail)
    lights = config.lights_dir(tid); lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    _png(config.finished_dir(tid) / f"{tid}_final.png")
    refresh.run_refresh()                       # scan + derive + render (thumbnails)

    from m110.ui.detail import DetailPane
    d = DetailPane()
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        qapp.processEvents()
        assert d._gallery is not None and d._gallery.count() >= 1
        assert d._gallery_items                 # parallel list backing the viewer
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_detail_gallery_grid_is_compact_and_square(tmp_path, monkeypatch, qapp):
    from PySide6.QtCore import QSize
    seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    lights = config.lights_dir(tid); lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    long_name = f"Stacked_120_{tid}_30s_LP_20260524-030000_processed.png"
    _png(config.finished_dir(tid) / long_name)
    refresh.run_refresh()

    from m110.ui.detail import DetailPane, _GALLERY_TILE
    d = DetailPane()
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        qapp.processEvents()
        g = d._gallery
        assert g is not None and g.count() >= 1
        assert g.iconSize() == QSize(_GALLERY_TILE, _GALLERY_TILE)      # denser tile
        assert g.gridSize().width() > 0 and g.gridSize().height() > 0   # explicit → aligned
        item = g.item(0)
        assert not item.icon().isNull()
        assert item.toolTip() == long_name        # full name kept even though it elides
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_detail_no_gallery_when_uncaptured(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, {"ngc-7000": {"id": "NGC 7000", "name": "NA", "type": "nebula"}})
    refresh.run_refresh()
    from m110.ui.detail import DetailPane
    d = DetailPane()
    try:
        d.show_object("ngc-7000", catalog.load_library()["ngc-7000"], {})
        qapp.processEvents()
        assert d._gallery is None               # no images → no gallery widget
    finally:
        d.deleteLater()
        qapp.processEvents()


# ── row thumbnails (Library / Sessions / Processing) ─────────────────────────

def _row_item_for_slug(table, slug, col=0):
    from PySide6.QtCore import Qt
    for r in range(table.rowCount()):
        it = table.item(r, col)
        if it is not None and it.data(Qt.UserRole) == slug:
            return it
    return None


def test_catalog_row_gets_async_thumbnail(tmp_path, monkeypatch, qapp, qtbot):
    seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    lights = config.lights_dir(tid); lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    _png(config.finished_dir(tid) / f"{tid}_final.png")
    refresh.run_refresh()

    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        item = _row_item_for_slug(page.table, slug)
        assert item is not None
        qtbot.waitUntil(lambda: not item.icon().isNull(), timeout=2000)
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_sessions_row_gets_async_thumbnail(tmp_path, monkeypatch, qapp, qtbot):
    seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    lights = config.lights_dir(tid); lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    _png(config.finished_dir(tid) / f"{tid}_final.png")
    refresh.run_refresh()

    from m110.ui.pages.sessions import SessionsPage
    page = SessionsPage()
    try:
        item = _row_item_for_slug(page._table, slug, col=1)
        assert item is not None
        qtbot.waitUntil(lambda: not item.icon().isNull(), timeout=2000)
    finally:
        page.deleteLater()
        qapp.processEvents()


# ── viewer metadata overlay (detail._gallery_meta) ────────────────────────────

def _stack_fits(path, stackcnt=12, exptime=30.0):
    np = pytest.importorskip("numpy")
    astropy_fits = pytest.importorskip("astropy.io.fits")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.random.default_rng(0).random((64, 64)) * 1000).astype("float32")
    h = astropy_fits.PrimaryHDU(data)
    h.header["STACKCNT"] = stackcnt
    h.header["EXPTIME"] = exptime
    h.header["LIVETIME"] = stackcnt * exptime
    h.writeto(path)


def test_gallery_meta_includes_source_date_size(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    lights = config.lights_dir(tid); lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    _png(config.finished_dir(tid) / f"{tid}_final.png")
    refresh.run_refresh()

    from m110.ui.detail import DetailPane
    d = DetailPane()
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        qapp.processEvents()
        meta = d._gallery_items[0]["meta"]
        assert meta.get("Source") == "Finished render"
        assert meta.get("Date")             # some YYYY-MM-DD string
        assert "MB" in meta.get("Size", "")
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_gallery_meta_filter_single_vs_mixed(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    lights = config.lights_dir(tid); lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    _png(config.finished_dir(tid) / f"{tid}_final.png")
    refresh.run_refresh()

    from m110.ui.detail import DetailPane
    d = DetailPane()
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        qapp.processEvents()
        assert d._gallery_items[0]["meta"].get("Filter") == "LP"

        # a second session with a *different* filter → now ambiguous, dropped
        (lights / f"Light_{tid}_30.0s_IRCUT_20260530-010101.fit").write_text("x")
        refresh.run_refresh()
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        qapp.processEvents()
        assert "Filter" not in d._gallery_items[0]["meta"]
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_gallery_meta_integration_from_matching_stack(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    lights = config.lights_dir(tid); lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    _stack_fits(config.stacks_dir(tid) / "stack.fit", stackcnt=12, exptime=30.0)
    refresh.run_refresh()

    from m110.ui.detail import DetailPane
    d = DetailPane()
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        qapp.processEvents()
        stack_item = next((im for im in d._gallery_items if im["name"] == "stack.fit"), None)
        assert stack_item is not None
        assert "12 fr" in stack_item["meta"].get("Integration", "")
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_processing_row_gets_async_thumbnail(tmp_path, monkeypatch, qapp, qtbot):
    seed_root(tmp_path, monkeypatch)
    slug, tid = messier_member()
    lights = config.lights_dir(tid); lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    _png(config.finished_dir(tid) / f"{tid}_final.png")   # hero source for the thumbnail
    seed_sandbox(tid)   # unimported Siril output → shows in the "Ready to import" group
    refresh.run_refresh()

    from m110.ui.pages.processing import ProcessingPage
    page = ProcessingPage()
    try:
        item = None
        for i in range(page._lay.count()):
            w = page._lay.itemAt(i).widget()
            if hasattr(w, "rowCount"):
                found = _row_item_for_slug(w, slug)
                if found is not None:
                    item = found
                    break
        assert item is not None
        qtbot.waitUntil(lambda: not item.icon().isNull(), timeout=2000)
    finally:
        page.deleteLater()
        qapp.processEvents()
