"""Offscreen smoke for the pages + shared dialogs: they construct, reload against
a seeded temp root, and emit open_object on row/card activation. Store/builder
helpers come from tests/_helpers.py; qtbot/qapp come from pytest-qt."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

from m110 import config  # noqa: E402
from tests._helpers import add_library, seed_capture, seed_root, seed_sandbox  # noqa: E402


def test_sessions_page_lists_and_links(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
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


def test_goals_page_lists_progress_and_links(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)       # m31 captured (shallow)
    from m110 import goals
    goals.create_custom_goal("My List", ["m31", "m51"])
    from m110.ui.pages.goals import GoalsPage
    from PySide6.QtWidgets import QTableWidget
    page = GoalsPage()
    try:
        # default Messier + the new custom goal each get a checkbox
        assert page._checks["messier"].isChecked()
        assert "my-list" in page._checks and page._checks["my-list"].isChecked()
        # progress tables render; the captured-but-shallow m31 is clickable through
        tables = page._content.findChildren(QTableWidget)
        assert tables
        got = []
        page.open_object.connect(got.append)
        for tbl in tables:
            for r in range(tbl.rowCount()):
                it = tbl.item(r, 0)
                if it and it.data(Qt.UserRole) == slug:
                    tbl.itemDoubleClicked.emit(it)
                    break
        assert got and got[0] == slug
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_goals_page_toggle_emits_dirty(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    from m110 import goals
    from m110.ui.pages.goals import GoalsPage
    page = GoalsPage()
    try:
        fired = []
        page.dirty.connect(lambda: fired.append(True))
        # activate Caldwell via its checkbox
        page._checks["caldwell"].setChecked(True)
        assert fired                                   # toggle → dirty (shell refreshes)
        assert "caldwell" in goals.active_goal_ids()
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_catalog_parity_columns_search_and_stat(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
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
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
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
        assert "Object Notes" in labels    # per-object notes section (the journal body)
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


def test_import_dialog_cleanup_default_follows_selection(tmp_path, monkeypatch, qapp, qtbot):
    root = seed_root(tmp_path, monkeypatch)
    seed_sandbox("M51")
    from m110 import siril
    assert siril.has_unimported_output("M51")
    from m110.ui.import_dialog import ImportDialog
    dlg = ImportDialog("M51", "m51")
    try:
        qtbot.waitUntil(dlg._import_btn.isEnabled)  # scan finished
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


def test_import_dialog_self_closes_after_import(tmp_path, monkeypatch, qapp, qtbot):
    root = seed_root(tmp_path, monkeypatch)
    seed_sandbox("M51")
    # auto-confirm the "Confirm import" question box (it would otherwise block)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    from m110.ui.import_dialog import ImportDialog
    dlg = ImportDialog("M51", "m51")
    fired = []
    dlg.imported.connect(fired.append)
    try:
        qtbot.waitUntil(dlg._import_btn.isEnabled)
        dlg._do_import()
        qtbot.waitUntil(lambda: dlg.result() == QDialog.Accepted)  # self-closes
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
    root = seed_root(tmp_path, monkeypatch)
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
    root = seed_root(tmp_path, monkeypatch)
    # 5d: the Library is the user's collection, not the full catalog. The catalog
    # filter narrows the collection to a catalog's members. Seed a mixed collection.
    add_library(root, {
        "m31": {"id": "M31", "name": "Andromeda", "type": "galaxy"},
        "ngc-7000": {"id": "NGC 7000", "name": "North America", "type": "nebula"},
        "ngc-6992": {"id": "NGC 6992", "name": "Veil", "type": "nebula"},
    })
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        all_rows = page.table.rowCount()
        assert all_rows == 3                           # the whole collection
        # select Caldwell in the combo
        idx = next(i for i in range(page._catalog_combo.count())
                   if page._catalog_combo.itemData(i) == "caldwell")
        page._catalog_combo.setCurrentIndex(idx)
        assert page.table.rowCount() == 2              # only Caldwell members in it
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


def test_library_captured_only_filter(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)       # one captured object (m31)
    # plus an uncaptured (e.g. added/annotated) object that the filter should hide
    add_library(root, {"ngc-7000": {"id": "NGC 7000", "name": "NA", "type": "nebula"}})
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        total = page.table.rowCount()
        assert total == 2                               # one captured + one not
        # off (default): everything visible
        assert not any(page.table.isRowHidden(r) for r in range(total))
        # "Captured only" → only rows whose slug is in totals remain visible
        page._captured_chk.setChecked(True)
        visible = [r for r in range(total) if not page.table.isRowHidden(r)]
        assert visible and all(
            page.table.item(r, 0).data(Qt.UserRole) in page._totals for r in visible)
        assert slug in {page.table.item(r, 0).data(Qt.UserRole) for r in visible}
        # composes with search: a non-matching query hides even the captured row
        page._search.setText("zzz-nomatch")
        assert all(page.table.isRowHidden(r) for r in range(total))
        page._search.clear()
        # back off → all visible again
        page._captured_chk.setChecked(False)
        assert not any(page.table.isRowHidden(r) for r in range(total))
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_fill_missing_metadata(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    # Inject a stale stub like the live C33 (name/type/season all missing).
    with (root / config.INTERNAL_DIRNAME / "library.toml").open("a") as f:
        f.write('\n[catalog.ngc-6992]\nid = "NGC 6992"\nname = ""\ntype = "unknown"\n'
                'ra_deg = 314.0792\ndec_deg = 31.7433\n')
    from m110 import catalog
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        # Engine path the right-click action calls.
        filled = catalog.fill_missing_metadata("ngc-6992")
        assert filled.get("name") == "East Veil Nebula" and filled.get("season")
        page.reload()
        # the row now reflects the filled name
        page._search.setText("Veil")
        vis = [r for r in range(page.table.rowCount()) if not page.table.isRowHidden(r)]
        assert any(page.table.item(r, 1).text() == "East Veil Nebula" for r in vis)
        # the page exposes the context-menu hook
        assert hasattr(page, "_on_context_menu")
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_main_window_library_menu(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.main import MainWindow
    w = MainWindow()
    try:
        # Library menu carries Refresh + Add object + Fill + Enrich online
        labels = [a.text() for a in w.lib_menu.actions()]
        assert "Refresh" in labels
        assert any("Add object" in t for t in labels)
        assert any("Fill missing metadata" in t for t in labels)
        assert any("Enrich online" in t for t in labels)
    finally:
        w.close()
        qapp.processEvents()


def test_add_object_dialog_resolves_and_adds(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110 import catalog
    from m110.ui.add_object_dialog import AddObjectDialog
    dlg = AddObjectDialog()
    try:
        dlg._ident.setText("NGC 7000")        # in the bundled reference (Caldwell C20)
        dlg._resolve_offline()
        assert dlg._slug == "ngc-7000"
        assert dlg._edits["name"].text() == "North America Nebula"
        assert dlg._add_btn.isEnabled()
        got = []
        dlg.added.connect(got.append)
        dlg._do_add()
        assert got == ["ngc-7000"]
        assert "ngc-7000" in catalog.load_library()
    finally:
        dlg.deleteLater()
        qapp.processEvents()


def test_object_notes_edit_wraps_and_signals_reload(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from PySide6.QtWidgets import QPlainTextEdit
    from m110 import objects
    from m110.ui.detail import DetailPane
    from m110 import catalog, derived
    d = DetailPane()
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        d._enter_edit()
        # Bug #2: editor wraps to width (no horizontal scrollbar).
        assert d._editor.lineWrapMode() == QPlainTextEdit.WidgetWidth
        # Bug #1: saving emits `saved(slug)` so the shell can reload other views.
        d._editor.setPlainText("# notes\n\nGot 4h last night.\n")
        got = []
        d.saved.connect(got.append)
        d._save_edit()
        assert got == [slug]
        assert "4h last night" in objects.read_journal_text(slug)
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_catalog_page_reemits_notes_saved(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        got = []
        page.notes_saved.connect(got.append)
        page.detail.saved.emit("m31")        # detail → catalog re-emit
        assert got == ["m31"]
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_catalog_page_has_online_enrich_hook(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        assert hasattr(page, "_enrich_one_online")
        assert page._enrich_worker is None
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
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
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
