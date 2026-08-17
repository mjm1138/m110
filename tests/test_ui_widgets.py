"""Shared widgets — status pill delegate + table helpers."""
import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QStyleOptionViewItem, QTableWidget, QTableWidgetItem,
)

from m110.ui import theme
from m110.ui.widgets import (
    STATUS_ROLE, StatusPillDelegate, make_table, status_label,
)


def _opt_index_for(qapp, status, captured):
    t = QTableWidget(1, 1)
    d = StatusPillDelegate(t)
    t.setItemDelegateForColumn(0, d)
    it = QTableWidgetItem(status_label(status, captured))
    it.setData(STATUS_ROLE, status if captured else None)
    t.setItem(0, 0, it)
    idx = t.model().index(0, 0)
    opt = QStyleOptionViewItem()
    d.initStyleOption(opt, idx)
    opt.rect = QRect(0, 0, 160, 28)
    return d, opt, idx, t


def test_pill_delegate_paints_captured(qapp):
    theme.install(qapp)
    d, opt, idx, _t = _opt_index_for(qapp, "deep_stack", True)
    pm = QPixmap(160, 28)
    p = QPainter(pm)
    d.paint(p, opt, idx)              # must not raise
    p.end()
    assert d.sizeHint(opt, idx).width() > opt.rect.width() - 160  # widened for the chip


def test_pill_delegate_paints_uncaptured_dash(qapp):
    theme.install(qapp)
    d, opt, idx, _t = _opt_index_for(qapp, None, False)
    pm = QPixmap(160, 28)
    p = QPainter(pm)
    d.paint(p, opt, idx)              # muted-dash path, must not raise
    p.end()


def test_make_table_has_alternating_rows(qapp):
    t = make_table(["A", "B"])
    assert t.alternatingRowColors() is True


def test_make_numeric_right_aligns_and_mono(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTableWidgetItem
    from m110.ui.theme import fonts
    from m110.ui.widgets import make_numeric
    theme.install(qapp)
    it = make_numeric(QTableWidgetItem("42"))
    assert it.textAlignment() & Qt.AlignmentFlag.AlignRight
    fam = fonts.load_fonts()
    if fam:
        assert it.font().family() == fam
    # mono=False → right-aligned but no font override
    plain = make_numeric(QTableWidgetItem("7"), mono=False)
    assert plain.textAlignment() & Qt.AlignmentFlag.AlignRight


def test_thumbnail_loader_decodes_async_and_caches(tmp_path, qapp, qtbot):
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    from m110.ui.widgets import ThumbnailLoader

    img_path = tmp_path / "hero.jpg"
    Image.new("RGB", (200, 100), (10, 20, 30)).save(img_path)

    loader = ThumbnailLoader()
    results = []
    loader.request(img_path, 20, results.append)
    qtbot.waitUntil(lambda: len(results) == 1, timeout=2000)
    assert results[0] is not None and not results[0].isNull()

    # same (path, size) again → cache hit, callback fires synchronously
    results2 = []
    loader.request(img_path, 20, results2.append)
    assert len(results2) == 1 and results2[0] is not None


def test_drain_thumbnail_pool_waits_for_inflight_decode(tmp_path, qapp):
    """drain_thumbnail_pool() must block until an in-flight decode finishes, so no
    pool thread is still running native Qt image code when Qt tears down — the
    intermittent CI SIGSEGV (exit 139) the drain exists to prevent."""
    pytest.importorskip("PIL")
    from PIL import Image
    from PySide6.QtCore import QThreadPool, QCoreApplication
    from m110.ui.widgets import ThumbnailLoader, drain_thumbnail_pool

    img_path = tmp_path / "hero.jpg"
    Image.new("RGB", (300, 200), (5, 6, 7)).save(img_path)

    loader = ThumbnailLoader()
    results = []
    loader.request(img_path, 24, results.append)     # queues a background decode
    drain_thumbnail_pool(10000)                       # must wait for it to finish
    assert QThreadPool.globalInstance().activeThreadCount() == 0
    QCoreApplication.processEvents()                  # deliver the queued result
    assert results and results[0] is not None and not results[0].isNull()


def test_thumbnail_loader_missing_file_calls_back_none(tmp_path, qapp):
    from m110.ui.widgets import ThumbnailLoader

    loader = ThumbnailLoader()
    results = []
    loader.request(tmp_path / "missing.jpg", 20, results.append)
    assert results == [None]


def test_row_thumbnails_reset_drops_stale_slug(tmp_path, qapp, monkeypatch):
    from m110 import config
    from m110.ui.widgets import ThumbnailLoader, RowThumbnails

    monkeypatch.setattr(config, "HERO_DIR", tmp_path / "hero")
    config.HERO_DIR.mkdir(parents=True)
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    Image.new("RGB", (40, 40), (1, 2, 3)).save(config.HERO_DIR / "m1.jpg")

    thumbs = RowThumbnails(ThumbnailLoader())
    item = QTableWidgetItem("M1")
    thumbs.add("m1", item)
    # a rebuild resets tracking before the slug reappears (or not) — an apply
    # for a slug no longer tracked must be a no-op, not touch a stale item.
    thumbs.reset()
    thumbs._apply("m1", QPixmap(4, 4))   # simulate a late callback landing post-reset
    assert item.icon().isNull()


def test_no_widget_label_eats_an_ampersand_as_a_mnemonic():
    """Qt reads a single "&" in a button/checkbox/group-box label as a mnemonic
    marker: it is consumed and the next character is underlined. "Automation &
    retention" therefore rendered as "Automation  retention" in the Backup dialog.
    A literal ampersand has to be written "&&".

    A source scan rather than a widget walk: it covers every label in the UI,
    including ones behind a dialog that a test would have to construct, and it's
    the same shape as the assistant's static AST checks."""
    import re
    from pathlib import Path

    ui = Path(__file__).resolve().parents[1] / "m110" / "ui"
    # A label passed straight to a widget constructor / setter.
    call = re.compile(
        r"(?:QGroupBox|QCheckBox|QPushButton|QRadioButton|QLabel|QAction|QMenu)\("
        r"\s*(['\"])(.*?)\1"
        r"|set(?:Title|Text)\(\s*(['\"])(.*?)\3")
    # A lone "&" — not "&&", and not an HTML entity (QLabel accepts rich text).
    lone = re.compile(r"(?<!&)&(?!&|amp;|nbsp;|lt;|gt;|quot;|#)")

    offenders = []
    for py in sorted(ui.rglob("*.py")):
        for m in call.finditer(py.read_text(encoding="utf-8")):
            text = m.group(2) if m.group(2) is not None else m.group(4)
            if text and lone.search(text):
                offenders.append(f"{py.relative_to(ui)}: {text!r}")
    assert not offenders, (
        "these labels contain a single '&', which Qt eats as a mnemonic — "
        "write '&&' for a literal ampersand:\n  " + "\n  ".join(offenders))
