"""QSS generation from tokens."""
import re

from m110.ui.theme import tokens
from m110.ui.theme.qss import ICONS_DIR, build_qss


def test_build_qss_nonempty_for_both():
    assert build_qss(tokens.LIGHT).strip()
    assert build_qss(tokens.DARK).strip()


def test_light_and_dark_qss_differ():
    assert build_qss(tokens.LIGHT) != build_qss(tokens.DARK)


def test_qss_contains_key_selectors_and_palette():
    qss = build_qss(tokens.DARK)
    for sel in ("QTableWidget", 'QLabel[muted="true"]', 'QLabel[caption="true"]',
                "QListWidget::item:selected", "QMenu", "QHeaderView::section"):
        assert sel in qss, f"missing selector {sel}"
    assert tokens.DARK.window in qss
    assert tokens.DARK.accent in qss


def test_table_check_indicator_is_stylesheet_drawn():
    """Item check indicators must carry explicit ::indicator rules.

    QMacStyle only paints an item-view check indicator for the *current* row; every
    other checked row renders blank (state + click handling are unaffected, so the
    Import preview's checkboxes looked dead while silently toggling). Explicit rules
    route the indicator through QStyleSheetStyle, which paints every row. Without
    them the blank rows come back — and no offscreen paint test can catch it, since
    the offscreen platform can't render the macOS style at all.
    """
    for t in (tokens.LIGHT, tokens.DARK):
        qss = build_qss(t)
        assert "QTableWidget::indicator" in qss
        assert "QTableWidget::indicator:checked" in qss
        # the checked state needs a glyph, else it's an ambiguous filled square
        checked = qss.split("QTableWidget::indicator:checked {", 1)[1].split("}", 1)[0]
        assert "image: url(" in checked


def test_check_indicator_icons_exist():
    """Every url(...) the sheet references must resolve, or the glyph silently
    vanishes (Qt fails quietly on a missing stylesheet image)."""
    qss = build_qss(tokens.LIGHT)
    urls = re.findall(r"image: url\(([^)]+)\)", qss)
    assert urls, "no indicator images referenced"
    for u in urls:
        assert ICONS_DIR.joinpath(u.rsplit("/", 1)[-1]).is_file(), f"missing icon {u}"
        assert "\\" not in u, "QSS url() needs POSIX separators"


def test_pushbutton_has_min_height():
    """QPushButton needs a min-height so a styled button in a tight layout doesn't
    clip its label top-and-bottom (esp. on macOS)."""
    qss = build_qss(tokens.LIGHT)
    btn_block = qss.split("QPushButton {", 1)[1].split("}", 1)[0]
    assert "min-height" in btn_block
