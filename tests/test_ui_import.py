"""Offscreen UI tests for the Import page (m110/ui/pages/import_page.py).

The recursive scan + collision engine is covered in test_ingest.py; here we drive
the page: that pointing it at an arbitrary nested tree populates the grouped,
selectable table with canonicalized copy destinations, and that Browse remembers
recent places. qtbot/qapp come from pytest-qt."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402

from m110 import config  # noqa: E402
from tests._helpers import seed_root  # noqa: E402


def _no_device(monkeypatch):
    monkeypatch.setattr(config, "find_seestar_myworks", lambda: None)


def _build_external(tmp_path):
    """A nested external tree (not under the data root): an M13 lights folder a
    couple levels deep + a media folder. Returns (root, expected_row_count)."""
    src = tmp_path / "external"
    sub = src / "2026-01" / "M13_sub"
    sub.mkdir(parents=True)
    (sub / "Light_M13_a.fit").write_text("x" * 10)
    (sub / "Light_M13_b.fit").write_text("x" * 10)
    med = src / "Lunar_photo"
    med.mkdir(parents=True)
    (med / "moon.jpg").write_text("j")
    return str(src), 2


def _scan(page, qtbot, rows):
    qtbot.waitUntil(lambda: page.table.rowCount() == rows, timeout=5000)


def test_import_page_recurses_and_populates(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    src, rows = _build_external(tmp_path)
    from m110.ui.pages.import_page import ImportPage
    page = ImportPage()
    qtbot.addWidget(page)
    page._root = src
    page.scan()
    _scan(page, qtbot, rows)

    # one row per recognized folder, found despite nesting; media sorts last
    assert page.table.rowCount() == rows
    assert page.table.item(rows - 1, 2).text() == "media"
    # the M13 lights group aggregated both frames, copy destination canonicalized
    r13 = next(r for r in range(rows)
               if "Images/M13/lights" in page.table.item(r, 6).text())
    assert page.table.item(r13, 3).text() == "2"
    assert page.table.item(r13, 1).text().startswith("M13")
    # summary reflects copy semantics (leave the source alone)
    assert "copy" in page._summary.text().lower()


def test_import_page_browse_remembers_recents(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    from m110.ui.pages.import_page import ImportPage, RECENTS_KEY
    page = ImportPage()
    qtbot.addWidget(page)

    page._remember_recent("/some/place/A")
    page._remember_recent("/some/place/B")
    assert config.get_setting(RECENTS_KEY)[:2] == ["/some/place/B", "/some/place/A"]
    # a re-visited path floats to the front, no duplicate
    page._remember_recent("/some/place/A")
    assert config.get_setting(RECENTS_KEY)[0] == "/some/place/A"
    assert config.get_setting(RECENTS_KEY).count("/some/place/A") == 1
    # and it surfaces as a selectable source place
    page.reload()
    datas = [page._source.itemData(i) for i in range(page._source.count())]
    assert "/some/place/A" in datas
