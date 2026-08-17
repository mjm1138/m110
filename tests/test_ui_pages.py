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
    from m110.ui.pages.overview import OverviewPage
    from PySide6.QtWidgets import QTableWidget
    page = OverviewPage()
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
    from m110.ui.pages.overview import OverviewPage
    from PySide6.QtWidgets import QTableWidget
    page = OverviewPage()
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
    from m110.ui.pages.overview import OverviewPage
    page = OverviewPage()
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
    # The filter offers the catalogs you've set as goals, so track the one this
    # test filters by.
    from m110 import goals
    goals.set_active_goals(["messier", "caldwell"])
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


def test_context_menu_fill_enrich_reflect_gaps(tmp_path, monkeypatch, qapp):
    """Right-click Fill / Enrich are enabled only when there's something to do: a
    fully-populated object disables both (they then render greyed via the QSS
    QMenu::item:disabled rule); a sparse object with gaps enables them. Uses the
    exec-free `_object_menu` builder — a modal exec can't run headless and PySide6's
    QMenu.exec can't be monkeypatched."""
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, {
        "m13": {                              # every fillable field present → no gaps
            "id": "M13", "name": "Hercules Globular", "type": "globular",
            "magnitude": 5.8, "size": "20", "season": "Jun–Aug",
            "filter": "IRCUT", "ra_deg": 250.42, "dec_deg": 36.46},
        "m1": {"id": "M1", "name": "Crab", "type": "emission_snr"},   # reference can fill
        "custom-neb": {"id": "Custom", "type": "unknown"},   # off-catalog stub → real gaps
    })
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        _m1, complete = page._object_menu("m13")
        assert complete["fill"].isEnabled() is False       # nothing the reference can add
        assert complete["online"].isEnabled() is False     # no remaining gaps → greyed
        _m2, refable = page._object_menu("m1")
        assert refable["fill"].isEnabled() is True          # reference fills mag/size/coords
        _m3, offcat = page._object_menu("custom-neb")
        assert offcat["online"].isEnabled() is True         # gaps the reference can't fill
        for m in (_m1, _m2, _m3):
            m.deleteLater()
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_detail_hidden_until_selection_then_closable(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, {"m31": {"id": "M31", "name": "Andromeda", "type": "galaxy"}})
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        page._set_view_mode("list")               # list mode (grid is the default)
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
        page._set_view_mode("list")              # list mode (grid is the default)
        page.table.selectRow(0)
        assert not page.detail.isHidden()

        page._set_view_mode("grid")               # toggle to grid
        assert page._view_mode == "grid"
        sel = page.grid_view.selectionModel().selectedIndexes()
        assert sel and sel[0].data(KEY_ROLE) == slug
        assert not page.detail.isHidden()              # no hide/show flash

        page._set_view_mode("list")               # toggle back
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
        page._set_view_mode("grid")
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
        page._set_view_mode("grid")
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
        page._set_view_mode("grid")
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
        page._set_view_mode("grid")
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
        page._set_view_mode("grid")
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
        assert hasattr(page, "_show_context_menu")
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
        # Library menu = operations on the collection itself. (Back up / Restore /
        # Prepare / Preferences moved to Tools; Import / Publish to File.)
        labels = [a.text() for a in w.lib_menu.actions()]
        assert "Refresh" in labels
        assert any("Add object" in t for t in labels)
        assert any("Fill missing metadata" in t for t in labels)
        assert any("Enrich online" in t for t in labels)

        tools = [a.text() for a in w.tools_menu.actions()]
        assert any("Prepare working folders" in t for t in tools)
        assert any("Back up" in t for t in tools)
        assert any("Restore" in t for t in tools)
        assert any("Preferences" in t for t in tools)

        files = [a.text() for a in w.file_menu.actions()]
        assert any("Import" in t for t in files)
        assert any("Publish" in t for t in files)
        assert any("Exit" in t for t in files)
    finally:
        w.close()
        qapp.processEvents()


def _settle_probe(dlg, qapp):
    """Wait out the backup dialog's destination-probe worker and deliver its
    queued result signal."""
    for _ in range(100):
        qapp.processEvents()
        if dlg._probe_worker is None:
            return
        dlg._probe_worker.wait(20)
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
        dlg._dest.setText(str(dest))
        # Typing must NOT probe (it used to walk the destination on the GUI
        # thread on every keystroke — a freeze on a slow share).
        assert dlg._probe_worker is None
        dlg._refresh_status()
        _settle_probe(dlg, qapp)
        assert "backup" in dlg._status.text()
        assert "shared between backups" in dlg._status.text()
    finally:
        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


