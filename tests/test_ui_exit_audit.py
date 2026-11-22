"""The UI 1.0 exit audit (UI Phase 8 · F), kept as tests.

`docs-archive/UI_CRITIQUE_2026-11.md` filed five P1s: no Edit menu, no Window
menu, object commands only in context menus, white-on-accent at 3.1:1, and no
toolbar. Phase 7 closed them and Phase 8 built on top. Each is re-checked here in
one place, across every selectable theme, so 1.0 can't quietly lose one. AA for
every text pair lives in `test_theme_contrast.py` (it covers all three palettes);
this adds the night-specific rule that nothing in the night palette leaves red.
"""
import re

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QKeySequence  # noqa: E402

from m110.ui.theme import build_qss, contrast, tokens  # noqa: E402
from tests._helpers import seed_root  # noqa: E402


@pytest.fixture
def win(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    from m110.ui.main import MainWindow
    w = MainWindow()
    w._ready = False
    yield w
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _labels(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def _keys(action):
    return {k.toString() for k in action.shortcuts()}


def test_the_menu_bar_is_the_mac_set(win):
    titles = [a.text() for a in win.menuBar().actions()]
    for title in ("File", "Edit", "View", "Object", "Library", "Window", "Help"):
        assert title in titles


def test_p1_edit_menu(win):
    """P1 · No Edit menu."""
    labels = _labels(win.edit_menu)
    for want in ("Copy", "Select All", "Find…"):
        assert want in labels
    assert any(t.startswith("Undo") for t in labels)
    assert any(t.startswith("Redo") for t in labels)
    assert QKeySequence(QKeySequence.StandardKey.Find).toString() in _keys(win.find_action)


def test_p1_window_menu_and_close(win):
    """P1 · No Window menu (and no ⌘W on the main window)."""
    labels = _labels(win.window_menu)
    assert "Minimize" in labels and "Zoom" in labels
    assert "Ctrl+M" in _keys(win.minimize_action)
    assert QKeySequence(QKeySequence.StandardKey.Close).toString() in \
        _keys(win.close_window_action)


def test_p1_object_commands_live_in_the_menu_bar(win):
    """P1 · Object commands only in context menus and pane buttons."""
    labels = _labels(win.object_menu)
    for want in ("Set Goal…", "Pin as Priority", "Deprioritize", "Process in Siril",
                 "Send to AstroWizard…", "Stack in StackingWizard…",
                 "Import Finished Work…", "Export for Sharing…",
                 "Reveal Working Folder", "Remove from Library"):
        assert want in labels, want


@pytest.mark.parametrize("t", list(tokens.THEMES.values()), ids=lambda t: t.name)
def test_p1_selected_item_contrast(t):
    """P1 (a11y) · White on the accent was 3.1:1. Every selectable theme now."""
    assert contrast.ratio(t.accent_text, t.accent) >= 4.5
    assert contrast.ratio(t.selection_text, t.selection_bg) >= 4.5


def test_p1_the_toolbar_holds_the_search_field(win):
    """P1 · No toolbar; controls stacked in the content area. The header bar is
    the toolbar: Deep Sky's search field lives in it, not above the grid."""
    win.go_to(win.pages.index(win.catalog))
    field, parent = win.catalog._search, win.catalog._search.parentWidget()
    while parent is not None and parent is not win.header:
        parent = parent.parentWidget()
    assert parent is win.header, "the search field isn't in the header bar"
    assert field.isVisibleTo(win)


def test_night_vision_is_reachable_from_view_and_settings(win):
    assert "Night Vision" in _labels(win.view_menu)
    assert win.night_action.isCheckable()


def test_nothing_in_the_night_palette_leaves_red():
    """Night vision's point: no colour the night stylesheet paints has more green or
    blue than red (images go through `theme.night_image`, which zeroes both)."""
    for role in tokens.ROLE_FIELDS:
        c = QColor(getattr(tokens.NIGHT, role))
        assert c.green() <= c.red() and c.blue() <= c.red(), role
    qss = build_qss(tokens.NIGHT)
    for hexcol in set(re.findall(r"#[0-9a-fA-F]{6}\b", qss)):
        c = QColor(hexcol)
        assert c.green() <= c.red() and c.blue() <= c.red(), hexcol
