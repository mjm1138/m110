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


def test_nav_column_owns_the_surface_and_divider():
    """The brand mark sits *below* the rail, so a rail-owned border would stop short
    of it and leave the logo on the window background. (Asserted on the QSS, not by
    painting — QMacStyle-only gaps can't be caught offscreen.)"""
    for t in (tokens.LIGHT, tokens.DARK):
        qss = build_qss(t)
        col = re.search(r"QWidget#navColumn \{(.*?)\}", qss, re.S)
        assert col, "missing QWidget#navColumn rule"
        assert t.surface in col.group(1)
        assert f"border-right: 1px solid {t.border}" in col.group(1)

        rail = re.search(r"QListWidget#navRail \{(.*?)\}", qss, re.S)
        assert rail and "border-right" not in rail.group(1)

        # …and the mark must not punch a `window`-colored hole in that column —
        # the base QWidget rule paints QLabel too.
        logo = re.search(r"QLabel#navLogo \{(.*?)\}", qss, re.S)
        assert logo and "background-color: transparent" in logo.group(1)


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


def test_checkbox_and_radio_indicators_are_stylesheet_drawn():
    """Standalone QCheckBox / QRadioButton indicators need explicit ::indicator
    rules too. Left to QMacStyle, the *unchecked* box/circle renders near-invisibly
    on the dark surface (dark-on-dark, no readable border) — the click target
    vanishes in dark mode. Explicit rules give them a visible border + a :checked
    glyph. Can't be paint-tested offscreen (Fusion fallback) — assert on the QSS."""
    for t in (tokens.LIGHT, tokens.DARK):
        qss = build_qss(t)
        assert "QCheckBox::indicator" in qss
        assert "QRadioButton::indicator" in qss
        # unchecked base must carry a visible border (the invisible-in-dark bug)
        base = qss.split("QCheckBox::indicator, QRadioButton::indicator {", 1)[1] \
                  .split("}", 1)[0]
        assert t.border in base and "border:" in base
        # checked states need a glyph, else they're ambiguous filled shapes
        for sel in ("QCheckBox::indicator:checked {", "QRadioButton::indicator:checked {"):
            checked = qss.split(sel, 1)[1].split("}", 1)[0]
            assert "image: url(" in checked and t.accent in checked


def test_checkbox_radio_have_min_height():
    """A min-height keeps the styled 14px indicator from crowding stacked
    checkboxes/radios (their circles read as overlapping without it) — same
    reason QPushButton carries a min-height."""
    block = build_qss(tokens.LIGHT).split("QCheckBox, QRadioButton {", 1)[1] \
                                   .split("}", 1)[0]
    assert "min-height" in block


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


def test_inputs_have_min_height():
    """The sibling of the QPushButton rule above, and the same failure: styling an
    input puts the padding INSIDE it, so a tight layout hands the inner line edit
    less room than the font needs and the value clips top-and-bottom. Buttons and
    checkboxes declared a floor; the inputs didn't, so they were the only thing
    that collapsed in the Backup dialog — a 28px sizeHint squeezed to 16, leaving
    6px for a 16px font ("100" rendered as a row of stubs).

    Asserted on the generated QSS rather than by painting, per the theme gotcha:
    offscreen falls back to Fusion and can't validate what QMacStyle draws."""
    qss = build_qss(tokens.LIGHT)
    block = qss.split("QPlainTextEdit, QTextEdit {", 1)[1].split("}", 1)[0]
    assert "min-height" in block


def test_disabled_menu_items_are_greyed():
    """Styling QMenu::item stops Qt from auto-greying disabled entries, so a disabled
    context-menu item would draw at full strength and merely fail to highlight — it
    reads as broken, not unavailable. The sheet must grey it explicitly (like
    QPushButton:disabled). Native menu painting can't be regression-tested offscreen —
    assert on the generated QSS, per the theme gotcha."""
    for t in (tokens.LIGHT, tokens.DARK):
        qss = build_qss(t)
        assert "QMenu::item:disabled {" in qss
        rule = qss.split("QMenu::item:disabled {", 1)[1].split("}", 1)[0]
        assert t.text_disabled in rule


def test_calendar_popup_escapes_the_table_item_padding():
    """BUGS #43: the QDateEdit calendar's day grid is a QTableView subclass, so the
    generic `QTableView::item` padding squeezed its fixed-size day cells until
    two-digit dates + weekday names elided to "…", and the muted table selection
    made the picked date read as disabled. The sheet must scope the calendar back
    out: zero item padding + accent selection. (Offscreen paint can't regression-
    test this natively — assert on the generated QSS, per the theme gotcha.)"""
    for t in (tokens.LIGHT, tokens.DARK):
        qss = build_qss(t)
        assert "QCalendarWidget QTableView::item {" in qss
        cal_item = qss.split("QCalendarWidget QTableView::item {", 1)[1].split("}", 1)[0]
        assert "padding: 0px" in cal_item
        sel = qss.split("QCalendarWidget QTableView::item:selected {", 1)[1].split("}", 1)[0]
        assert t.accent in sel and t.accent_text in sel


def test_date_edit_is_covered_by_the_input_rules():
    """QDateEdit is QAbstractSpinBox kin but NOT matched by the QSpinBox selector —
    omitting it left the Planning "Night:" field on default palette colors, near-
    unreadable in dark mode (the #43 follow-up nit)."""
    for t in (tokens.LIGHT, tokens.DARK):
        qss = build_qss(t)
        # the selector list ending in "QPlainTextEdit, QTextEdit {" must name it
        input_selector = qss.split("QPlainTextEdit, QTextEdit {", 1)[0].rsplit("*/", 1)[-1]
        assert "QDateEdit" in input_selector          # the color/border rule
        assert "QDateEdit:focus" in qss               # the focus ring rule
