"""Offscreen UI regression: the detail pane must not leak/duplicate buttons.

Reproduces the bug where re-rendering (selection / auto-refresh on resize/focus)
left stale Edit/Prepare/Save+Cancel buttons piling up because `_clear` didn't
recurse into sub-layouts — which also caused a teardown crash when a stale button
was clicked.
"""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QPushButton  # noqa: E402

from m110 import config  # noqa: E402
from tests._helpers import seed_root  # noqa: E402


def _count(widget, text):
    return sum(1 for b in widget.findChildren(QPushButton) if b.text() == text)


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBJECTS_DIR", tmp_path / "Objects")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    monkeypatch.setattr(config, "DERIVED_DIR", tmp_path / "derived")
    monkeypatch.setattr(config, "RENDERS_DIR", tmp_path / "renders")
    monkeypatch.setattr(config, "HERO_DIR", tmp_path / "renders" / "hero")


def test_detail_buttons_do_not_accumulate(tmp_path, monkeypatch, qapp):
    _isolate(tmp_path, monkeypatch)
    from m110.ui.detail import DetailPane
    d = DetailPane()
    e = {"id": "M1", "name": "Crab", "type": "nebula"}
    t = {"status": "initial", "integration_hms": "1:00",
         "session_count": 1, "frames": 10}

    for _ in range(4):                 # re-render repeatedly (as refresh/resize does)
        d.show_object("m1", e, t)
        qapp.processEvents()           # flush deleteLater so counts are real
    assert _count(d._content, "Edit") == 1


def test_table_sort_persists_across_rebuild(tmp_path, monkeypatch, qapp):
    from PySide6.QtCore import Qt
    root = tmp_path / "M110"
    internal = root / config.INTERNAL_DIRNAME
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "LIBRARY_TOML", internal / "library.toml")
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "DERIVED_DIR", internal / "derived")
    monkeypatch.setattr(config, "RENDERS_DIR", internal / "renders")
    monkeypatch.setattr(config, "HERO_DIR", internal / "renders" / "hero")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.ensure_data_root(root)

    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        assert page.table.horizontalHeader().sortIndicatorSection() == 0  # Object

        integ = page.HEADERS.index("Integration")
        page.table.sortByColumn(integ, Qt.DescendingOrder)   # user sorts by Integration
        assert (page._sort_col, page._sort_order) == (integ, Qt.DescendingOrder)

        page._rebuild_views()                            # e.g. after an ingest
        hdr = page.table.horizontalHeader()
        assert hdr.sortIndicatorSection() == integ       # sort preserved
        assert hdr.sortIndicatorOrder() == Qt.DescendingOrder
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_shell_nav_default_and_open_object(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    from m110 import catalog
    slug, tid = next(iter(catalog.load_bundled_catalog("messier")["members"].items()))
    lights = config.lights_dir(tid)
    lights.mkdir(parents=True)
    (lights / f"Light_{tid}_a.fit").write_text("x")
    from m110 import refresh
    refresh.run_refresh()

    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False    # neuter the deferred launch-refresh worker
    try:
        assert [win.nav.item(i).text() for i in range(win.nav.count())] == \
            ["Summary", "Goals", "Library", "Processing", "Sessions", "Journal",
             "Media", "Import"]
        assert win.stack.currentIndex() == 0          # Summary lands first
        win.open_object(slug)                         # link from another page
        assert win.stack.currentIndex() == win._catalog_index
        assert win.catalog._selected_slug() == slug
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_quit_waits_for_running_refresh_worker(tmp_path, monkeypatch, qapp):
    """Regression: quitting (incl. Cmd+Q from a viewer) must wait for the refresh
    QThread, or Qt aborts ('Destroyed while thread is still running')."""
    seed_root(tmp_path, monkeypatch)
    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = True
    try:
        win._do_refresh()                       # starts the RefreshWorker thread
        assert win._worker is not None
        win._stop_worker()                      # must block until it finishes
        assert not win._worker.isRunning()      # safe to tear down now
    finally:
        win._ready = False
        win._stop_worker()
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_detail_edit_buttons_clear_on_cancel(tmp_path, monkeypatch, qapp):
    _isolate(tmp_path, monkeypatch)
    from m110.ui.detail import DetailPane
    d = DetailPane()
    e = {"id": "M1", "name": "Crab", "type": "nebula"}
    d.show_object("m1", e, {})
    qapp.processEvents()

    d._enter_edit()
    qapp.processEvents()
    assert _count(d._content, "Save") == 1 and _count(d._content, "Cancel") == 1

    d._cancel_edit()
    qapp.processEvents()
    assert _count(d._content, "Save") == 0 and _count(d._content, "Cancel") == 0
    assert _count(d._content, "Edit") == 1     # back to a single Edit button


def _seed_object_with_images(tmp_path, monkeypatch):
    """A captured Messier object with a finished render + a Seestar stack, rendered
    into images.json/heroes. Returns (slug, entry, totals)."""
    from PIL import Image
    from m110 import refresh, catalog, derived
    from tests._helpers import seed_root, seed_capture
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)                      # light → session → totals
    fin = config.finished_dir(tid); fin.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 60), (200, 30, 30)).save(fin / "M_final.png")
    ss = config.seestar_stacks_dir(tid); ss.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 60), (30, 30, 200)).save(ss / "Stacked_1_x.jpg")
    refresh.run_refresh()                               # render=True → images.json
    e = catalog.load_library()[slug]
    t = derived.totals_by_slug().get(slug, {})
    return slug, e, t


def test_gallery_splits_finished_and_working(tmp_path, monkeypatch, qapp):
    slug, e, t = _seed_object_with_images(tmp_path, monkeypatch)
    from m110.ui.detail import DetailPane
    d = DetailPane()
    try:
        d.show_object(slug, e, t)
        states = sorted(gi["_state"] for gi in d._gallery_items)
        assert states == ["finished", "working"]        # one of each tier
        assert len(d._galleries) == 2                    # two labelled groups
    finally:
        d.deleteLater(); qapp.processEvents()


def test_gallery_promote_demote_persists(tmp_path, monkeypatch, qapp):
    from m110 import objects
    slug, e, t = _seed_object_with_images(tmp_path, monkeypatch)
    from m110.ui.detail import DetailPane
    d = DetailPane()
    try:
        d.show_object(slug, e, t)
        # demote the finished render → working
        fin_name = next(gi["name"] for gi in d._gallery_items
                        if gi["_state"] == "finished")
        d._set_curation(fin_name, "working")
        assert objects.get_curation(slug) == {fin_name: "working"}
        # after the in-place reload, that image is now grouped as working
        assert all(gi["_state"] == "working" for gi in d._gallery_items)
    finally:
        d.deleteLater(); qapp.processEvents()


def test_gallery_set_hero_writes_and_rerenders(tmp_path, monkeypatch, qapp):
    from m110 import objects
    slug, e, t = _seed_object_with_images(tmp_path, monkeypatch)
    from m110.ui.detail import DetailPane
    d = DetailPane()
    try:
        d.show_object(slug, e, t)
        # pick the working (Seestar) image as hero
        work_name = next(gi["name"] for gi in d._gallery_items
                         if gi["_state"] == "working")
        fired = []
        d.saved.connect(fired.append)
        d._set_hero(work_name)
        assert objects.read_journal(slug)[0]["hero"] == work_name
        assert objects.hero_path(slug) is not None       # hero re-rendered
        assert fired == [slug]                            # shell told to reload thumbs
    finally:
        d.deleteLater(); qapp.processEvents()
