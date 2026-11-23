"""The inspector's title block is pinned at the top: name, facts, ✕ top right.

Mike: the ✕ "hanging out by itself" under the hero was hard to find, and it
scrolled away with the body. The title block (serif name + common name, the
facts line, the close button) is now a header pinned above the scrolling body —
a child of the scroll area with the viewport pushed down — and the hero sits
under it. The placeholder and the Notes editor have no header.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402

from m110.ui.image_viewer import ScalableImage  # noqa: E402
from tests.test_ui_detail import _seed_object_with_images  # noqa: E402


def _settle(qapp, n=10):
    for _ in range(n):
        qapp.processEvents()


@pytest.fixture
def pane(tmp_path, monkeypatch, qapp, qtbot):
    from m110.ui.detail import DetailPane
    slug, e, t = _seed_object_with_images(tmp_path, monkeypatch)
    d = DetailPane()
    qtbot.addWidget(d)
    d.resize(460, 600)
    d.show()
    d.show_object(slug, e, t)
    _settle(qapp)
    d._seeded = (slug, e, t)
    return d


def _top(d, w):
    return w.mapTo(d, QPoint(0, 0)).y()


def _header_h(d):
    return d.viewportMargins().top()


def test_title_facts_and_close_are_pinned_above_the_hero(pane):
    d = pane
    hdr = d._header
    assert not hdr.isHidden()
    h = _header_h(d)
    assert h > 0 and hdr.height() == h
    assert hdr.geometry().top() == d.frameWidth()
    # ✕ at the pane's top right, inside the header
    btn = d._close_btn
    assert btn.parent() is hdr
    assert _top(d, btn) < h
    right_gap = d.width() - (btn.mapTo(d, QPoint(0, 0)).x() + btn.width())
    assert right_gap <= 24
    # the name and the facts are in the header, the hero below it
    texts = [lbl.text() for lbl in hdr.findChildren(QLabel)]
    assert any("M" in t and "<span" in t for t in texts)      # object_title
    hero = d._hero_slot.itemAt(0).widget()
    assert isinstance(hero, ScalableImage)
    assert _top(d, hero) >= h
    assert not d._content.isAncestorOf(btn)          # not in the scrolling body


def test_the_header_stays_put_when_the_body_scrolls(pane, qapp):
    d = pane
    before = d._header.geometry()
    sb = d.verticalScrollBar()
    assert sb.maximum() > 0
    sb.setValue(sb.maximum())
    _settle(qapp)
    assert d._header.geometry() == before
    assert d._header.isVisible()
    # the scrollbar runs below the header, not under it
    assert sb.mapTo(d, QPoint(0, 0)).y() >= _header_h(d)
    closed = []
    d.closed.connect(lambda: closed.append(True))
    d._close_btn.click()
    assert closed == [True]


def test_a_narrow_pane_wraps_the_title_and_the_header_grows(pane, qapp):
    d = pane
    wide = _header_h(d)
    d.resize(200, 600)
    _settle(qapp)
    assert _header_h(d) > wide
    assert d._header.height() == _header_h(d)
    assert d._header.width() == d.width() - 2 * d.frameWidth()


def test_placeholder_and_editor_have_no_header(pane, qapp):
    d = pane
    d._enter_edit()
    _settle(qapp)
    assert d._header.isHidden() and _header_h(d) == 0
    d._cancel_edit()
    _settle(qapp)
    assert not d._header.isHidden() and _header_h(d) > 0
    d.placeholder()
    _settle(qapp)
    assert d._header.isHidden() and _header_h(d) == 0


def test_reshowing_rebuilds_one_header(pane, qapp):
    """Each show_object clears the old title block — no pile-up of titles or ✕s."""
    d = pane
    for _ in range(3):
        d.show_object(*d._seeded)
        _settle(qapp)
    from PySide6.QtWidgets import QToolButton
    live = [b for b in d._header.findChildren(QToolButton) if not b.isHidden()]
    assert live == [d._close_btn]
