"""Offscreen UI regression: the detail pane must not leak/duplicate buttons.

Reproduces the bug where re-rendering (selection / auto-refresh on resize/focus)
left stale Edit/Prepare/Save+Cancel buttons piling up because `_clear` didn't
recurse into sub-layouts — which also caused a teardown crash when a stale button
was clicked.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from m110 import config  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _count(widget, text):
    return sum(1 for b in widget.findChildren(QPushButton) if b.text() == text)


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBJECTS_DIR", tmp_path / "Objects")
    monkeypatch.setattr(config, "CATALOG_TOML", tmp_path / "absent.toml")
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
    monkeypatch.setattr(config, "CATALOG_TOML", internal / "catalog.toml")
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

        page.table.sortByColumn(6, Qt.DescendingOrder)   # user sorts by Integration
        assert (page._sort_col, page._sort_order) == (6, Qt.DescendingOrder)

        page._rebuild_table()                            # e.g. after an ingest
        hdr = page.table.horizontalHeader()
        assert hdr.sortIndicatorSection() == 6           # sort preserved
        assert hdr.sortIndicatorOrder() == Qt.DescendingOrder
    finally:
        page.deleteLater()
        qapp.processEvents()


def _seed_root(tmp_path, monkeypatch):
    root = tmp_path / "M110"
    internal = root / config.INTERNAL_DIRNAME
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "CATALOG_TOML", internal / "catalog.toml")
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "DERIVED_DIR", internal / "derived")
    monkeypatch.setattr(config, "RENDERS_DIR", internal / "renders")
    monkeypatch.setattr(config, "HERO_DIR", internal / "renders" / "hero")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.ensure_data_root(root)
    return root


def test_shell_nav_default_and_open_object(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    import tomllib
    with (root / config.INTERNAL_DIRNAME / "catalog.toml").open("rb") as f:
        slug, entry = next(iter(tomllib.load(f)["catalog"].items()))
    tid = (entry.get("id") or slug)
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
            ["Summary", "Catalog", "Processing", "Sessions", "Journal"]
        assert win.stack.currentIndex() == 0          # Summary lands first
        win.open_object(slug)                         # link from another page
        assert win.stack.currentIndex() == win._catalog_index
        assert win.catalog._selected_slug() == slug
    finally:
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
