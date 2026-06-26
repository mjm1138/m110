"""Offscreen UI gaps for the Library/detail area (§B/C): status label+colour
mapping, NumItem ordering, and the detail-pane gallery presence (captured object
shows thumbnails + a hero; uncaptured shows none). Natural M/NGC + season sort
keys themselves are unit-tested in test_catalog.py."""
import pytest

pytest.importorskip("PySide6")
PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from m110 import catalog, config, derived, refresh  # noqa: E402
from tests._helpers import add_library, messier_member, seed_root  # noqa: E402


def _png(path, color=(40, 80, 160)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 120), color).save(path)


# ── status label + colours (widgets.status_label / STATUS_COLOR) ─────────────

def test_status_label_and_colours():
    from m110.ui import widgets
    assert widgets.status_label("deep_stack", True) == "Deep Stack"
    assert widgets.status_label("initial", True) == "Initial"
    assert widgets.status_label("deep_stack", False) == "—"      # uncaptured → muted dash
    assert widgets.status_label(None, True) == "—"
    assert widgets.STATUS_COLOR["deep_stack"].name() == "#3fb950"  # green
    assert widgets.STATUS_COLOR["initial"].name() == "#d29922"     # amber


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
