"""Offscreen smoke for the Phase-2 pages (Sessions + Journal): they construct,
reload against a seeded temp root, and emit open_object on row/card activation."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tomllib

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from m110 import config, refresh  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _wait(cond, qapp, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end and not cond():
        qapp.processEvents()
        time.sleep(0.01)
    return cond()


def _seed_root(tmp_path, monkeypatch):
    root = tmp_path / "M110"
    internal = root / config.INTERNAL_DIRNAME
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "LIBRARY_TOML", internal / "library.toml")
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "DERIVED_DIR", internal / "derived")
    monkeypatch.setattr(config, "RENDERS_DIR", internal / "renders")
    monkeypatch.setattr(config, "HERO_DIR", internal / "renders" / "hero")
    monkeypatch.setattr(config, "SESSIONS_JSONL", internal / "sessions.jsonl")
    monkeypatch.setattr(config, "MEDIA_DIR", root / "Media")
    monkeypatch.setattr(config, "STAGING_DIR", root / "Inbox")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.ensure_data_root(root)
    return root


def _first_object(root):
    with (root / config.INTERNAL_DIRNAME / "library.toml").open("rb") as f:
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


def test_catalog_parity_columns_search_and_stat(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    slug, tid = _seed_capture(root, monkeypatch)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        headers = [page.table.horizontalHeaderItem(c).text()
                   for c in range(page.table.columnCount())]
        assert "Size" in headers and "Filter" in headers
        # stat row reflects captured/total
        assert "captured" in page._stat.text() and "total" in page._stat.text()
        # search hides non-matching rows
        page._search.setText("zzz-nomatch")
        assert all(page.table.isRowHidden(r) for r in range(page.table.rowCount()))
        page._search.clear()
        assert not all(page.table.isRowHidden(r) for r in range(page.table.rowCount()))
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_detail_enrichment_sections(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    slug, tid = _seed_capture(root, monkeypatch)
    from m110.ui.detail import DetailPane
    from m110 import catalog, derived
    d = DetailPane()
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        qapp.processEvents()
        from PySide6.QtWidgets import QLabel
        labels = " | ".join(l.text() for l in d._content.findChildren(QLabel))
        assert "Processing" in labels      # per-object processing section
        assert "Sessions" in labels        # per-object sessions section
        assert "Object details" in labels  # metadata block
        assert slug in labels              # metadata shows the slug
        # comprehensive details incl. RA/Dec (decimal + sexagesimal) when coords known
        assert "Type" in labels and "Magnitude" in labels
        if catalog.load_coords().get(slug):
            assert "RA" in labels and "Dec" in labels and "h" in labels  # HMS form
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_radec_formatters():
    from m110.ui.detail import _ra_hms, _dec_dms
    assert _ra_hms(202.4696).startswith("13h29m")
    assert _ra_hms(0.0) == "00h00m00.0s"
    assert _dec_dms(47.1952).startswith("+47°11")
    assert _dec_dms(-12.5) == "-12°30′00″"


def _seed_sandbox(target="M51"):
    """A siril sandbox with two unimported deliverables (render + stack)."""
    sb = config.siril_dir(target)
    sb.mkdir(parents=True, exist_ok=True)
    (sb / f"{target}_x_processed.png").write_text("png")
    (sb / f"{target}_x_processed.fit").write_text("fit")
    return sb


def test_import_dialog_cleanup_default_follows_selection(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    _seed_sandbox("M51")
    from m110 import siril
    assert siril.has_unimported_output("M51")
    from m110.ui.import_dialog import ImportDialog
    dlg = ImportDialog("M51", "m51")
    try:
        assert _wait(lambda: dlg._import_btn.isEnabled(), qapp), "scan never finished"
        assert dlg._cleanup.currentData() == "archive"      # all checked → archive
        dlg.table.item(0, 0).setCheckState(Qt.Unchecked)     # leave one behind
        qapp.processEvents()
        assert dlg._cleanup.currentData() == "none"          # → leave as-is
        dlg.table.item(0, 0).setCheckState(Qt.Checked)
        qapp.processEvents()
        assert dlg._cleanup.currentData() == "archive"       # back to archive
        # once the user picks cleanup, selection no longer steers it
        dlg._cleanup_user_set = True
        dlg.table.item(0, 0).setCheckState(Qt.Unchecked)
        qapp.processEvents()
        assert dlg._cleanup.currentData() == "archive"
    finally:
        dlg.reject()
        dlg.deleteLater()
        qapp.processEvents()


def test_import_dialog_self_closes_after_import(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    _seed_sandbox("M51")
    # auto-confirm the "Confirm import" question box (it would otherwise block)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    from m110.ui.import_dialog import ImportDialog
    dlg = ImportDialog("M51", "m51")
    fired = []
    dlg.imported.connect(fired.append)
    try:
        assert _wait(lambda: dlg._import_btn.isEnabled(), qapp)
        dlg._do_import()
        assert _wait(lambda: dlg.result() == QDialog.Accepted, qapp), "did not self-close"
        assert fired == ["M51"]                              # main window got notified
        assert (config.finished_dir("M51") / "M51_x_processed.png").is_file()
    finally:
        dlg.deleteLater()
        qapp.processEvents()


def test_image_viewer_close_and_quit_shortcuts(qapp):
    from PySide6.QtGui import QShortcut, QKeySequence
    from m110.ui.image_viewer import ImageViewer
    v = ImageViewer([("a", "/no/such/file.png")], 0)
    try:
        keys = {sc.key() for sc in v.findChildren(QShortcut)}
        assert QKeySequence(QKeySequence.StandardKey.Close) in keys   # Cmd/Ctrl+W
        assert QKeySequence(QKeySequence.StandardKey.Quit) in keys     # Cmd/Ctrl+Q
        v.show()
        assert v.isVisible()
        v.close()                                   # the Close shortcut path
        qapp.processEvents()
        assert not v.isVisible()
    finally:
        v.deleteLater()
        qapp.processEvents()


def test_media_page_sections_and_empty(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    from m110.ui.pages.media import MediaPage
    page = MediaPage()
    try:
        assert page.section_count() == 0          # seeded root has no media yet
        (config.MEDIA_DIR / "Moon_photo").mkdir(parents=True)
        (config.MEDIA_DIR / "Moon_photo" / "a.png").write_text("x")
        page.reload()
        assert page.section_count() == 1
        assert page._galleries and page._galleries[0][0].count() == 1   # one photo
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_catalog_filter_and_identifiers(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    from m110 import catalog, goals
    goals.set_active_goals(["messier", "caldwell"])   # bring Caldwell into the Library
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        all_rows = page.table.rowCount()
        assert all_rows >= 200                         # Messier + Caldwell
        # select Caldwell in the combo
        idx = next(i for i in range(page._catalog_combo.count())
                   if page._catalog_combo.itemData(i) == "caldwell")
        page._catalog_combo.setCurrentIndex(idx)
        assert page.table.rowCount() == 109            # only Caldwell members
        # Object cells read by C-number, with the NGC id in parens
        cells = [page.table.item(r, 0).text() for r in range(page.table.rowCount())]
        joined = " ".join(cells)
        assert "C20 (NGC 7000)" in joined
        assert all(c.startswith("C") for c in cells)   # Caldwell designation primary
        assert "Caldwell —" in page._stat.text()
        # back to all
        page._catalog_combo.setCurrentIndex(0)
        assert page.table.rowCount() == all_rows
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_body_markdown_excludes_stub():
    """A fresh stub (heading + comment only) is not 'real notes'; edited prose is."""
    from m110.ui.pages.journal import _body_markdown
    stub = "# M51 — Whirlpool Galaxy\n\n<!--\nnotes go here\n-->\n"
    assert _body_markdown(stub) is None
    assert _body_markdown(stub + "\nGot 4h last night.\n")  # truthy


def test_journal_page_card_per_captured_object(tmp_path, monkeypatch, qapp):
    root = _seed_root(tmp_path, monkeypatch)
    slug, tid = _seed_capture(root, monkeypatch)
    from m110.ui.pages.journal import JournalPage
    page = JournalPage()
    try:
        # Only the captured object shows — uncaptured objects have stub-only
        # journals (no notes, no images) and must be excluded.
        assert page.card_count() == 1
        got = []
        page.open_object.connect(got.append)
        from PySide6.QtWidgets import QPushButton
        card, _ = page._cards[0]
        card.findChild(QPushButton).click()
        assert got == [slug]
    finally:
        page.deleteLater()
        qapp.processEvents()
