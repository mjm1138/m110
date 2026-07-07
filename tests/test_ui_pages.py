"""Offscreen smoke for the pages + shared dialogs: they construct, reload against
a seeded temp root, and emit open_object on row/card activation. Store/builder
helpers come from tests/_helpers.py; qtbot/qapp come from pytest-qt."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

from m110 import config  # noqa: E402
from m110.ui.image_grid import KEY_ROLE, MUTED_ROLE  # noqa: E402
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


def test_goals_page_catalog_table_marks_captured_and_deep(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)       # m31 captured (shallow → not deep)
    from m110.ui.pages.goals import GoalsPage
    from PySide6.QtWidgets import QTableWidget
    page = GoalsPage()
    try:
        # find the row for the captured object across the per-catalog tables
        row = None
        for tbl in page._content.findChildren(QTableWidget):
            hdr = [tbl.horizontalHeaderItem(c).text() for c in range(tbl.columnCount())]
            if hdr[:4] != ["Object", "Name", "Captured", "Deep stack"]:
                continue
            for r in range(tbl.rowCount()):
                it = tbl.item(r, 0)
                if it and it.data(Qt.UserRole) == slug:
                    row = (tbl.item(r, 2).text(), tbl.item(r, 3).text())
                    break
            if row:
                break
        assert row == ("✓", ""), row     # captured checked, deep-stack unchecked
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


def _viewer_png(path, size=(200, 100), color=(40, 80, 160)):
    pytest.importorskip("PIL")
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def test_image_viewer_accepts_dict_items(qapp):
    from m110.ui.image_viewer import ImageViewer
    v = ImageViewer([{"name": "a", "path": "/no/such/file.png",
                       "meta": {"Filter": "LP"}}], 0)
    try:
        v.show()
        assert v.isVisible()
        assert v._info_btn is not None            # meta present → toggle built
    finally:
        v.deleteLater()
        qapp.processEvents()


def test_image_viewer_tuple_items_no_info_toggle(qapp):
    from m110.ui.image_viewer import ImageViewer
    v = ImageViewer([("a", "/no/such/file.png")], 0)
    try:
        assert v._info_btn is None                 # no meta → no toggle
    finally:
        v.deleteLater()
        qapp.processEvents()


def test_image_viewer_zoom_fit_vs_100_percent_differ(tmp_path, qapp):
    from m110.ui.image_viewer import ImageViewer
    p = tmp_path / "a.png"
    _viewer_png(p, size=(2000, 1000))
    v = ImageViewer([("a", str(p))], 0)
    try:
        v.resize(400, 300)
        qapp.processEvents()
        assert v._image.is_fit()
        fit_zoom = v._image.current_zoom()
        v._image.set_zoom(1.0)
        assert not v._image.is_fit()
        assert v._image.current_zoom() == pytest.approx(1.0)
        assert fit_zoom != pytest.approx(1.0)       # 2000px source, ~400px viewport
    finally:
        v.deleteLater()
        qapp.processEvents()


def test_image_viewer_zoom_in_out_move_monotonically(tmp_path, qapp):
    from m110.ui.image_viewer import ImageViewer
    p = tmp_path / "a.png"
    _viewer_png(p, size=(400, 300))
    v = ImageViewer([("a", str(p))], 0)
    try:
        v._image.set_zoom(1.0)
        base = v._image.current_zoom()
        v._image.zoom_in()
        assert v._image.current_zoom() > base
        v._image.zoom_out()
        v._image.zoom_out()
        assert v._image.current_zoom() < base
    finally:
        v.deleteLater()
        qapp.processEvents()


def test_image_viewer_fit_resets_on_navigate(tmp_path, qapp):
    from m110.ui.image_viewer import ImageViewer
    p1, p2 = tmp_path / "a.png", tmp_path / "b.png"
    _viewer_png(p1, size=(400, 300))
    _viewer_png(p2, size=(400, 300))
    v = ImageViewer([("a", str(p1)), ("b", str(p2))], 0)
    try:
        v._image.set_zoom(2.0)
        assert not v._image.is_fit()
        v.next()
        assert v._image.is_fit()                   # smoother transitions: no carried-over zoom
    finally:
        v.deleteLater()
        qapp.processEvents()


def test_image_viewer_keyboard_shortcuts(tmp_path, qapp):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from m110.ui.image_viewer import ImageViewer
    p1, p2 = tmp_path / "a.png", tmp_path / "b.png"
    _viewer_png(p1, size=(400, 300))
    _viewer_png(p2, size=(400, 300))
    v = ImageViewer([{"name": "a", "path": str(p1), "meta": {"Filter": "LP"}},
                      {"name": "b", "path": str(p2), "meta": {}}], 0)
    try:
        def press(key):
            v.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))

        press(Qt.Key_End)
        assert v._i == 1
        press(Qt.Key_Home)
        assert v._i == 0
        press(Qt.Key_1)
        assert v._image.current_zoom() == pytest.approx(1.0)
        press(Qt.Key_0)
        assert v._image.is_fit()
        press(Qt.Key_Plus)
        assert not v._image.is_fit()
        assert v._info_btn is not None and not v._info_btn.isChecked()
        press(Qt.Key_I)
        assert v._info_btn.isChecked()
    finally:
        v.deleteLater()
        qapp.processEvents()


def test_image_viewer_arrow_keys_navigate_via_real_focus(tmp_path, qapp, qtbot):
    # Regression: calling keyPressEvent() directly (as above) always exercises
    # the handler regardless of focus — it can't catch a widget upstream (the
    # ZoomableImage scroll area) intercepting the key before ImageViewer ever
    # sees it. Route a real Qt key event through qtbot instead, honoring focus.
    from m110.ui.image_viewer import ImageViewer
    p1, p2 = tmp_path / "a.png", tmp_path / "b.png"
    _viewer_png(p1, size=(400, 300))
    _viewer_png(p2, size=(400, 300))
    v = ImageViewer([("a", str(p1)), ("b", str(p2))], 0)
    qtbot.addWidget(v)
    try:
        v.show()
        qapp.processEvents()
        qtbot.keyClick(v, Qt.Key_Right)
        assert v._i == 1
        qtbot.keyClick(v, Qt.Key_Left)
        assert v._i == 0
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


def test_library_detail_hidden_until_selection_then_closable(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, {"m31": {"id": "M31", "name": "Andromeda", "type": "galaxy"}})
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        assert page.detail.isHidden()                  # nothing selected on first nav

        page.table.selectRow(0)
        assert not page.detail.isHidden()
        close_btn = page.detail._close_btn
        assert close_btn is not None

        close_btn.click()
        assert page.detail.isHidden()                   # ✕ dismisses back to full width
        assert not page.table.selectedItems()           # and clears the selection
    finally:
        page.deleteLater()
        qapp.processEvents()


# ── Library grid view (UI_ROADMAP Phase 3) ───────────────────────────────────

def test_library_grid_model_matches_filtered_table(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)       # one captured object
    add_library(root, {"ngc-7000": {"id": "NGC 7000", "name": "NA", "type": "nebula"}})
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        def visible_rows():
            return sum(1 for r in range(page.table.rowCount())
                       if not page.table.isRowHidden(r))

        assert page._grid_model.rowCount() == visible_rows() == 2
        page._search.setText("ngc 7000")       # search filters both views alike
        assert page._grid_model.rowCount() == visible_rows() == 1
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_view_toggle_preserves_selection(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page.table.selectRow(0)
        assert not page.detail.isHidden()

        page._grid_btn.setChecked(True)               # toggle to grid
        assert page._view_mode == "grid"
        sel = page.grid_view.selectionModel().selectedIndexes()
        assert sel and sel[0].data(KEY_ROLE) == slug
        assert not page.detail.isHidden()              # no hide/show flash

        page._grid_btn.setChecked(False)               # toggle back
        assert page._view_mode == "list"
        row = page.table.selectedItems()[0].row()
        assert page.table.item(row, 0).data(Qt.UserRole) == slug
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_grid_search_preserves_selection_when_still_matching(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page._grid_btn.setChecked(True)
        page._select_slug(slug)
        assert not page.detail.isHidden()

        page._search.setText(tid.lower())               # still matches this object
        sel = page.grid_view.selectionModel().selectedIndexes()
        assert sel and sel[0].data(KEY_ROLE) == slug
        assert not page.detail.isHidden()

        page._search.setText("zzz-nomatch")
        assert not page.grid_view.selectionModel().selectedIndexes()
        assert page.detail.isHidden()
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_grid_click_routes_to_detail_pane(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page._grid_btn.setChecked(True)
        idx = page._grid_model.index_of(slug)
        assert idx.isValid()
        page.grid_view.selectionModel().select(
            idx, page.grid_view.selectionModel().SelectionFlag.ClearAndSelect)
        assert not page.detail.isHidden()
        assert page.detail._current[0] == slug
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_grid_zoom_changes_tile_size_and_persists(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page._zoom_slider.setValue(200)
        assert page._grid_delegate._tile_size == 200
        page._zoom_slider.sliderReleased.emit()
        assert config.get_setting("library_grid_zoom") == 200
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_grid_uncaptured_tile_renders_without_crash(tmp_path, monkeypatch, qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QStyleOptionViewItem
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, {"ngc-7000": {"id": "NGC 7000", "name": "NA", "type": "nebula"}})
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page._grid_btn.setChecked(True)
        assert page._grid_model.rowCount() == 1
        idx = page._grid_model.index(0)
        assert page._grid_model.data(idx, MUTED_ROLE) is True
        assert page._grid_model.data(idx, Qt.DecorationRole) is None

        pm = QPixmap(200, 200)
        p = QPainter(pm)
        opt = QStyleOptionViewItem()
        opt.rect = QRect(0, 0, 150, 190)
        opt.widget = page.grid_view
        page._grid_delegate.paint(p, opt, idx)          # must not raise
        p.end()
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_grid_context_menu_resolves_same_slug_as_table(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page._grid_btn.setChecked(True)
        page.grid_view.resize(400, 400)                 # force layout offscreen
        idx = page._grid_model.index_of(slug)
        rect = page.grid_view.visualRect(idx)
        assert rect.isValid()
        assert page._slug_at(rect.center()) == slug
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_select_object_works_in_grid_mode(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page._grid_btn.setChecked(True)
        page.select_object(slug)
        assert not page.detail.isHidden()
        sel = page.grid_view.selectionModel().selectedIndexes()
        assert sel and sel[0].data(KEY_ROLE) == slug
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
    w._ready = False    # neuter the deferred launch-refresh worker (else it can run
                        # after monkeypatch unwinds → writes the LIVE store)
    try:
        # Library menu carries Refresh + Add object + Fill + Enrich online
        labels = [a.text() for a in w.lib_menu.actions()]
        assert "Refresh" in labels
        assert any("Add object" in t for t in labels)
        assert any("Fill missing metadata" in t for t in labels)
        assert any("Enrich online" in t for t in labels)
        assert any("Back up" in t for t in labels)
        assert any("Restore" in t for t in labels)
    finally:
        w.close()
        qapp.processEvents()


def test_backup_dialog_constructs_and_shows_snapshot_status(tmp_path, monkeypatch, qapp):
    from m110 import backup
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))

    from m110.ui.backup_dialog import BackupDialog
    dlg = BackupDialog()
    try:
        dlg._dest.setText(str(dest))          # triggers _refresh_status
        qapp.processEvents()
        assert "backup" in dlg._status.text()
    finally:
        dlg.deleteLater()
        qapp.processEvents()


def test_backup_dialog_save_persists_settings_without_backup(tmp_path, monkeypatch, qapp):
    from m110 import backup, config
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    dest.mkdir()

    from m110.ui.backup_dialog import BackupDialog
    dlg = BackupDialog()
    try:
        dlg._dest.setText(str(dest))
        dlg._auto.setChecked(True)
        dlg._interval.setValue(6)
        dlg._save_and_close()                     # Save, not "Back up now"
        qapp.processEvents()
        # Settings persisted…
        assert config.get_setting(backup.SETTING_AUTO) is True
        assert int(config.get_setting(backup.SETTING_INTERVAL)) == 6
        assert config.get_setting(backup.SETTING_DEST) == str(dest)
        # …but no snapshot was written.
        assert backup.list_snapshots(dest) == []
    finally:
        dlg.deleteLater()
        qapp.processEvents()


def test_restore_dialog_lists_snapshot_and_selects(tmp_path, monkeypatch, qapp):
    from PySide6.QtCore import Qt
    from m110 import backup
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))

    from m110.ui.restore_dialog import RestoreDialog
    dlg = RestoreDialog(str(dest))
    try:
        assert dlg._snap_combo.count() == 1
        assert dlg._tree.topLevelItemCount() >= 1     # Objects/Images/… nodes
        assert dlg._restore_btn.isEnabled()
        # check every file node → selection resolves to real relpaths
        def check_all(node):
            for i in range(node.childCount()):
                c = node.child(i)
                c.setCheckState(0, Qt.Checked)
                check_all(c)
        check_all(dlg._tree.invisibleRootItem())
        light_rel = f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"
        assert light_rel in dlg._selected_relpaths()
    finally:
        dlg.deleteLater()
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


def test_catalog_status_color_follows_theme(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)                        # m31 captured → status cell colored
    from m110.ui import theme
    from m110.ui.pages.catalog import CatalogPage
    mgr = theme.install(qapp)
    page = CatalogPage()
    try:
        sc = page.HEADERS.index("Status")

        def status_cell_color():
            for r in range(page.table.rowCount()):
                it = page.table.item(r, sc)
                if it and it.text() not in ("—", ""):
                    return it.foreground().color().name()
            return None

        mgr.set_mode("dark")
        page.restyle()                        # repaint programmatic colors
        dark = status_cell_color()
        mgr.set_mode("light")
        page.restyle()
        light = status_cell_color()
        assert dark and light and dark != light
    finally:
        page.deleteLater()
        qapp.processEvents()


# ── manual Pin / Mute priorities (#3) ─────────────────────────────────────────

def test_summary_empty_priority_state(tmp_path, monkeypatch, qapp):
    """A store with captures but no priorities/pins shows a guiding priority
    empty-state (not an empty table). (An all-empty store shows the welcome card
    instead — covered separately.)"""
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)                       # a capture → dashboard (not welcome) renders
    from PySide6.QtWidgets import QLabel
    from m110.ui.pages.summary import SummaryPage
    page = SummaryPage()
    try:
        caps = [w.text() for w in page._content.findChildren(QLabel)]
        assert any("Pin an object" in t for t in caps)
        assert page._priority_rows([]) == []
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_summary_surfaces_pinned_object(tmp_path, monkeypatch, qapp):
    """A pinned Library object appears in the Priority-targets rows (with a ▲ mark)
    and a muted one is excluded."""
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110 import pins
    pins.set_state(slug, pins.PIN)
    from m110.ui.pages.summary import SummaryPage
    page = SummaryPage()
    try:
        rows = page._priority_rows([])
        assert any(r["slug"] == slug and r["label"].startswith("▲") for r in rows)
        # muting it drops it back out
        pins.set_state(slug, pins.MUTE)
        assert all(r["slug"] != slug for r in page._priority_rows([]))
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_catalog_set_pin_marks_and_emits(tmp_path, monkeypatch, qapp):
    """_set_pin persists the override, marks the Library row, and emits pins_changed."""
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110 import pins
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        fired = []
        page.pins_changed.connect(lambda: fired.append(True))
        page._set_pin(slug, pins.PIN)
        assert pins.get_state(slug) == "pin"
        assert fired
        # the list-view Object cell now carries the ▲ marker
        marked = [page.table.item(r, 0).text()
                  for r in range(page.table.rowCount())
                  if page.table.item(r, 0).data(Qt.UserRole) == slug]
        assert marked and marked[0].startswith("▲")
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_goals_member_pin_emits(tmp_path, monkeypatch, qapp):
    """The Goals membership context-menu action persists a pin + emits pins_changed."""
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110 import pins
    from m110.ui.pages.goals import GoalsPage
    from PySide6.QtWidgets import QTableWidget
    page = GoalsPage()
    try:
        fired = []
        page.pins_changed.connect(lambda: fired.append(True))
        pins.set_state(slug, pins.PIN)         # engine path used by the menu action
        page.pins_changed.emit()
        assert pins.get_state(slug) == "pin" and fired
        page.reload()
        # the member row shows the ▲ marker after reload
        marked = False
        for tbl in page._content.findChildren(QTableWidget):
            for r in range(tbl.rowCount()):
                it = tbl.item(r, 0)
                if it and it.data(Qt.UserRole) == slug and it.text().startswith("▲"):
                    marked = True
        assert marked
    finally:
        page.deleteLater()
        qapp.processEvents()


# ── onboarding / first-run (#onboarding) ──────────────────────────────────────

def test_first_run_dialog_accept_persists_and_bootstraps(tmp_path, monkeypatch, qapp):
    """FirstRunDialog → Accept saves the data-folder preference and creates the store."""
    monkeypatch.delenv("M110_DATA_ROOT", raising=False)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "DEFAULT_DATA_ROOT", tmp_path / "default")
    chosen = tmp_path / "chosen-store"
    from m110.ui.first_run_dialog import FirstRunDialog
    dlg = FirstRunDialog()
    try:
        dlg._edit.setText(str(chosen))
        dlg._accept()                       # simulate "Get started"
        from m110.ui.first_run_dialog import run_first_run_if_needed  # noqa: F401
        # emulate the accepted branch of run_first_run_if_needed
        config.save_data_root(chosen)
        config.set_data_root(chosen)
        config.ensure_data_root(chosen)
        assert config.get_setting("data_root") == str(chosen)
        assert (chosen / config.INTERNAL_DIRNAME / "library.toml").is_file()
        assert config.is_first_run() is False   # won't re-prompt
    finally:
        dlg.deleteLater()
        qapp.processEvents()


def test_summary_empty_store_shows_welcome_cta(tmp_path, monkeypatch, qapp):
    """A fresh store shows the welcome card; its Import button fires go_to_import."""
    seed_root(tmp_path, monkeypatch)        # bootstrapped but nothing captured
    from PySide6.QtWidgets import QLabel, QPushButton
    from m110.ui.pages.summary import SummaryPage
    page = SummaryPage()
    try:
        labels = " ".join(w.text() for w in page._content.findChildren(QLabel))
        assert "Welcome to M110" in labels
        btn = next(b for b in page._content.findChildren(QPushButton)
                   if b.text() == "Import images…")
        fired = []
        page.go_to_import.connect(lambda: fired.append(True))
        btn.click()
        assert fired
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_summary_seeded_store_shows_dashboard_not_welcome(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)                      # now there's a capture
    from PySide6.QtWidgets import QLabel
    from m110.ui.pages.summary import SummaryPage
    page = SummaryPage()
    try:
        labels = " ".join(w.text() for w in page._content.findChildren(QLabel))
        assert "Welcome to M110" not in labels
        assert "Progress by category" in labels
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_empty_state_hint(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)        # Library starts empty (5d)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        assert "Library is empty" in page._stat.text()
    finally:
        page.deleteLater()
        qapp.processEvents()
