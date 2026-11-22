"""Import's empty state (UI Phase 8 · D): one start page with one primary action;
the scan table only once a scan finds something; the holding area only while
something is held."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QFileDialog  # noqa: E402

from m110 import config  # noqa: E402
from tests._helpers import mount_seestar, seed_root  # noqa: E402
from tests.test_ui_import import _build_external, _held_page, _no_device, _scan  # noqa: E402


def _page(qtbot):
    from m110.ui.pages.import_page import ImportPage
    page = ImportPage()
    qtbot.addWidget(page)
    return page


def test_opens_on_the_start_page_with_one_action(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    page = _page(qtbot)
    assert page.showing_start()
    assert page._primary_btn.text() == "Choose Folder…"
    assert page._primary_btn.isDefault()                 # the accent button
    assert page._other_btn.isHidden()                    # nothing to choose *another* of
    assert page._recent_head.isHidden() and page._recent_btns == []
    assert page._start_note.isHidden()
    assert page._holding_box.isHidden()                  # nothing held → no frame


def test_choose_folder_scans_and_reveals_the_table(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    src, rows = _build_external(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(src))
    page = _page(qtbot)
    page._primary_btn.click()
    _scan(page, qtbot, rows)
    assert not page.showing_start()
    assert str(src) in page._path_lbl.text()
    assert config.get_setting("import_recents")[0] == str(src)

    # Change Source… → back to the start page, which now offers it as a recent place
    page._change_btn.click()
    assert page.showing_start()
    assert page.table.rowCount() == 0 and page._root is None
    assert [b.toolTip() for b in page._recent_btns] == [str(src)]
    page._recent_btns[0].click()                         # a recent place rescans it
    _scan(page, qtbot, rows)
    assert not page.showing_start()


def test_a_mounted_seestar_is_the_primary_action(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    mount_seestar(tmp_path, monkeypatch, "M 72", volume="Seestar S50")
    page = _page(qtbot)
    assert page._primary_btn.text() == "Import from Seestar — Seestar S50"
    assert not page._other_btn.isHidden()
    # "Choose Another Folder…" browses; cancelling the dialog leaves the start page
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    page._other_btn.click()
    assert page.showing_start()
    page._primary_btn.click()
    _scan(page, qtbot, 1)
    assert not page.showing_start()


def test_a_folder_with_nothing_to_import_stays_on_the_start_page(tmp_path, monkeypatch,
                                                                 qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    empty = tmp_path / "Empty card"
    empty.mkdir()
    page = _page(qtbot)
    page.scan_folder(str(empty))
    qtbot.waitUntil(lambda: not page._start_note.isHidden(), timeout=5000)
    assert page.showing_start()
    assert "No capture files were found in Empty card" in page._start_note.text()

    page.scan_folder(str(tmp_path / "unplugged"))
    assert "Folder not found" in page._start_note.text()


def test_an_import_that_empties_the_source_says_so_on_the_start_page(tmp_path, monkeypatch,
                                                                     qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    page = _page(qtbot)
    page._root = str(tmp_path)
    page._post_import_msg = "3 file(s) imported."
    page._on_scan_done([])
    assert page.showing_start()
    assert page._start_note.text() == "3 file(s) imported.  Nothing left to import."


def test_the_holding_area_shows_only_while_something_is_held(tmp_path, monkeypatch, qtbot):
    page = _held_page(tmp_path, monkeypatch, qtbot)
    assert page.showing_start()
    assert not page._holding_box.isHidden()
    assert page.holding_table.rowCount() == 1
    for f in (config.STAGING_DIR / "M94").iterdir():
        f.unlink()
    page.refresh_holding()
    assert page._holding_box.isHidden()


def test_busy_disables_the_start_actions(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    src = tmp_path / "Recent"
    src.mkdir()
    page = _page(qtbot)
    page._remember_recent(str(src))
    page.reload()
    page._set_busy(True)
    assert not any(b.isEnabled() for b in
                   (page._primary_btn, page._change_btn, *page._recent_btns))
    page._set_busy(False)
    assert all(b.isEnabled() for b in (page._primary_btn, *page._recent_btns))
