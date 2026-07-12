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


def _held_page(tmp_path, monkeypatch, qtbot):
    """An ImportPage with one file waiting in the Inbox holding area."""
    from m110 import config
    root = seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    held = config.STAGING_DIR / "M94"
    held.mkdir(parents=True)
    (held / "mystery.fit").write_text("x" * 64)
    from m110.ui.pages.import_page import ImportPage
    page = ImportPage()
    qtbot.addWidget(page)
    return page


def _action_buttons(page, row):
    """The {label: QPushButton} in a holding row's Actions cell."""
    from PySide6.QtWidgets import QPushButton
    cell = page.holding_table.cellWidget(row, 5)
    return {b.text(): b for b in cell.findChildren(QPushButton)}


def test_holding_assign_column_is_legible(tmp_path, monkeypatch, qtbot):
    """#65: the Object/Kind/Actions columns are cell widgets, which
    resizeColumnsToContents ignores — they get explicit widths so the buttons
    aren't clipped."""
    page = _held_page(tmp_path, monkeypatch, qtbot)
    assert page.holding_table.rowCount() == 1
    assert page.holding_table.columnWidth(5) >= 200         # Assign · Reveal · Discard
    assert set(_action_buttons(page, 0)) == {"Assign", "Reveal", "Discard"}


def test_holding_discard_removes_row(tmp_path, monkeypatch, qtbot):
    """Discard deletes the held files (auto-confirmed) and the row drops out."""
    from PySide6.QtWidgets import QMessageBox
    from m110 import config
    page = _held_page(tmp_path, monkeypatch, qtbot)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    _action_buttons(page, 0)["Discard"].click()
    assert page.holding_table.rowCount() == 0
    assert not (config.STAGING_DIR / "M94").exists()


def test_holding_reveal_opens_folder(tmp_path, monkeypatch, qtbot):
    """Reveal hands the group's Inbox folder to the OS file manager."""
    from PySide6.QtGui import QDesktopServices
    from m110 import config
    page = _held_page(tmp_path, monkeypatch, qtbot)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(url.toLocalFile()))
    _action_buttons(page, 0)["Reveal"].click()
    assert opened == [str(config.STAGING_DIR / "M94")]


def test_holding_selections_survive_benign_refresh(tmp_path, monkeypatch, qtbot):
    """#66: a focus/modal-close refresh must not wipe the user's in-progress picks."""
    page = _held_page(tmp_path, monkeypatch, qtbot)
    page.holding_table.cellWidget(0, 3).setCurrentText("M94")
    kind = page.holding_table.cellWidget(0, 4)
    kind.setCurrentIndex(kind.findData("stack"))
    page.refresh_holding()                                   # the benign refresh
    assert page.holding_table.cellWidget(0, 3).currentText() == "M94"
    assert page.holding_table.cellWidget(0, 4).currentData() == "stack"


def test_holding_dropdown_picks_up_new_object(tmp_path, monkeypatch, qtbot):
    """#64: a just-added object appears in the holding object dropdown (the catalog
    cache is refreshed on rescan, not cached for the page's lifetime)."""
    from m110 import catalog
    page = _held_page(tmp_path, monkeypatch, qtbot)
    assert "M51" not in page._catalog_ids()
    catalog._append_library_entries(
        {"m51": {"id": "M51", "name": "Whirlpool", "type": "galaxy"}})
    page.refresh_holding()
    combo = page.holding_table.cellWidget(0, 3)
    assert "M51" in [combo.itemText(i) for i in range(combo.count())]


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


def _held_fits(folder, name, **headers):
    import numpy as np
    from astropy.io import fits
    folder.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="float32"))
    for k, v in headers.items():
        h.header[k] = v
    h.writeto(folder / name)


def test_holding_prefills_suggested_object_and_kind(tmp_path, monkeypatch, qtbot):
    """#26: a held FITS with an OBJECT header pre-selects the Object + Kind pickers."""
    from m110 import config
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    _held_fits(config.STAGING_DIR / "mystery", "a.fit", OBJECT="M 10", IMAGETYP="Light")
    from m110.ui.pages.import_page import ImportPage
    page = ImportPage()
    qtbot.addWidget(page)
    assert page.holding_table.rowCount() == 1
    assert page.holding_table.cellWidget(0, 3).currentText() == "M10"     # Object
    assert page.holding_table.cellWidget(0, 4).currentData() == "light"    # Kind


def test_holding_inspect_dialog_shows_header_and_suggestion(tmp_path, monkeypatch, qtbot):
    from m110 import config, ingest, catalog
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    ra, dec = catalog.load_coords()["m10"]
    _held_fits(config.STAGING_DIR / "blob", "x.fit",
               OBJECT="M 10", IMAGETYP="Light", RA=ra, DEC=dec)
    groups = ingest.group_ops(ingest.scan_holding())
    info = ingest.annotate_holding(groups)
    from m110.ui.holding_inspect_dialog import HoldingInspectDialog
    from PySide6.QtWidgets import QLabel, QTableWidget
    dlg = HoldingInspectDialog(groups[0], info[0])
    qtbot.addWidget(dlg)
    labels = " ".join(w.text() for w in dlg.findChildren(QLabel))
    assert "Suggested" in labels and "M10" in labels
    facts = dlg.findChildren(QTableWidget)
    assert facts and facts[0].rowCount() >= 4        # Object/Type/Filter/RA/Dec


def test_holding_object_combo_is_typeable_and_empty(tmp_path, monkeypatch, qtbot):
    """#34: the holding Object picker is editable, starts empty (so its placeholder
    shows and it reads as type-or-pick), and accepts an arbitrary off-catalog name."""
    page = _held_page(tmp_path, monkeypatch, qtbot)
    combo = page.holding_table.cellWidget(0, 3)
    assert combo.isEditable()
    assert combo.currentText() == ""                       # empty → placeholder visible
    assert combo.lineEdit().placeholderText()              # a non-empty hint is set
    combo.setCurrentText("Barnard's Loop Test")            # an arbitrary name is accepted
    assert combo.currentText() == "Barnard's Loop Test"


def test_assign_accepts_arbitrary_object_name(tmp_path, monkeypatch):
    """Engine capability behind #34: assigning a held group to an off-catalog name
    routes it under that (canonicalized) target."""
    from m110 import ingest
    root = seed_root(tmp_path, monkeypatch)
    held = config.STAGING_DIR / "loose"
    held.mkdir(parents=True)
    (held / "a.fit").write_text("x")
    groups = ingest.group_ops(ingest.scan_holding())
    assigned = ingest.assign(groups[0], "My New Nebula", "light")
    assert assigned.object == ingest.canonical_target("My New Nebula")
    assert assigned.ops and all("lights" in op.dest_rel for op in assigned.ops)
