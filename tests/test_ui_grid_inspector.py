"""UI 1.0 Phase 8 · B — overlay tiles, the justified grid, and the inspector.

* `image_grid.justify` / `JustifiedGridView`: every row fills the width.
* `TileDelegate`: paints on a real pixmap (offscreen can't catch a delegate that
  raises inside `paint` from model-state tests alone), drops the status label
  before eliding the title, outlines the selection in the accent.
* The inspector: hero `fit="cover"`, the Integration card, the DETAILS rows, notes
  without the journal's own `# title`.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem  # noqa: E402

from m110 import config  # noqa: E402
from m110.ui import theme  # noqa: E402
from m110.ui.image_grid import (  # noqa: E402
    JustifiedGridView, TileDelegate, TileItem, TileModel, justify,
)


# ── the justified grid ──────────────────────────────────────────────────────
@pytest.mark.parametrize("width,target,gap", [
    (1036, 140, 8), (997, 140, 8), (300, 140, 8), (100, 140, 8), (2000, 80, 8),
    (681, 220, 8),
])
def test_justify_fills_the_row(width, target, gap):
    cols, cell = justify(width, target, gap)
    assert cols >= 1
    assert cols * cell <= width                     # never wraps early
    assert width - cols * cell < cols               # leftover under a px per column
    if width >= target + gap:
        assert cell >= target + gap                 # tiles only ever grow to fill


def _grid(qapp, n=15, width=1000, target=140):
    m = TileModel()
    m.set_items([TileItem(key=str(i), thumb_path=None, title=f"M{i}",
                          status="initial", status_text="Initial") for i in range(n)])
    v = JustifiedGridView(target)
    v.setModel(m)
    v.resize(width, 600)
    v.show()
    qapp.processEvents()
    return v, m


def _row_of(v, m, row):
    return [r for r in range(m.rowCount())
            if v.visualRect(m.index(r)).top() == v.visualRect(m.index(row)).top()]


def test_grid_rows_hold_exactly_the_computed_columns(qapp):
    """Qt wraps an icon view inside the viewport less a scrollbar's width; the
    view must count columns against the same bounds, or the last one wraps and
    leaves the ragged gap this replaced."""
    for width in (1000, 700, 1301):
        v, m = _grid(qapp, width=width)
        try:
            first_row = _row_of(v, m, 0)
            assert len(first_row) == v.columns(), (width, len(first_row), v.columns())
            right = v.visualRect(m.index(first_row[-1])).right()
            assert v.viewport().width() - right <= v._reserved_scrollbar() + v.columns() + 1
        finally:
            v.close()


def test_grid_target_size_and_resize_change_the_columns(qapp):
    v, m = _grid(qapp, width=1000, target=140)
    try:
        wide = v.columns()
        v.set_target_size(220)
        qapp.processEvents()
        assert v.columns() < wide
        assert v.tile_side() >= 220
        v.resize(500, 600)
        qapp.processEvents()
        assert v.columns() == len(_row_of(v, m, 0))
    finally:
        v.close()


def test_grid_asks_for_sharper_thumbnails_when_tiles_grow(qapp, qtbot):
    v, m = _grid(qapp, width=600, target=100)
    try:
        v.note_decoded(v.thumbnail_px())
        with qtbot.waitSignal(v.tileSideChanged, timeout=2000) as sig:
            v.set_target_size(200)
        assert sig.args[0] >= 200
        assert sig.args[0] == v.thumbnail_px()
    finally:
        v.close()


# ── the tile ────────────────────────────────────────────────────────────────
def _paint_tile(index, delegate, view, size=180, selected=False):
    pm = QPixmap(size, size)
    pm.fill(QColor("#000000"))
    p = QPainter(pm)
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, size, size)
    opt.widget = view
    opt.state = QStyle.StateFlag.State_Enabled
    if selected:
        opt.state |= QStyle.StateFlag.State_Selected
    delegate.paint(p, opt, index)
    p.end()
    return pm.toImage()


def test_tile_paints_image_empty_slot_badge_and_selection(qapp):
    m = TileModel()
    m.set_items([
        TileItem(key="a", thumb_path=None, title="M81", status="deep_stack",
                 status_text="Deep"),
        TileItem(key="b", thumb_path=None, title="NGC 7000", muted=True),
        TileItem(key="c", thumb_path=None, title="clip.mp4", badge="▶"),
    ])
    img = QImage(64, 48, QImage.Format.Format_RGB32)
    img.fill(QColor("#f0f0f0"))                      # a bright picture
    m._on_thumb("a", QPixmap.fromImage(img))
    v = JustifiedGridView(140)
    v.setModel(m)
    d = v.tile_delegate()
    d.set_cell(180, 8)
    try:
        shot = _paint_tile(m.index(0), d, v)
        tile = d.tile_rect(QRect(0, 0, 180, 180))
        top = QColor(shot.pixel(int(tile.center().x()), int(tile.top()) + 10))
        bottom = QColor(shot.pixel(int(tile.left()) + 4, int(tile.bottom()) - 3))
        assert top.lightness() > 200                 # the image fills the tile
        assert bottom.lightness() < top.lightness()  # the caption's scrim
        # empty slot = the well's surface, not the image
        slot = _paint_tile(m.index(1), d, v)
        assert QColor(slot.pixel(90, 40)) == QColor(theme.on_well().surface)
        _paint_tile(m.index(2), d, v)                # the badge path
        sel = _paint_tile(m.index(0), d, v, selected=True)
        edge = QColor(sel.pixel(int(tile.center().x()), int(tile.top()) + 1))
        assert edge == QColor(theme.active_tokens().accent)
    finally:
        v.close()


def test_caption_drops_the_status_label_before_eliding_the_title(qapp):
    d = TileDelegate(140)
    title = "C20 (NGC 7000)"
    text, _, status, show = d.caption_layout(QRectF(0, 0, 400, 400), title, "Initial")
    assert text == title and status is not None and show
    # Shrink the tile: the label goes first, at a width where the title still fits.
    label_gone = elided = None
    for side in range(400, 40, -2):
        text, rect, status, show = d.caption_layout(QRectF(0, 0, side, side), title,
                                                    "Initial")
        assert status is not None                    # the dot always stays
        assert rect.right() < status.left()          # and is never overlapped
        if label_gone is None and not show:
            label_gone = side
            assert text == title                     # the identity survives whole
        if elided is None and text != title:
            elided = side
            assert text.endswith("…")
    assert label_gone is not None and elided is not None and elided < label_gone


def test_tile_tooltip_carries_what_the_caption_leaves_out(qapp):
    m = TileModel()
    m.set_items([TileItem(key="a", thumb_path=None, title="M81",
                          subtitle="0:10 · 2 sessions", status_text="Initial")])
    tip = m.data(m.index(0), Qt.ItemDataRole.ToolTipRole)
    assert tip.splitlines() == ["M81", "Initial", "0:10 · 2 sessions"]


def test_media_grid_cuts_long_filenames_in_the_middle(tmp_path, monkeypatch, qapp):
    from tests._helpers import seed_root
    seed_root(tmp_path, monkeypatch)
    from m110.ui.pages.media import MediaPage
    page = MediaPage()
    try:
        d = page.grid_view.tile_delegate()
        text, *_ = d.caption_layout(QRectF(0, 0, 120, 120),
                                    "2026-08-14-221530-Jupiter-RAW.avi", None)
        assert text.startswith("2026") and text.endswith(".avi") and "…" in text
    finally:
        page.deleteLater()
        qapp.processEvents()


# ── the inspector ───────────────────────────────────────────────────────────
def test_cover_hero_fills_the_width_and_caps_the_height(qapp):
    from m110.ui.image_viewer import ScalableImage
    tall = QPixmap(400, 800)
    tall.fill(QColor("#123456"))
    h = ScalableImage(tall, max_height=460, fit="cover")
    assert h.cover_height(400) == 300                # 0.75 × width, cropped
    assert h.cover_height(1000) == 460               # and never past max_height
    wide = ScalableImage(QPixmap(800, 200), max_height=460, fit="cover")
    assert wide.cover_height(400) == 100             # shorter than the cap: natural
    pm = h.cover_pixmap(400)
    assert pm.width() == round(400 * pm.devicePixelRatio())
    assert pm.height() == round(300 * pm.devicePixelRatio())


def test_fmt_duration_and_facts_line():
    from m110.ui.detail import facts_line, fmt_duration
    assert fmt_duration(1797) == "29 h 57 m"
    assert fmt_duration(45) == "45 m"
    assert fmt_duration(1200) == "20 h"
    assert fmt_duration(None) == "0 m"
    assert facts_line({"type": "galaxy", "magnitude": 6.9, "size": "27'×14'",
                       "season": "Feb–Apr"}) == "Galaxy · mag 6.9 · 27'×14' · Feb–Apr"
    assert facts_line({"type": "open_cluster"}) == "Open cluster"


def test_details_rows_put_the_capture_first(tmp_path, monkeypatch, qapp):
    from m110 import catalog, derived
    from m110.ui.detail import details_rows
    from tests._helpers import seed_root, seed_capture
    root = seed_root(tmp_path, monkeypatch)
    slug, _ = seed_capture(root)
    e = catalog.load_library()[slug]
    keys = [k for k, _ in details_rows(slug, e, derived.totals_by_slug()[slug])]
    assert keys[:2] == ["Sessions", "Frames"]
    assert keys.index("Frames") < keys.index("Type")
    assert keys[-1] == "Slug"
    bare = [k for k, _ in details_rows(slug, e, {})]
    assert "Sessions" not in bare and "Type" in bare


def test_integration_card_shows_total_bar_and_goal(tmp_path, monkeypatch, qapp):
    from PySide6.QtWidgets import QLabel, QProgressBar
    from m110 import catalog, derived
    from m110.ui.detail import DetailPane
    from tests._helpers import seed_root, seed_capture
    root = seed_root(tmp_path, monkeypatch)
    slug, _ = seed_capture(root)
    e = catalog.load_library()[slug]
    t = derived.totals_by_slug()[slug]
    d = DetailPane()
    try:
        d.show_object(slug, e, t)
        card = d._content.findChild(QLabel, "integrationTotal").parent()
        bar = card.findChild(QProgressBar, "integrationBar")
        assert bar.property("status") == t["status"]
        assert bar.value() == round(min(1.0, t["progress"]) * 1000)
        line = card.findChild(QLabel, "integrationStatus").text()
        assert "goal" in line and " on " in line
        d.show_object(slug, e, {})                   # not captured
        card = d._content.findChild(QLabel, "integrationTotal").parent()
        assert card.findChild(QProgressBar) is None
        assert any("Not captured" in w.text() for w in card.findChildren(QLabel))
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_notes_drop_the_journal_title_but_editing_shows_it(tmp_path, monkeypatch, qapp):
    from m110 import catalog, derived, objects
    from m110.ui.detail import DetailPane, _NotesView
    from tests._helpers import seed_root, seed_capture
    root = seed_root(tmp_path, monkeypatch)
    slug, _ = seed_capture(root)
    objects.write_journal(slug, "# M-test — Title Line\n\nIRCUT looked better.\n")
    d = DetailPane()
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        notes = d._content.findChild(_NotesView)
        assert "IRCUT looked better" in notes.toPlainText()
        assert "Title Line" not in notes.toPlainText()
        assert notes.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        d._enter_edit()
        assert d._editor.toPlainText().startswith("# M-test — Title Line")
        d._cancel_edit()
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_close_button_is_the_lucide_x_and_closes(tmp_path, monkeypatch, qapp):
    from m110 import catalog, derived
    from m110.ui.detail import DetailPane
    from tests._helpers import seed_root, seed_capture
    root = seed_root(tmp_path, monkeypatch)
    slug, _ = seed_capture(root)
    d = DetailPane()
    closed = []
    d.closed.connect(lambda: closed.append(True))
    try:
        d.show_object(slug, catalog.load_library()[slug],
                      derived.totals_by_slug().get(slug, {}))
        assert d._close_btn.text() == "" and not d._close_btn.icon().isNull()
        d._close_btn.click()
        assert closed == [True]
    finally:
        d.deleteLater()
        qapp.processEvents()


def test_qss_colours_goal_bars_by_status_not_accent():
    from m110.ui.theme import qss, tokens
    sheet = qss.build_qss(tokens.DARK)
    for status, color in (("deep_stack", tokens.DARK.status_deep),
                          ("in_progress", tokens.DARK.status_progress),
                          ("initial", tokens.DARK.status_initial)):
        assert f'QProgressBar[status="{status}"]::chunk {{ background-color: {color};' in sheet
    assert 'QFrame[card="true"]' in sheet
