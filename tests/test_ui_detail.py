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
    from m110.ui.main import DetailPane
    d = DetailPane()
    e = {"id": "M1", "name": "Crab", "type": "nebula"}
    t = {"status": "initial", "integration_hms": "1:00",
         "session_count": 1, "frames": 10}

    for _ in range(4):                 # re-render repeatedly (as refresh/resize does)
        d.show_object("m1", e, t)
        qapp.processEvents()           # flush deleteLater so counts are real
    assert _count(d._content, "Edit") == 1


def test_detail_edit_buttons_clear_on_cancel(tmp_path, monkeypatch, qapp):
    _isolate(tmp_path, monkeypatch)
    from m110.ui.main import DetailPane
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
