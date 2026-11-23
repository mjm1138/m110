"""Import, Mike's option B (Phase 8 follow-up): the Source row is always on top; the
table area holds a message in the table's place — the next step while nothing is
chosen, "No frames found in <folder>" for a chosen folder with nothing to import
(never the nothing-chosen state). The holding area is one line while empty."""
from pathlib import Path

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


def _message(page):
    return page._area.currentIndex() == 1


def test_opens_with_the_source_row_and_one_next_step(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    page = _page(qtbot)
    assert not page._source.isHidden() and not page._browse_btn.isHidden()
    assert page._source.currentData() is None            # "Choose a source…"
    assert _message(page)
    assert page._msg_title.text() == "Import captures"
    assert page._primary_btn.text() == "Choose Folder…"
    assert page._primary_btn.isDefault()                 # the accent button
    assert page._other_btn is None and page._recent_btns == []
    assert not page._rescan_btn.isEnabled()              # nothing to rescan yet
    assert not page._import_btn.isEnabled()


def test_choose_folder_scans_into_the_table(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    src, rows = _build_external(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(src))
    page = _page(qtbot)
    page._primary_btn.click()
    _scan(page, qtbot, rows)
    assert not _message(page)
    assert page._source.currentData() == str(src)        # the source row names it
    assert str(src) in page._path_lbl.text()
    assert config.get_setting("import_recents")[0] == str(src)
    assert page._import_btn.isEnabled() and page._import_btn.isDefault()
    assert page._all_btn.isEnabled() and page._none_btn.isEnabled()
    page._none_btn.click()
    assert not page._import_btn.isEnabled()
    page._all_btn.click()
    assert page._import_btn.isEnabled()

    # Back to "Choose a source…" → the next step again, offering it as a recent
    page._source.setCurrentIndex(0)
    page._on_source_chosen(0)
    assert _message(page) and page._root is None
    assert [b.toolTip() for b in page._recent_btns] == [str(src)]
    page._recent_btns[0].click()                         # a recent folder rescans it
    _scan(page, qtbot, rows)
    assert not _message(page)


def test_browse_scans_a_chosen_folder(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    src, rows = _build_external(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(src))
    page = _page(qtbot)
    page._browse_btn.click()
    _scan(page, qtbot, rows)
    assert page._source.currentData() == str(src)


def test_a_mounted_seestar_is_the_next_step(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    mount_seestar(tmp_path, monkeypatch, "M 72", volume="Seestar S50")
    page = _page(qtbot)
    assert page._primary_btn.text() == "Import from Seestar — Seestar S50"
    assert page._other_btn is not None
    # "Choose Another Folder…" browses; cancelling the dialog changes nothing
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    page._other_btn.click()
    assert _message(page) and page._root is None
    page._primary_btn.click()
    _scan(page, qtbot, 1)
    assert not _message(page)
    assert page._source.currentText().startswith("Seestar device")


def test_an_empty_folder_stays_chosen_and_says_so(tmp_path, monkeypatch, qtbot):
    """Mike: falling back to the no-selection view for an empty folder 'feels like
    a bug'. The folder stays the source, and the message names it."""
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    empty = tmp_path / "Empty card"
    empty.mkdir()
    page = _page(qtbot)
    page.scan_folder(str(empty))
    qtbot.waitUntil(lambda: page._worker is None, timeout=5000)
    assert _message(page)
    assert page._msg_title.text() == "No frames found in Empty card"
    assert page._root == str(empty)
    assert page._source.currentData() == str(empty)      # still the chosen source
    assert page._primary_btn is None and page._recent_btns == []   # not the start
    assert page._rescan_btn.isEnabled()
    assert not page._import_btn.isEnabled()
    assert not page._import_btn.isDefault()              # no gold on a dead button
    assert not page._all_btn.isEnabled() and not page._none_btn.isEnabled()

    # files appear → Rescan finds them, in the same folder
    src, rows = _build_external(tmp_path)
    src = Path(src)
    for f in src.rglob("*"):
        if f.is_file():
            dest = empty / f.relative_to(src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.read_bytes())
    page._rescan_btn.click()
    _scan(page, qtbot, rows)
    assert not _message(page)


def test_a_missing_folder_stays_chosen(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    page = _page(qtbot)
    page.scan_folder(str(tmp_path / "unplugged"))
    assert _message(page)
    assert page._msg_title.text() == "Folder not found: unplugged"
    assert page._source.currentData() == str(tmp_path / "unplugged")


def test_an_import_that_empties_the_source_says_so(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    page = _page(qtbot)
    page._root = str(tmp_path / "Card")
    page._post_import_msg = "3 file(s) imported."
    page._on_scan_done([])
    assert _message(page)
    assert page._msg_title.text() == "3 file(s) imported."
    assert page._msg_body.text() == "Nothing left to import in Card."


def test_cancelled_and_failed_scans_keep_the_folder(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    page = _page(qtbot)
    page._root = str(tmp_path)
    page._on_scan_cancelled()
    assert _message(page) and page._msg_title.text() == "Scan cancelled"
    page._on_scan_failed("disk said no")
    assert page._msg_title.text() == "Scan failed"
    assert page._msg_body.text() == "disk said no"
    assert page._root == str(tmp_path)


def test_the_holding_area_is_one_line_while_empty(tmp_path, monkeypatch, qtbot):
    page = _held_page(tmp_path, monkeypatch, qtbot)
    assert not page.holding_table.isHidden() and not page._bulk_bar.isHidden()
    assert page.holding_table.rowCount() == 1
    for f in (config.STAGING_DIR / "M94").iterdir():
        f.unlink()
    page.refresh_holding()
    assert page.holding_table.isHidden() and page._bulk_bar.isHidden()
    assert page._holding_header.text() == "Nothing held."
    assert not page._holding_box.isHidden()              # the frame stays, one line


def test_the_source_combo_never_forces_the_window_wide(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    deep = tmp_path / ("a-very-long-folder-name-" * 6) / "and-deeper" / "Captures"
    deep.mkdir(parents=True)
    page = _page(qtbot)
    narrow = page._source.sizeHint().width()
    page._remember_recent(str(deep))
    page.reload()
    assert page._source.sizeHint().width() == narrow
    i = page._source.findData(str(deep))
    assert page._source.itemText(i).startswith("Captures — ")
    assert page._source.itemData(i, 3) == str(deep)      # Qt.ToolTipRole


def test_busy_disables_the_next_step(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    src = tmp_path / "Recent"
    src.mkdir()
    page = _page(qtbot)
    page._remember_recent(str(src))
    page.reload()
    page._set_busy(True)
    assert not any(b.isEnabled() for b in
                   (page._primary_btn, page._source, page._browse_btn,
                    *page._recent_btns))
    page._set_busy(False)
    assert all(b.isEnabled() for b in (page._primary_btn, *page._recent_btns))