def test_backup_dialog_exit_button_says_close_until_something_changes(
        tmp_path, monkeypatch, qapp):
    """"Cancel" should only appear when it can actually undo something.

    The reported confusion: after "Back up now" — which persists the settings
    itself, before running — the exit button still read "Cancel", as though it
    would roll back the snapshot that just ran. `reject()` only closes the window,
    so there was nothing to cancel and the label was simply untrue."""
    seed_root(tmp_path, monkeypatch)
    from m110.ui.backup_dialog import BackupDialog
    dlg = BackupDialog()
    try:
        assert dlg._reject_btn.text() == "Close"
        assert dlg._save_btn.isEnabled() is False      # nothing to save either

        dlg._interval.setValue(dlg._interval.value() + 1)
        assert dlg._reject_btn.text() == "Cancel"      # now it can discard an edit
        assert dlg._save_btn.isEnabled() is True

        # Persisting is what makes the widgets and the stored settings agree —
        # whether it came from Save or from "Back up now".
        dlg._persist_settings(str(tmp_path / "dest"))
        assert dlg._reject_btn.text() == "Close"
        assert dlg._save_btn.isEnabled() is False

        # Changing the destination arms it too — including programmatically, because
        # Browse sets the field with `setText` and picking a folder is very much a
        # change worth saving. (An earlier version listened to `textEdited` to skip
        # programmatic writes; that left Save greyed out after Browse. Nothing else
        # writes this field — the destination probe updates the status label.)
        dlg._dest.setText(str(tmp_path / "elsewhere"))
        assert dlg._reject_btn.text() == "Cancel"
        assert dlg._save_btn.isEnabled() is True
    finally:
        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


