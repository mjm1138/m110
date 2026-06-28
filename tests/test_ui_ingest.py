"""Offscreen UI tests for the Ingest dialog (m110/ui/ingest_dialog.py).

The ingest *engine* (grouping, canonicalization, pointing, retarget, apply) is
covered in test_ingest.py; here we drive the dialog the engine feeds — that the
threaded scan populates a grouped, selectable table with canonicalized
destinations, renders the pointing-remap dropdown, writes an alias, applies only
checked groups, and tears down safely. qtbot/qapp come from pytest-qt."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QComboBox, QMessageBox  # noqa: E402

from m110 import catalog, config, ingest  # noqa: E402
from tests._helpers import add_library, fits_at, seed_root  # noqa: E402


def _no_device(monkeypatch):
    # Deterministic: never offer a real mounted Seestar (CI/dev machines vary).
    monkeypatch.setattr(config, "find_seestar_myworks", lambda: None)


def _build_inbox(root):
    """A staging Inbox exercising grouping, canonicalization, a mis-pointed group,
    and media. Returns the expected group (= table-row) count."""
    # The dialog resolves the remap suggestion slug→designation via the Library, so
    # seed the two objects involved (a real store has captured objects in it).
    add_library(root, {"m81": {"id": "M81", "name": "Bode", "type": "galaxy"},
                       "m82": {"id": "M82", "name": "Cigar", "type": "galaxy"}})
    staging = config.STAGING_DIR
    # plain (non-FITS) lights → clean/unverified pointing, plain label
    m27 = staging / "M27_sub"; m27.mkdir()
    (m27 / "Light_M27_a.fit").write_text("x" * 10)
    (m27 / "Light_M27_b.fit").write_text("x" * 10)
    # lowercase variant → canonicalized to M13
    m13 = staging / "m13_sub"; m13.mkdir()
    (m13 / "Light_m13_a.fit").write_text("x" * 10)
    # named M81 but the frame points at M82 → pointing flag + remap suggestion
    ra82, dec82 = catalog.load_coords()["m82"]
    fits_at(staging / "M81_sub" / "Light_M81_a.fit", ra82, dec82)
    # media folder (sorts last)
    med = staging / "Lunar_photo"; med.mkdir()
    (med / "moon.jpg").write_text("j")
    return 4


def _scan(dlg, qtbot, rows):
    qtbot.waitUntil(lambda: dlg.table.rowCount() == rows, timeout=5000)


def _row_for(dlg, dest_contains):
    for r in range(dlg.table.rowCount()):
        if dest_contains in dlg.table.item(r, 6).text():
            return r
    raise AssertionError(f"no row with dest containing {dest_contains!r}")


def test_ingest_dialog_groups_canonicalizes_and_flags_pointing(tmp_path, monkeypatch, qtbot):
    root = seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    rows = _build_inbox(root)
    from m110.ui.ingest_dialog import IngestDialog
    dlg = IngestDialog()
    qtbot.addWidget(dlg)
    _scan(dlg, qtbot, rows)

    # one row per source folder (grouped, not per-frame); media sorts last
    assert dlg.table.rowCount() == rows
    assert dlg.table.item(rows - 1, 2).text() == "media"
    assert dlg.table.item(rows - 1, 5).text() == "—"          # media → no pointing check

    # canonicalization (#12a): lowercase m13_sub routes to Images/M13/lights AND the
    # row label folds to the canonical "M13" (matches where files land).
    r13 = _row_for(dlg, "Images/M13/lights")
    assert dlg.table.item(r13, 6).text() == "Images/M13/lights"
    assert dlg.table.item(r13, 1).text().startswith("M13")     # label canonicalized too

    # the M27 group aggregated both frames
    r27 = _row_for(dlg, "Images/M27/lights")
    assert dlg.table.item(r27, 3).text() == "2"

    # mis-pointed M81 group → a remap dropdown + a ⚠ pointing cell suggesting M82
    r81 = _row_for(dlg, "Images/M81/lights")
    combo = dlg.table.cellWidget(r81, 1)
    assert isinstance(combo, QComboBox)
    assert "M82" in dlg.table.item(r81, 5).text()
    assert "M82" in [combo.itemText(i) for i in range(combo.count())]


def test_ingest_dialog_remap_rewrites_dest_and_writes_alias(tmp_path, monkeypatch, qtbot):
    root = seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    rows = _build_inbox(root)
    # auto-answer the "Remember alias?" prompt with Yes
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    from m110.ui.ingest_dialog import IngestDialog
    dlg = IngestDialog()
    qtbot.addWidget(dlg)
    _scan(dlg, qtbot, rows)

    r81 = _row_for(dlg, "Images/M81/lights")
    combo = dlg.table.cellWidget(r81, 1)
    combo.setCurrentText("M82")                                # user accepts the suggestion
    # destination rewritten + alias persisted for next time
    assert dlg.table.item(r81, 6).text() == "Images/M82/lights"
    assert ingest.load_aliases().get("M81_sub") == "M82"


def test_ingest_dialog_applies_only_checked_groups(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    # keep it simple + fast: two clean objects, no autoprep
    staging = config.STAGING_DIR
    for obj in ("M27", "M13"):
        d = staging / f"{obj}_sub"; d.mkdir()
        (d / f"Light_{obj}_a.fit").write_text("x")
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    from m110 import processing
    monkeypatch.setattr(processing, "run_autoprep", lambda *a, **k: None)
    from m110.ui.ingest_dialog import IngestDialog
    dlg = IngestDialog()
    qtbot.addWidget(dlg)
    _scan(dlg, qtbot, 2)

    # uncheck the M13 row → it must be excluded from the ingest
    r13 = _row_for(dlg, "Images/M13/lights")
    dlg.table.item(r13, 0).setCheckState(Qt.Unchecked)
    with qtbot.waitSignal(dlg.ingested, timeout=5000):
        dlg._do_ingest()

    assert config.lights_dir("M27").is_dir()                   # checked → moved in
    assert not config.target_dir("M13").exists()              # unchecked → untouched
    assert (staging / "M13_sub" / "Light_M13_a.fit").exists()


def test_import_page_holding_assign_moves_files(tmp_path, monkeypatch, qtbot):
    """6c: held files in Inbox/ show in the holding panel; assigning an object+kind
    moves them out of the holding area into the content tree."""
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    blob = config.STAGING_DIR / "blob"
    blob.mkdir(parents=True)
    (blob / "f1.fit").write_text("1")
    (blob / "f2.fit").write_text("2")
    # auto-confirm the move + decline the "remember alias?" follow-up
    answers = iter([QMessageBox.Yes, QMessageBox.No])
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: next(answers, QMessageBox.No)))
    from m110 import processing
    monkeypatch.setattr(processing, "run_autoprep", lambda *a, **k: None)
    from m110.ui.pages.import_page import ImportPage
    p = ImportPage()
    qtbot.addWidget(p)
    p.refresh_holding()

    assert p.holding_table.rowCount() == 1
    assert p.holding_table.item(0, 0).text() == "blob"
    p.holding_table.cellWidget(0, 3).setCurrentText("M27")     # object
    # kind dropdown defaults to the first assignable kind (light)
    assert p.holding_table.cellWidget(0, 4).currentData() == "light"

    with qtbot.waitSignal(p.imported, timeout=5000):
        p._on_assign(0)

    assert sorted(x.name for x in config.lights_dir("M27").iterdir()) == ["f1.fit", "f2.fit"]
    assert not (blob / "f1.fit").exists()                       # moved out of Inbox
    qtbot.waitUntil(lambda: p.holding_table.rowCount() == 0, timeout=5000)


def test_import_page_rescans_after_import(tmp_path, monkeypatch, qtbot):
    """After importing a subset, the view auto-rescans to true remaining state
    (imported group gone, unselected group still shown) instead of going blank."""
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    src = tmp_path / "src"
    for obj, n in (("M27", 3), ("M13", 2)):
        d = src / f"{obj}_sub"
        d.mkdir(parents=True)
        for i in range(n):
            (d / f"Light_{obj}_{i}.fit").write_text("x")
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    from m110.ui.pages.import_page import ImportPage
    p = ImportPage()
    qtbot.addWidget(p)
    p._root = str(src)
    p.scan()
    qtbot.waitUntil(lambda: p.table.rowCount() == 2, timeout=5000)

    # uncheck M13 → import only M27
    for r in range(p.table.rowCount()):
        if p._groups[r].object == "M13":
            p.table.item(r, 0).setCheckState(Qt.Unchecked)
    p._do_import()

    # auto-rescan settles to just the un-imported M13 (not blank), with a confirmation
    qtbot.waitUntil(lambda: not p.is_busy() and p.table.rowCount() == 1, timeout=5000)
    assert p._groups[0].object == "M13"
    assert "imported" in p._summary.text()
    assert config.lights_dir("M27").is_dir() and not config.target_dir("M13").exists()


def test_ingest_dialog_close_during_scan_is_safe(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _no_device(monkeypatch)
    (config.STAGING_DIR / "M5_sub").mkdir()
    (config.STAGING_DIR / "M5_sub" / "Light_a.fit").write_text("x")
    from m110.ui.ingest_dialog import IngestDialog
    dlg = IngestDialog()
    qtbot.addWidget(dlg)
    dlg.reject()                          # close immediately — must cancel+wait, not crash
    assert dlg._worker is None
