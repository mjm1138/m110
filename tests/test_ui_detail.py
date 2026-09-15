"""Offscreen UI regression: the detail pane must not leak/duplicate buttons.

Reproduces the bug where re-rendering (selection / auto-refresh on resize/focus)
left stale Edit/Prepare/Save+Cancel buttons piling up because `_clear` didn't
recurse into sub-layouts — which also caused a teardown crash when a stale button
was clicked.
"""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QLabel, QPushButton  # noqa: E402

from m110 import config  # noqa: E402
from tests._helpers import seed_root  # noqa: E402
from m110.ui.widgets import targets_for_slug  # noqa: E402


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
    from tests._helpers import seed_capture
    slug, tid = seed_capture(root)    # real light → session → totals (store not empty)

    from m110.ui.main import MainWindow
    win = MainWindow()
    win._ready = False    # neuter the deferred launch-refresh worker
    try:
        assert [win.nav.item(i).text() for i in range(win.nav.count())] == \
            ["Library", "Overview", "Planning", "Import", "Processing"]
        # A store with captures lands on the Library (home); Library is index 0.
        assert win.stack.currentIndex() == win._catalog_index == 0
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


def test_gallery_item_src_is_the_real_file_for_fits(tmp_path, monkeypatch, qapp):
    """A FITS tile displays a *render*, but Reveal / Open / Export must act on the
    .fit itself — so the item carries the render as "path" and the source as "src".
    (Reveal on a .fit used to open the renders folder; Export shipped the ~480px
    thumbnail instead of re-rendering the FITS at full resolution.)"""
    import numpy as np
    from astropy.io import fits
    from m110 import refresh, catalog, derived
    from tests._helpers import seed_root, seed_capture
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    st = config.stacks_dir(tid); st.mkdir(parents=True, exist_ok=True)
    fit = st / "M_stack_processed.fit"
    fits.PrimaryHDU((np.random.rand(40, 40) * 1000).astype("float32")).writeto(fit)
    refresh.run_refresh()

    from m110.ui.detail import DetailPane
    d = DetailPane()
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        gi = next(g for g in d._gallery_items if g["name"].endswith(".fit"))
        assert gi["src"] == str(fit)                     # the real .fit on disk
        assert gi["path"] != gi["src"]                   # displayed image differs…
        assert str(config.RENDERS_DIR) in gi["path"]     # …and it's the render
    finally:
        d.deleteLater()
        qapp.processEvents()


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


def test_hero_double_click_opens_the_viewer(tmp_path, monkeypatch, qapp):
    """End-to-end for the hero gesture: a real double-click on the hero widget
    opens the image viewer at that same image's place in the gallery.

    Deliberately driven through `QTest.mouseDClick` rather than by calling the
    handler — that's what covers the parts a direct call would skip:
    `ScalableImage.mouseDoubleClickEvent`, the signal, and the `connect` in
    `show_object`. (`tests/test_ui_modal_safety.py` covers the deferral.)"""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from m110 import objects
    slug, e, t = _seed_object_with_images(tmp_path, monkeypatch)
    from m110.ui import detail as detail_mod

    shown = []

    class _FakeViewer:
        def __init__(self, items, idx, **kw):
            self._args = (items, idx)

        def exec(self):
            shown.append(self._args)

    monkeypatch.setattr(detail_mod, "ImageViewer", _FakeViewer)

    d = detail_mod.DetailPane()
    try:
        d.show_object(slug, e, t)
        assert d._hero_widget is not None, "no hero rendered — fixture changed?"
        hero_name = objects.read_journal(slug)[0].get("hero")
        expected = next(i for i, gi in enumerate(d._gallery_items)
                        if gi["name"] == hero_name) if hero_name else \
            d._hero_gallery_index(slug)

        QTest.mouseDClick(d._hero_widget, Qt.LeftButton)
        qapp.processEvents()                 # the open is deferred past the handler

        assert len(shown) == 1
        items, idx = shown[0]
        assert idx == expected                            # opened ON the hero
        assert len(items) == len(d._gallery_items)        # with the whole gallery
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


def test_action_row_sits_below_hero_and_notes_and_wraps(tmp_path, monkeypatch, qapp):
    """The processing actions (Import / Process / Reveal / Send / Stack) used to be
    a `QHBoxLayout` *above* the hero, whose minimum width — the sum of five
    buttons — forced the pane into a horizontal scrollbar. They now live below the
    hero and the notes, in a wrapping `FlowLayout`."""
    from PySide6.QtWidgets import QPushButton
    from m110.ui.detail import DetailPane
    from m110.ui.widgets import FlowLayout
    from m110.ui.image_viewer import ScalableImage
    import numpy as np
    from astropy.io import fits
    slug, e, t = _seed_object_with_images(tmp_path, monkeypatch)
    # A Siril sandbox with a finished render in it → Import/Process/Reveal; a
    # FITS master in stacks/ → Send/Stack. Every button the pane can show.
    for tid in targets_for_slug(slug):
        sb = config.siril_dir(tid); sb.mkdir(parents=True, exist_ok=True)
        (sb / "M_processed.png").write_bytes(b"render")
        st = config.stacks_dir(tid); st.mkdir(parents=True, exist_ok=True)
        fits.PrimaryHDU(np.zeros((4, 4), dtype="float32")).writeto(st / "M_stack.fit")
    d = DetailPane()
    try:
        d.show_object(slug, e, t)
        lay = d._lay
        kinds = []
        for i in range(lay.count()):
            it = lay.itemAt(i)
            if it.widget() is not None:
                w = it.widget()
                kinds.append("hero" if isinstance(w, ScalableImage)
                             else "notes" if w.__class__.__name__ == "QTextBrowser"
                             or (isinstance(w, QLabel) and "No notes" in w.text())
                             else None)
            elif isinstance(it.layout(), FlowLayout):
                kinds.append("actions")
        kinds = [k for k in kinds if k]
        assert kinds.index("hero") < kinds.index("notes") < kinds.index("actions")
        flow = next(lay.itemAt(i).layout() for i in range(lay.count())
                    if isinstance(lay.itemAt(i).layout(), FlowLayout))
        labels = [flow.itemAt(i).widget().text() for i in range(flow.count())]
        assert labels == ["Import finished work…", "Process in Siril",
                          "Reveal working folder", "Stack in StackingWizard…",
                          "Send to AstroWizard…"]
        assert all(isinstance(flow.itemAt(i).widget(), QPushButton)
                   for i in range(flow.count()))
        # The row's minimum is one button wide, so a narrow pane wraps it rather
        # than growing a horizontal scrollbar for the whole pane.
        widest = max(flow.itemAt(i).widget().minimumSizeHint().width()
                     for i in range(flow.count()))
        assert flow.minimumSize().width() == widest
        assert flow.heightForWidth(widest + 8) > flow.heightForWidth(4000)
    finally:
        d.deleteLater(); qapp.processEvents()