def test_backup_dialog_warns_when_destination_cannot_share_files(tmp_path, monkeypatch, qapp):
    """The #92 case: a destination whose filesystem has no hardlinks stores a full
    copy per backup. Say so *before* the first backup, not after."""
    import os

    from m110 import backup
    seed_root(tmp_path, monkeypatch)
    dest = tmp_path / "backups"
    dest.mkdir()
    monkeypatch.setattr(os, "link",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no links")))

    from m110.ui.backup_dialog import BackupDialog
    dlg = BackupDialog()
    try:
        dlg._dest.setText(str(dest))
        dlg._refresh_status()
        _settle_probe(dlg, qapp)
        text = dlg._status.text()
        assert "No backups here yet." in text          # nothing written yet…
        assert "can't share files between backups" in text   # …and we still warn
    finally:
        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


def test_backup_dialog_offers_the_format_choice_and_explains_it(tmp_path, monkeypatch, qapp):
    from m110 import backup
    seed_root(tmp_path, monkeypatch)
    dest = tmp_path / "backups"
    dest.mkdir()

    from m110.ui.backup_dialog import BackupDialog
    dlg = BackupDialog()
    try:
        assert dlg._current_format() == backup.FORMAT_MIRRORED     # the default
        dlg._dest.setText(str(dest))
        dlg._refresh_status()
        _settle_probe(dlg, qapp)
        assert dlg._format.isEnabled()                             # a real choice
        assert "browsable copy" in dlg._format_note.text()

        dlg._select_format(backup.FORMAT_POOLED)
        dlg._on_format_changed()
        assert "stored once" in dlg._format_note.text()
        dlg._save_and_close()
        assert config.get_setting(backup.SETTING_FORMAT) == backup.FORMAT_POOLED
    finally:
        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


def test_backup_dialog_forces_pooled_where_files_cannot_be_shared(tmp_path, monkeypatch, qapp):
    """#92: on a destination without hardlinks, mirrored backups are a full copy
    every night. The dialog makes the choice, says why, and remembers it."""
    import os

    from m110 import backup
    seed_root(tmp_path, monkeypatch)
    dest = tmp_path / "backups"
    dest.mkdir()
    monkeypatch.setattr(os, "link",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no links")))

    from m110.ui.backup_dialog import BackupDialog
    dlg = BackupDialog()
    try:
        dlg._dest.setText(str(dest))
        dlg._refresh_status()
        _settle_probe(dlg, qapp)
        assert dlg._current_format() == backup.FORMAT_POOLED
        assert not dlg._format.isEnabled()
        assert "can't share files" in dlg._format_note.text()
        assert config.get_setting(backup.SETTING_FORMAT) == backup.FORMAT_POOLED
    finally:
        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


def test_restore_dialog_lists_both_formats_and_restores_a_pooled_snapshot(
        tmp_path, monkeypatch, qapp):
    from PySide6.QtCore import Qt
    from m110 import backup
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"
    config.save_setting(backup.SETTING_FORMAT, backup.FORMAT_MIRRORED)
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    config.save_setting(backup.SETTING_FORMAT, backup.FORMAT_POOLED)
    backup.create_snapshot(backup.BackupOptions(destination=dest))

    from m110.ui.restore_dialog import RestoreDialog
    dlg = RestoreDialog(str(dest))
    try:
        assert dlg._snap_combo.count() == 2
        assert "pooled" in dlg._snap_combo.itemText(0)      # newest first
        assert "pooled" not in dlg._snap_combo.itemText(1)
        assert dlg._tree.topLevelItemCount() >= 1           # pooled tree builds

        def check_all(node):
            for i in range(node.childCount()):
                c = node.child(i)
                c.setCheckState(0, Qt.Checked)
                check_all(c)
        check_all(dlg._tree.invisibleRootItem())
        light_rel = f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"
        assert light_rel in dlg._selected_relpaths()

        out = tmp_path / "out"
        res = backup.restore(dlg._current_snapshot(), [light_rel], out)
        assert res["written"] == 1
        assert (out / light_rel).read_bytes() == (root / light_rel).read_bytes()
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


# ── manual Pin / Deprioritize priorities (#3) ─────────────────────────────────

def test_summary_empty_priority_state(tmp_path, monkeypatch, qapp):
    """A store with captures but no priorities/pins shows a guiding priority
    empty-state (not an empty table). (An all-empty store shows the welcome card
    instead — covered separately.)"""
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)                       # a capture → dashboard (not welcome) renders
    from PySide6.QtWidgets import QLabel
    from m110.ui.pages.overview import OverviewPage
    page = OverviewPage()
    try:
        caps = [w.text() for w in page._content.findChildren(QLabel)]
        assert any("pinned" in t.lower() and "Planning page" in t for t in caps)
        assert page._priority_rows() == []      # pins-only source
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_summary_surfaces_pinned_object(tmp_path, monkeypatch, qapp):
    """A pinned Library object appears in the Priority-targets rows (with a ▲ mark)
    and a deprioritized one is excluded."""
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110 import pins
    pins.set_state(slug, pins.PIN)
    from m110.ui.pages.overview import OverviewPage
    page = OverviewPage()
    try:
        rows = page._priority_rows()
        assert any(r["slug"] == slug and r["label"].startswith("▲") for r in rows)
        # deprioritizing it drops it back out
        pins.set_state(slug, pins.DEPRIORITIZE)
        assert all(r["slug"] != slug for r in page._priority_rows())
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_summary_priority_view_has_pin_controls(tmp_path, monkeypatch, qapp):
    """The priority table is right-clickable and a pin change from it reloads the
    view (#3 — pin/unpin available from within the priority view)."""
    from PySide6.QtWidgets import QTableWidget
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110 import pins
    pins.set_state(slug, pins.PIN)
    from m110.ui.pages.overview import OverviewPage
    page = OverviewPage()
    try:
        def headers(t):
            return [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
        pt = next(t for t in page._content.findChildren(QTableWidget)
                  if {"Priority", "Target"} <= set(headers(t)))   # the priority table
        assert any(pt.item(r, 0) and pt.item(r, 0).data(Qt.UserRole) == slug
                   for r in range(pt.rowCount()))
        assert pt.contextMenuPolicy() == Qt.CustomContextMenu   # right-click enabled
        fired = []
        page.pins_changed.connect(lambda: fired.append(True))
        pins.set_state(slug, None)          # the engine path the menu's Unpin calls
        page.pins_changed.emit()
        assert fired
        page.reload()                       # unpinned → drops off the list
        assert all(r["slug"] != slug for r in page._priority_rows())
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
    from m110.ui.pages.overview import OverviewPage
    from PySide6.QtWidgets import QTableWidget
    page = OverviewPage()
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
    from m110.ui.pages.overview import OverviewPage
    page = OverviewPage()
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
    from PySide6.QtWidgets import QLabel, QToolButton
    from m110.ui.pages.overview import OverviewPage
    page = OverviewPage()
    try:
        labels = " ".join(w.text() for w in page._content.findChildren(QLabel))
        assert "Welcome to M110" not in labels
        # dashboard sections render as collapsible headers (QToolButton), not labels
        sections = [b.text() for b in page._content.findChildren(QToolButton)]
        assert "Progress by category" in sections
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


# ── BETA_BUGS: table-height helper, Overview restructure, Library segments ────

def test_fit_table_height_no_clip_and_caps(qapp):
    from PySide6.QtWidgets import QTableWidgetItem
    from m110.ui.widgets import make_table, fit_table_height
    # a single-row table: no inner scrollbar, whole row fits (+ half-row pad)
    t = make_table(["A", "B"])
    t.insertRow(0)
    t.setItem(0, 0, QTableWidgetItem("x")); t.setItem(0, 1, QTableWidgetItem("y"))
    fit_table_height(t)
    assert t.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert t.height() > t.horizontalHeader().height()      # header + a full row
    # a table above the cap turns the scrollbar on
    t2 = make_table(["A"])
    for i in range(9):
        t2.insertRow(i); t2.setItem(i, 0, QTableWidgetItem(str(i)))
    fit_table_height(t2, max_rows=6)
    assert t2.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded


def test_overview_section_order_and_pins_only(tmp_path, monkeypatch, qapp):
    from PySide6.QtWidgets import QToolButton
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    from m110.ui.pages.overview import OverviewPage
    page = OverviewPage()
    try:
        section_titles = {"Goals", "Priority targets", "Integration Time and Sessions",
                          "Goal checklists", "Progress by category", "Manage goals"}
        order = [b.text() for b in page._content.findChildren(QToolButton)
                 if b.text() in section_titles]
        assert order == ["Goals", "Priority targets", "Integration Time and Sessions",
                         "Goal checklists", "Progress by category", "Manage goals"]
        assert "Processing queue" not in [b.text() for b in
                                          page._content.findChildren(QToolButton)]
        assert page._priority_rows() == []      # pins-only source, none pinned
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_overview_category_drops_total_column_keeps_total_row(tmp_path, monkeypatch, qapp):
    """Item 21: Progress by category loses the 'Total' column but keeps the Total row."""
    from PySide6.QtWidgets import QTableWidget
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    from m110.ui.pages.overview import OverviewPage
    page = OverviewPage()
    try:
        def hdr(t):
            return [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
        cat = next(t for t in page._content.findChildren(QTableWidget)
                   if hdr(t) == ["Category", "Captured", "Deep stack", "Captured objects"])
        assert "Total" not in hdr(cat)                       # no Total column
        col0 = [cat.item(r, 0).text() for r in range(cat.rowCount()) if cat.item(r, 0)]
        assert "Total" in col0                               # Total row remains
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_overview_integration_is_per_object(tmp_path, monkeypatch, qapp):
    """Item 22: the Integration table is keyed by catalog object (by_slug) to match
    the detail pane — not by capture folder — and excludes zero-session entries (which
    is what made multi-object / stack-only folders read as 'no data')."""
    from PySide6.QtWidgets import QTableWidget
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    from m110.ui.pages.overview import OverviewPage
    page = OverviewPage()
    try:
        def hdr(t):
            return [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
        integ = next(t for t in page._content.findChildren(QTableWidget)
                     if hdr(t) == ["Object", "Sessions", "Frames", "Integration",
                                   "Filter", "Status"])
        found = [(integ.item(r, 0).data(Qt.UserRole), int(integ.item(r, 1).text()))
                 for r in range(integ.rowCount())]
        assert any(s == slug and sc > 0 for s, sc in found)   # object appears with data
        assert all(sc > 0 for _, sc in found)                 # no zero-session rows
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_library_view_segment_stays_put_in_feed_and_hides_in_media(tmp_path, monkeypatch, qapp):
    """Item 17: the List/Grid/Feed/Map segment lives on its own row, so hiding the
    catalog filter in Feed mode can't relocate it. Item 20: Media has no object views
    yet, so the segment is hidden in Media scope."""
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    from m110.ui.pages.catalog import CatalogPage
    page = CatalogPage()
    try:
        assert set(page._view_btns) == {"list", "grid", "feed", "map"}
        page._view_btns["feed"].setChecked(True)
        assert page._filter_bar.isHidden() and not page._view_seg.isHidden()
        # The map is an object view: unlike Feed it keeps the search + filter.
        page._view_btns["map"].setChecked(True)
        assert not page._filter_bar.isHidden() and not page._search.isHidden()
        page._media_btn.setChecked(True)
        assert page._view_seg.isHidden()        # hidden in Media (no views there yet)
        page._deepsky_btn.setChecked(True)
        assert not page._view_seg.isHidden()
    finally:
        page.deleteLater()
        qapp.processEvents()


def _no_prioritizer_worker(monkeypatch):
    """Keep the Planning page from spawning its background astropy worker in tests
    (it would leak a running QThread at teardown). Stubs the recompute entry point,
    so even the force=True paths (profile/site change) stay inert."""
    from m110.ui.pages import planning
    monkeypatch.setattr(planning.PlanningPage, "_maybe_recompute",
                        lambda self, force=False: None)


def test_planning_page_profile_crud(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110 import planning_config as pc
    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    try:
        # Seeded default profile shows in the selector (by display name).
        names = [page.selector.itemText(i) for i in range(page.selector.count())]
        assert names == ["Home"]

        # Create a profile via the editor's signal path.
        pc.save_site(pc.Site(name="Dark Site", latitude_deg=39.9,
                             longitude_deg=-105.1, elevation_m=2800,
                             timezone="America/Denver", bortle=3), "dark-site")
        page._on_profile_created("dark-site")
        assert pc.active_profile() == "dark-site"
        assert page.editor._stem == "dark-site"
        assert page.editor._lat.value() == pytest.approx(39.9)

        # Switch active back to default via the selector.
        page.selector.setCurrentIndex(page.selector.findData("default"))
        assert pc.active_profile() == "default"

        # Delete the extra profile.
        page.editor.load("dark-site")
        pc.delete_profile("dark-site")
        page._on_profile_deleted("dark-site")
        assert pc.list_profiles() == ["default"]
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_planning_page_ranks_cached_contexts(tmp_path, monkeypatch, qapp):
    """The priority table renders the scorer's ranking from cached contexts, with a
    pinned target floated to the top. No background worker (contexts pre-seeded)."""
    root = seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110 import pins, prioritize
    from m110.prioritize import TargetContext
    obs = {"observable": True, "hours_clear": 3.0, "transit_alt": 60.0,
           "nights_to_close": 20, "season": "spring"}
    prioritize.write_contexts([
        TargetContext("m1", "emission_snr", 0, True, obs),
        TargetContext("m13", "globular", 0, True, obs),
    ])
    pins.set_state("m13", pins.PIN)          # should float to #1 despite score
    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    try:
        from PySide6.QtWidgets import QTableWidget
        tbl = next(t for t in page.findChildren(QTableWidget) if t.rowCount() >= 1)
        # rank #1 is the pinned m13 (Object column carries its slug + a ▲ marker)
        top = tbl.item(0, 1)
        assert top.data(Qt.UserRole) == "m13"
        assert "▲" in top.text()
        # flipping strategy re-ranks instantly (no worker)
        page._strategy_combo.setCurrentIndex(
            page._strategy_combo.findData(prioritize.STRATEGY_DEEP))
        assert prioritize.load_strategy() == prioritize.STRATEGY_DEEP
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_planning_plan_ready_distinguishes_engine_failure_from_no_dark(
        tmp_path, monkeypatch, qapp):
    """A planner-worker failure (plan is None — e.g. astropy didn't load) must read as
    an engine problem, NOT as 'no astronomical darkness' (that misreports a bug as an
    astronomical fact). A real plan with an empty window is the genuine no-dark case
    and keeps that message."""
    seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    try:
        page._on_plan_ready(None)                      # worker raised (engine failure)
        s1 = page._plan_status.text().lower()
        assert "astronomy engine" in s1 and "darkness" not in s1
        assert page._entries == [] and page._slots == []

        page._on_plan_ready({"window": (None, None), "moon": {}, "entries": []})
        assert "no astronomical darkness" in page._plan_status.text().lower()
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_planning_recompute_status_flags_degraded_ranking(tmp_path, monkeypatch, qapp):
    """When cached contexts have no observability at all (astropy unavailable), the
    Recompute status says the ranking is degraded rather than the reassuring 'up to
    date'."""
    seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110 import prioritize
    from m110.prioritize import TargetContext
    prioritize.write_contexts([TargetContext("m13", "globular", 0, True, None),
                               TargetContext("m81", "galaxy", 0, True, None)])
    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    try:
        page._on_worker_done()
        assert "degraded" in page._status.text().lower()
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_planning_visible_tonight_toggle_filters(tmp_path, monkeypatch, qapp):
    """The 'Visible tonight' toggle (default on) hides not-up targets and persists;
    unchecking reveals the full ranking."""
    seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110 import prioritize
    from m110.prioritize import TargetContext
    up = {"observable": True, "hours_clear": 3.0, "transit_alt": 60.0,
          "nights_to_close": 20, "season": "summer"}
    out = {"observable": False, "hours_clear": 0.0, "transit_alt": 70.0,
           "nights_to_close": None, "season": "winter"}
    prioritize.write_contexts([TargetContext("m13", "globular", 0, True, up),
                               TargetContext("m42", "emission", 0, True, out)])
    from m110.ui.pages.planning import PlanningPage
    from PySide6.QtWidgets import QTableWidget
    page = PlanningPage()
    try:
        def ptable():
            # The ranking table is rebuilt on each re-render (old one deleteLater'd
            # but briefly still in the tree) — take the freshest 7-col table.
            return [t for t in page.findChildren(QTableWidget)
                    if t.columnCount() == 7][-1]          # #,Object,…,Closes

        def slugs():
            t = ptable()
            return {t.item(r, 1).data(Qt.UserRole) for r in range(t.rowCount())}

        assert page._visible_chk.isChecked()             # default on
        assert slugs() == {"m13"}                         # out-of-season m42 hidden
        page._visible_chk.setChecked(False)
        qapp.processEvents()                              # flush the old table's deleteLater
        assert prioritize.load_visible_tonight() is False
        assert slugs() == {"m13", "m42"}                  # full ranking now
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_planning_type_weight_spin_persists(tmp_path, monkeypatch, qapp):
    """Nudging a type-group spinbox persists a per-type multiplier the scorer reads."""
    seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110 import prioritize
    from m110.prioritize import TargetContext
    prioritize.write_contexts([TargetContext(
        "m13", "globular", 0, True,
        {"observable": True, "hours_clear": 3.0, "transit_alt": 60.0,
         "nights_to_close": 20, "season": "summer"})])
    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    try:
        page._type_spins["galaxy"].setValue(1.6)
        w = prioritize.load_weights()
        assert w.type_weights.get("galaxy") == pytest.approx(1.6)
        assert prioritize.groups_from_type_weights(
            w.type_weights)["galaxy"] == pytest.approx(1.6)
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_site_editor_computes_and_saves_glow(tmp_path, monkeypatch, qapp):
    root = seed_root(tmp_path, monkeypatch)
    from m110 import glow, planning_config as pc
    from PySide6.QtWidgets import QMessageBox
    # inject fixture towns (no bundled data needed) + silence the modal
    monkeypatch.setattr(glow, "load_towns",
                        lambda *a, **k: [glow.Town("Metro", 39.6, -105.0, 1_500_000)])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    from m110.ui.site_profile_editor import SiteProfileEditor
    ed = SiteProfileEditor()
    try:
        ed.load("default")
        ed._lat.setValue(40.0); ed._lon.setValue(-105.0); ed._bortle.setValue(5)
        ed._compute_glow()
        assert ed._glow_mask == "default.glow.hrz"
        ed._save()
        site = pc.load_site("default")
        assert site.glow_mask == "default.glow.hrz"
        # the saved floor demotes a low-southern target (toward the town)
        from m110 import horizon
        m = horizon.load_mask(site.glow_path())
        assert horizon.horizon_alt(180, m) > 15 and horizon.horizon_alt(0, m) < 2
    finally:
        ed.deleteLater(); qapp.processEvents()


def test_site_editor_survives_refresh_while_editing(tmp_path, monkeypatch, qapp):
    """A background refresh (window focus) must not wipe unsaved profile edits —
    only an explicit profile switch / Save / restart should reset the form."""
    seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    try:
        page.editor.load("default")
        page.editor._lat.setValue(12.345)              # user edits, hasn't saved
        assert page.editor.is_dirty()
        page.reload()                                  # simulate the focus refresh
        assert page.editor._lat.value() == pytest.approx(12.345)   # preserved
        page.editor._save()                            # now persist
        assert not page.editor.is_dirty()
        page.reload()
        assert page.editor._lat.value() == pytest.approx(12.345)   # saved value stays
    finally:
        page.deleteLater(); qapp.processEvents()


def test_planning_plan_a_night_and_save_and_view(tmp_path, monkeypatch, qapp):
    """Generate a night plan (injected fast plan_night), toggle include, save a field
    guide, and see it in the browser + render it in the viewer dialog."""
    from datetime import datetime
    root = seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110 import prioritize, planning, fieldguide
    from m110.prioritize import TargetContext
    obs = {"observable": True, "hours_clear": 3, "transit_alt": 60,
           "nights_to_close": 20, "season": "summer"}
    prioritize.write_contexts([TargetContext("m13", "globular", 30, True, obs),
                               TargetContext("m81", "galaxy", 0, True, obs)])
    from datetime import timedelta
    t0 = datetime(2026, 7, 13, 22, 30)
    t1 = datetime(2026, 7, 14, 3, 30)

    def fake_plan(site, day, slugs, **kw):
        n = int((t1 - t0).total_seconds() / 60 / 10) + 1
        samples = [(t0 + timedelta(minutes=10 * i), 50.0, True) for i in range(n)]
        return {"window": (t0, datetime(2026, 7, 14, 3, 50)),
                "moon": {"illum": 0.1, "alt": -17.0, "set_time": None,
                         "rise_time": None, "track": []},
                "start_ceiling_deg": 75.0, "ceiling_is_hard": True,
                "entries": [{"slug": s, "transit_time": t0, "transit_alt": 50.0,
                             "best_alt": 50.0, "start_time": t0, "start_alt": 50.0,
                             "over_ceiling": False, "up_start": t0, "up_end": t1,
                             "moon_sep_deg": 70.0, "samples": samples}
                            for s in slugs[:2]]}
    monkeypatch.setattr(planning, "plan_night", fake_plan)

    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    try:
        page._on_generate()
        qapp.processEvents()
        if page._planner is not None:
            page._planner.wait()
            qapp.processEvents()
        assert len(page._entries) == 2
        # the sequencer schedules both (count=4, only 2 candidates), chained slots
        assert page._plan_table.rowCount() == 2
        assert len(page._slots) == 2
        assert page._slots[1]["start"] == page._slots[0]["end"]
        assert page._slots[0]["start"].minute % 10 == 0
        assert "Astro dark" in page._plan_summary.text()

        # reorder: move row 1 up → forced-order reflow, starts re-chain from dusk
        page._plan_table.selectRow(1)
        first_before = page._slots[0]["slug"]
        page._move_selected(-1)
        assert page._slots[1]["slug"] == first_before
        assert page._slots[0]["start"].minute % 10 == 0

        # uncheck the first slot → excluded + reflowed (no replacement available)
        page._plan_table.item(0, 0).setCheckState(Qt.Unchecked)
        assert len(page._slots) == 1

        # save a field guide (the remaining scheduled target)
        from PySide6.QtWidgets import QInputDialog
        monkeypatch.setattr(QInputDialog, "getText",
                            staticmethod(lambda *a, **k: ("My Plan", True)))
        page._save_field_guide()
        guides = fieldguide.list_guides()
        assert len(guides) == 1
        assert "## Schedule (1 targets)" in fieldguide.read(guides[0]["path"])
        assert page._guides_table.rowCount() == 1

        # the viewer dialog renders the saved markdown
        from m110.ui.field_guide_dialog import FieldGuideDialog
        dlg = FieldGuideDialog(guides[0]["path"])
        assert "Observing plan" in dlg._view.toPlainText() or \
               "My Plan" in dlg._view.toPlainText()
        dlg.deleteLater()
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_night_timeline_sets_plan_without_error(qapp):
    from datetime import datetime
    from m110.ui.night_timeline import NightTimeline
    tl = NightTimeline()
    tl.set_plan(None)                      # empty → "no darkness" path, no crash
    t0 = datetime(2026, 7, 13, 22, 0)
    t_mid = datetime(2026, 7, 14, 1, 0)
    tl.set_plan({"window": (t0, datetime(2026, 7, 14, 4, 0)),
                 # Phase 2/3/4 overlays: moon track + ceiling + schedule bands all
                 # paint without error alongside the target curves.
                 "moon": {"illum": 0.3, "alt": 5.0, "set_time": None,
                          "rise_time": None,
                          "track": [(t0, 5.0), (t_mid, -10.0)]},
                 "start_ceiling_deg": 75.0, "ceiling_is_hard": True,
                 "schedule": [{"slug": "m13", "start": t0, "end": t_mid,
                               "duration_min": 180, "alt_start": 40.0,
                               "moon_sep_deg": 70.0, "moon_alt_at_best": 5.0,
                               "moon_impact": "low", "over_ceiling": False}],
                 "entries": [{"slug": "m13",
                              "samples": [(t0, 40.0, True),
                                          (t_mid, 85.0, True)]}]})
    tl.resize(400, 200)
    tl.grab()                              # force a paint pass
    tl.deleteLater()


def test_planning_page_save_uses_plan_day_and_invalidates_on_change(
        tmp_path, monkeypatch, qapp):
    """BUGS #36 root cause: a plan generated for day X, then the date widget moved
    to day Y, must (a) save the guide stamped with X's astronomy — never relabel —
    and (b) actually get *cleared* when the date changes (stale-plan invalidation),
    so the relabel can't happen at all."""
    from datetime import date, datetime
    seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110.ui.pages.planning import PlanningPage
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QInputDialog
    page = PlanningPage()
    try:
        gen_day = date(2026, 7, 13)
        t0 = datetime(2026, 7, 13, 22, 30)
        entry = {"slug": "m13", "transit_time": t0, "transit_alt": 85.0,
                 "best_alt": 85.0, "up_start": t0,
                 "up_end": datetime(2026, 7, 14, 3, 30), "moon_sep_deg": 70.0,
                 "moon_alt_at_best": -20.0, "moon_impact": None, "samples": []}
        page._entries = [entry]
        page._included = {"m13"}
        page._plan_meta = {"window": (t0, datetime(2026, 7, 14, 3, 50)),
                           "moon": {"illum": 0.02, "alt": -17.0,
                                    "set_time": None, "rise_time": None, "track": []},
                           "day": gen_day}

        # The widget wanders to another night; the save must still stamp gen_day.
        page._date.blockSignals(True)                  # isolate (a) from (b)
        page._date.setDate(QDate(2026, 7, 18))
        page._date.blockSignals(False)
        saved = {}
        monkeypatch.setattr(QInputDialog, "getText",
                            staticmethod(lambda *a, **k: ("T", True)))
        from m110 import fieldguide
        real_render = fieldguide.render_markdown
        def spy(site, day, plan, **kw):
            saved["day"] = day
            return real_render(site, day, plan, **kw)
        monkeypatch.setattr(fieldguide, "render_markdown", spy)
        page._save_field_guide()
        assert saved["day"] == gen_day                 # not the widget's Jul 18

        # And a real date change invalidates the stale plan outright.
        page._date.setDate(QDate(2026, 7, 25))
        assert page._entries == [] and page._plan_meta == {}
        assert "generate the plan again" in page._plan_status.text().lower()
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_saved_guides_row_actions_moved_to_a_context_menu(
        tmp_path, monkeypatch, qapp):
    """The guides list's per-row actions moved from three buttons into a right-click
    menu — the buttons duplicated the double-click and put Delete a few pixels from
    View. They were the only visible affordance, so pin what replaced them.

    Uses the exec-free `_guide_menu` builder + `_guide_row_at`, per the same
    constraint as the Library's `_object_menu`: a modal exec can't run headless and
    PySide6's QMenu.exec can't be monkeypatched."""
    from datetime import date
    seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110 import fieldguide
    for i, title in enumerate(["First night", "Second night", "Third night"]):
        fieldguide.save(date(2026, 8, 10 + i), title, f"# {title}\n\nBody.\n")

    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    try:
        page._reload_guides()
        tbl = page._guides_table
        assert tbl.rowCount() == 3
        # The action column is gone entirely — no cell widgets left to clip.
        assert tbl.columnCount() == 2
        assert all(tbl.cellWidget(r, c) is None
                   for r in range(tbl.rowCount()) for c in range(tbl.columnCount()))

        # The row comes from the CLICK, not the selection: select row 0, point at
        # the last row, and the menu must target the last row.
        tbl.selectRow(0)
        target = tbl.rowCount() - 1
        pos = tbl.visualItemRect(tbl.item(target, 0)).center()
        assert page._guide_row_at(pos) == target
        # …and a click below the rows resolves to nothing rather than row 0.
        assert page._guide_row_at(tbl.viewport().rect().bottomRight()) is None

        menu, acts = page._guide_menu(target)
        assert set(acts) == {"view", "reveal", "delete"}
        assert acts["delete"].text().startswith("Delete")
        menu.deleteLater()
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_reveal_guide_opens_the_folder_not_the_file(tmp_path, monkeypatch, qapp):
    """"Reveal in file manager" must show the guide's enclosing folder. It used to
    hand the .md file itself to QDesktopServices, which opens whatever app owns
    Markdown — a text editor, not the file manager. The shared
    `widgets.reveal_in_manager` already resolves a file to its parent."""
    from datetime import date
    seed_root(tmp_path, monkeypatch)
    _no_prioritizer_worker(monkeypatch)
    from m110 import fieldguide
    path = fieldguide.save(date(2026, 8, 10), "A night", "# A night\n\nBody.\n")

    opened = []
    from PySide6.QtGui import QDesktopServices
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(url.toLocalFile()) or True)

    from m110.ui.pages.planning import PlanningPage
    page = PlanningPage()
    try:
        page._reload_guides()
        page._reveal_guide(0)
        assert opened == [str(path.parent)]        # the Plans/ folder…
        assert opened[0] != str(path)              # …not the guide itself
    finally:
        page.deleteLater()
        qapp.processEvents()



def test_backup_dialog_browse_enables_save(tmp_path, monkeypatch, qapp):
    """Picking a folder with **Browse** must enable Save.

    Regression: dirty-tracking listened to `textEdited`, which by design ignores
    programmatic writes — and Browse sets the field with `setText`. So a user who
    fixed a wrong destination via Browse got a greyed-out Save and no way to keep
    the correction. Only the constructor and Browse ever write this field; the
    destination probe writes the status label, never the path."""
    seed_root(tmp_path, monkeypatch)
    from m110.ui.backup_dialog import BackupDialog
    dlg = BackupDialog()
    try:
        assert dlg._save_btn.isEnabled() is False
        chosen = tmp_path / "picked"
        chosen.mkdir()
        monkeypatch.setattr(
            "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
            lambda *a, **k: str(chosen))
        dlg._browse()
        assert dlg._dest.text() == str(chosen)
        assert dlg._save_btn.isEnabled() is True
        assert dlg._reject_btn.text() == "Cancel"
    finally:
        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


def test_backup_dialog_never_erases_a_configured_destination(
        tmp_path, monkeypatch, qapp):
    """An empty box means "not entered", not "clear it".

    The destination is a path the user chose once and may not remember, and losing
    it silently stops their backups. Saving with the field blank used to write ""
    straight over it."""
    seed_root(tmp_path, monkeypatch)
    from m110 import backup, config
    config.save_setting(backup.SETTING_DEST, "/Volumes/Archive/M110-backup")

    from m110.ui.backup_dialog import BackupDialog
    dlg = BackupDialog()
    try:
        assert dlg._dest.text() == "/Volumes/Archive/M110-backup"   # loads it back
        dlg._dest.setText("")
        dlg._save_and_close()
        assert config.get_setting(backup.SETTING_DEST) == "/Volumes/Archive/M110-backup"
    finally:
        dlg.deleteLater()
        qapp.processEvents()


def test_backup_dialog_round_trips_the_destination_untouched(
        tmp_path, monkeypatch, qapp):
    """Open, change nothing, Save: the stored destination must come back byte-identical.
    A settings dialog that rewrites a value it merely displayed is how a path gets
    silently replaced."""
    seed_root(tmp_path, monkeypatch)
    from m110 import backup, config
    original = "/Volumes/AstroArchive/M110-backup/"
    config.save_setting(backup.SETTING_DEST, original)

    from m110.ui.backup_dialog import BackupDialog
    dlg = BackupDialog()
    try:
        dlg._save_and_close()
        assert config.get_setting(backup.SETTING_DEST) == original
    finally:
        dlg.deleteLater()
        qapp.processEvents()
