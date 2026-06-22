"""Offscreen smoke for the Phase-2 pages (Sessions + Journal): they construct,
reload against a seeded temp root, and emit open_object on row/card activation."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tomllib

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from m110 import config, refresh  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


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
    monkeypatch.setattr(config, "SESSIONS_JSONL", internal / "sessions.jsonl")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.ensure_data_root(root)
    return root


def _first_object(root):
    with (root / config.INTERNAL_DIRNAME / "catalog.toml").open("rb") as f:
        slug, entry = next(iter(tomllib.load(f)["catalog"].items()))
    return slug, (entry.get("id") or slug)


def _seed_capture(root, monkeypatch):
    """Give one object a light frame (→ a session) and rebuild derived."""
    slug, tid = _first_object(root)
    lights = config.lights_dir(tid)
    lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    refresh.run_refresh(render=False)
    return slug, tid


def test_sessions_page_lists_and_links(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    slug, tid = _seed_capture(root, monkeypatch)
    from m110.ui.pages.sessions import SessionsPage
    page = SessionsPage()
    try:
        assert page._table.rowCount() >= 1
        # the object cell carries its slug and fires open_object on activation
        got = []
        page.open_object.connect(got.append)
        page._table.itemDoubleClicked.emit(page._table.item(0, 1))
        assert got and got[0] == slug
        # search filters
        page._search.setText("zzz-nomatch")
        assert all(page._table.isRowHidden(r) for r in range(page._table.rowCount()))
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_journal_page_card_per_captured_object(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    slug, tid = _seed_capture(root, monkeypatch)
    from m110.ui.pages.journal import JournalPage
    page = JournalPage()
    try:
        assert page.card_count() >= 1
        got = []
        page.open_object.connect(got.append)
        # click the first card's header button → open_object
        from PySide6.QtWidgets import QPushButton
        card, _ = page._cards[0]
        card.findChild(QPushButton).click()
        assert got and isinstance(got[0], str)
    finally:
        page.deleteLater()
        qapp.processEvents()
