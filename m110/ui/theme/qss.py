"""Generate the app-wide Qt stylesheet from a `Tokens` palette.

One `build_qss(tokens)` produces the whole sheet; the manager installs it via
`app.setStyleSheet`, so every window/dialog inherits it. Selectors are kept broad
and token-driven — page-level polish (pill chips, alt rows, row heights) is Phase 1.
"""
from __future__ import annotations

from pathlib import Path

from .tokens import FONT_SIZE, RADIUS, SPACE, Tokens

ICONS_DIR = Path(__file__).parent / "icons"


def _icon_url(name: str) -> str:
    """Absolute POSIX path for a QSS `url(...)` (backslashes break the parser)."""
    return (ICONS_DIR / name).as_posix()


def build_qss(t: Tokens) -> str:
    r = RADIUS
    check_url = _icon_url("check.svg")
    dash_url = _icon_url("dash.svg")
    radio_dot_url = _icon_url("radio-dot.svg")
    chevron_up_url = _icon_url("chevron-up.svg")
    chevron_down_url = _icon_url("chevron-down.svg")
    return f"""
/* ── base ── */
QWidget {{
    background-color: {t.window};
    color: {t.text_primary};
    font-size: {FONT_SIZE['body']}px;
}}
QMainWindow, QDialog {{ background-color: {t.window}; }}
QToolTip {{
    background-color: {t.raised};
    color: {t.text_primary};
    border: 1px solid {t.border};
    padding: {SPACE['xs']}px {SPACE['sm']}px;
}}

/* ── muted / caption labels (the inline-gray sweep targets these) ── */
QLabel[muted="true"] {{ color: {t.text_secondary}; }}
QLabel[caption="true"] {{ color: {t.text_secondary}; font-size: {FONT_SIZE['caption']}px; }}

/* ── Overview "Manage goals" bounding box (the one non-table section) ── */
#manageGoalsBox {{
    border: 1px solid {t.border};
    border-radius: {r['md']}px;
    padding: {SPACE['xs']}px;
}}

/* ── joined segmented controls (Library: Deep sky|Media, List|Grid|Feed) ── */
/* The container has no border/background; each button carries the border, and the
   end buttons round their outer corners so the whole control reads as one pill. */
#segControl {{ background-color: transparent; }}
/* Sized like an NSSegmentedControl: macOS draws tool-button text at 11pt, and the
   blanket 13px + 12px padding made each segment 63x27 against a native 37x22. */
#segControl QToolButton#segButton {{
    border: 1px solid {t.border};
    border-left-width: 0px;             /* shared edges collapse to one line */
    border-radius: 0px;
    font-size: {FONT_SIZE['caption']}px;
    padding: 2px {SPACE['sm']}px;
    color: {t.text_primary};
    background-color: {t.surface};
}}
#segControl QToolButton#segButton[segpos="first"],
#segControl QToolButton#segButton[segpos="solo"] {{ border-left-width: 1px; }}
#segControl QToolButton#segButton[segpos="first"],
#segControl QToolButton#segButton[segpos="solo"] {{
    border-top-left-radius: {r['sm']}px;
    border-bottom-left-radius: {r['sm']}px;
}}
#segControl QToolButton#segButton[segpos="last"],
#segControl QToolButton#segButton[segpos="solo"] {{
    border-top-right-radius: {r['sm']}px;
    border-bottom-right-radius: {r['sm']}px;
}}
#segControl QToolButton#segButton:hover:!checked {{ background-color: {t.surface_alt}; }}
#segControl QToolButton#segButton:checked {{
    background-color: {t.accent};
    color: {t.accent_text};
}}

/* ── lists (galleries, pickers) ── */
QListWidget {{
    background-color: {t.surface};
    border: none;
    outline: 0;
}}
QListWidget::item:selected {{ background-color: {t.accent}; color: {t.accent_text}; }}
QListWidget::item:hover:!selected {{ background-color: {t.surface_alt}; }}

/* ── grid views (the Library grid, m110/ui/image_grid.py) ── */
QListView {{
    background-color: {t.surface};
    border: none;
    outline: 0;
}}
QListView::item:selected {{ background-color: {t.accent}; color: {t.accent_text}; }}
QListView::item:hover:!selected {{ background-color: {t.surface_alt}; }}

/* ── nav column (left): the rail + the brand mark anchored under it ──
   The surface and the divider belong to the *column*, not the rail — the mark
   sits below the list, so a rail-owned border would stop short of it and leave
   the logo on the window background. (Needs WA_StyledBackground on the plain
   QWidget; see MainWindow.__init__.) */
QWidget#navColumn {{
    background-color: {t.surface};
    border-right: 1px solid {t.border};
}}
QListWidget#navRail {{
    background-color: transparent;
    border: none;
    padding-top: {SPACE['sm']}px;
}}
/* The mark must not punch a `window`-colored hole in the column: the base
   `QWidget` rule above paints every widget, QLabel included. (Invisible while the
   mark sat on the window background; obvious once it sits on the column.) */
QLabel#navLogo {{ background-color: transparent; }}
/* A sidebar row, not a touch target: macOS sidebars (Finder, Mail) run 24–28px.
   `8px` padding made these 36px against a native 17 — +112%, the most visible
   clunky surface in the app because five of them stack down every screen. */
QListWidget#navRail::item {{
    padding: {SPACE['xs']}px {SPACE['sm'] + 2}px;
    margin: 1px {SPACE['xs']}px;
    border-radius: {r['sm']}px;
}}

/* ── tables ── */
QTableView, QTableWidget {{
    background-color: {t.surface};
    alternate-background-color: {t.surface_alt};
    gridline-color: {t.divider};
    border: 1px solid {t.border};
    border-radius: {r['md']}px;
    selection-background-color: {t.selection_bg};
    selection-color: {t.selection_text};
    outline: 0;
}}
/* Rows were 27px against a native 19. Keep a little horizontal breathing room and
   spend almost nothing vertically — a table is the densest surface in the app, so
   this is where padding costs the most rows on screen.
   NOTE: `widgets.CELL_WIDGET_PAD_H/V` restate these two numbers, because Qt lays a
   cell *widget* out inside this padding and nothing else accounts for it.
   `tests/test_ui_cell_widgets.py` fails the build if the two ever disagree. */
QTableView::item, QTableWidget::item {{ padding: {SPACE['xs'] // 2}px {SPACE['sm'] - 2}px; }}
/* Item check indicators are drawn by the stylesheet, not the platform style.
   QMacStyle only paints an item-view check indicator for the *current* row — every
   other checked row rendered blank (the model + click handling were fine, so the
   Import preview's checkboxes looked dead: clicks toggled state invisibly). Giving
   the indicator explicit rules routes it through QStyleSheetStyle, which paints all
   rows. Keep these rules — dropping them silently reintroduces the blank rows. */
QTableView::indicator, QTableWidget::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {t.border};
    border-radius: {r['sm']}px;
    background-color: {t.surface};
}}
QTableView::indicator:hover, QTableWidget::indicator:hover {{ border-color: {t.accent}; }}
QTableView::indicator:disabled, QTableWidget::indicator:disabled {{
    background-color: {t.surface_alt};
    border-color: {t.divider};
}}
QTableView::indicator:checked, QTableWidget::indicator:checked {{
    background-color: {t.accent};
    border-color: {t.accent};
    image: url({check_url});
}}
QTableView::indicator:indeterminate, QTableWidget::indicator:indeterminate {{
    background-color: {t.accent};
    border-color: {t.accent};
    image: url({dash_url});
}}
/* macOS draws header text at 11pt, deliberately smaller than body — the blanket
   QWidget font-size above was overriding that up to 13pt and taking the header
   from 21px to 33px. Restating the smaller size here is additive and can't affect
   body text anywhere else. */
QHeaderView::section {{
    background-color: {t.surface_alt};
    color: {t.text_secondary};
    font-size: {FONT_SIZE['caption']}px;
    padding: {SPACE['xs'] // 2}px {SPACE['sm']}px;
    border: none;
    border-bottom: 1px solid {t.border};
    border-right: 1px solid {t.divider};
}}
QTableCornerButton::section {{ background-color: {t.surface_alt}; border: none; }}

/* ── calendar popup (QDateEdit's picker) ──
   The calendar's day grid is a QTableView SUBCLASS, so the generic table rules
   above land on it: the item padding squeezed the small fixed day cells until
   two-digit dates + weekday names elided to "…", and the muted table selection
   made the picked date read as disabled (BUGS #43). Scope them back out. */
QCalendarWidget QTableView {{
    border: none;
    border-radius: 0;
    alternate-background-color: {t.surface};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}
QCalendarWidget QTableView::item {{ padding: 0px; }}
QCalendarWidget QTableView::item:selected {{
    background-color: {t.accent};
    color: {t.accent_text};
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {t.surface_alt};
}}
QCalendarWidget QToolButton {{
    color: {t.text_primary};
    background: transparent;
    border: none;
    border-radius: {r['sm']}px;
    padding: {SPACE['xs']}px {SPACE['sm']}px;
}}
QCalendarWidget QToolButton:hover {{ background-color: {t.surface}; }}
QCalendarWidget QToolButton::menu-indicator {{ image: none; }}

/* ── buttons ── */
QPushButton {{
    background-color: {t.surface};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: {r['sm']}px;
    padding: {SPACE['xs']}px {SPACE['md']}px;
    /* Guarantee vertical room for the label — a styled QPushButton in a tight
       layout (esp. on macOS) otherwise clips its text top-and-bottom. A literal,
       not `SPACE['xl'] - SPACE['xs']`: retuning an unrelated spacing token must not
       silently move a clipping floor. Buttons are deliberately left at 30px — they
       already measure 2px UNDER the native macOS 32px, so they were never the
       source of the "clunky" feel and shrinking them would undershoot the platform. */
    min-height: 20px;
}}
QPushButton:hover {{ background-color: {t.surface_alt}; }}
QPushButton:pressed {{ background-color: {t.selection_bg}; }}
QPushButton:default {{ border-color: {t.accent}; }}
QPushButton:disabled {{ color: {t.text_disabled}; border-color: {t.divider}; }}

/* ── inputs ── */
/* QDateEdit/QDateTimeEdit are QAbstractSpinBox kin but NOT covered by the
   QSpinBox selector — omitting them left the Planning "Night:" field on default
   palette colors, near-unreadable in dark mode (the #43 follow-up nit). */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit,
QPlainTextEdit, QTextEdit {{
    background-color: {t.surface};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: {r['sm']}px;
    /* macOS draws a text field MUCH shorter than a button — 21px against 32 — and
       flattening both to one height is what made the app read as clunky. Measured
       against the native metrics from the same style and font: `4px` padding with a
       20px floor put every input at 30px, +43% over native, while our buttons were
       already 2px *under* it. `2px` + a floor of just the line height lands at 24px.
       Still a touch roomier than the platform, which suits a data-dense app, but no
       longer a slab.
       The floor is NOT reduced with the padding, and that is deliberate. `min-height`
       sizes the *content* box, so it is the anti-clipping guarantee itself — the
       inner edit stays 20px at either padding — while the padding is what was making
       the control a slab. Cutting only the padding takes 30px to 26px and cannot
       narrow the text band at all. Written as a literal rather than
       `SPACE['xl'] - SPACE['xs']`: that expression made a clipping floor move
       silently whenever someone retuned an unrelated spacing token. */
    padding: {SPACE['xs'] // 2}px {SPACE['sm']}px;
    min-height: 20px;
    selection-background-color: {t.selection_bg};
    selection-color: {t.selection_text};
}}
/* Styling a spin box at all hands its whole rendering to the stylesheet, including
   the stepper — and with no sub-control rules the base style mispositioned it: the
   14x14 buttons landed on the widget's 1px border, inside the corner radius, and
   the macOS chevrons degraded into two ~2px dots. (We can't keep the native stepper
   and the themed colours: setting any property switches the widget over. The colours
   are the reason the rule exists — see the QDateEdit note above.) So place the
   buttons explicitly, inside the frame, with a divider of their own. */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QDateEdit::up-button, QDateTimeEdit::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: {SPACE['md']}px;
    margin: 1px 1px 0 0;
    border-left: 1px solid {t.border};
    border-top-right-radius: {r['sm']}px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button,
QDateEdit::down-button, QDateTimeEdit::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: {SPACE['md']}px;
    margin: 0 1px 1px 0;
    border-left: 1px solid {t.border};
    border-bottom-right-radius: {r['sm']}px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {t.surface_alt};
}}
/* Styling the buttons means Qt stops drawing their arrows and waits for these —
   without them the stepper is an empty compartment, which looks more broken than
   the mispositioned default did. */
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QDateEdit::up-arrow, QDateTimeEdit::up-arrow {{
    image: url({chevron_up_url});
    width: {SPACE['sm']}px;
    height: {SPACE['sm']}px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow,
QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{
    image: url({chevron_down_url});
    width: {SPACE['sm']}px;
    height: {SPACE['sm']}px;
}}
QSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled,
QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
    opacity: 80;
}}
/* A pop-up button is NOT a text field: macOS draws it at 32px, button height, not
   the 21px of a QLineEdit. It shares the rule above for colour and border, so put
   its height back — otherwise trimming the text fields drags the combo 6px under
   the platform and it reads as undersized next to the buttons it sits beside. */
QComboBox {{ min-height: 24px; }}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QDateTimeEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {t.focus_ring};
}}
QComboBox QAbstractItemView {{
    background-color: {t.raised};
    border: 1px solid {t.border};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}

/* ── checkboxes / groupboxes ── */
/* min-height gives the 14px indicator vertical breathing room so stacked
   checkboxes/radios don't crowd (their circles read as overlapping otherwise) —
   same reason QPushButton carries a min-height. */
QCheckBox, QRadioButton {{ spacing: {SPACE['sm']}px; min-height: 20px; }}
/* Standalone check/radio indicators — like the table indicators above, route these
   through QStyleSheetStyle so they're visible in dark mode. The native QMacStyle
   unchecked box/circle renders near-invisibly on the dark surface (dark-on-dark,
   no readable border). Keep the :checked glyph, or a stylesheet indicator draws no
   mark of its own. Offscreen paint can't catch this (Fusion fallback), so it's
   asserted on the generated QSS — per the theme gotcha. */
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {t.border};
    background-color: {t.surface};
}}
QCheckBox::indicator {{ border-radius: {r['sm']}px; }}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {t.accent}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background-color: {t.surface_alt};
    border-color: {t.divider};
}}
QCheckBox::indicator:checked {{
    background-color: {t.accent};
    border-color: {t.accent};
    image: url({check_url});
}}
QCheckBox::indicator:indeterminate {{
    background-color: {t.accent};
    border-color: {t.accent};
    image: url({dash_url});
}}
QRadioButton::indicator:checked {{
    background-color: {t.accent};
    border-color: {t.accent};
    image: url({radio_dot_url});
}}
QGroupBox {{
    border: 1px solid {t.border};
    border-radius: {r['md']}px;
    margin-top: {SPACE['md']}px;
    padding: {SPACE['sm']}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {SPACE['sm']}px;
    padding: 0 {SPACE['xs']}px;
    color: {t.text_secondary};
}}

/* ── menus ── */
QMenuBar {{ background-color: {t.window}; }}
QMenuBar::item:selected {{ background-color: {t.surface_alt}; }}
QMenu {{ background-color: {t.raised}; border: 1px solid {t.border}; }}
QMenu::item {{ padding: {SPACE['xs']}px {SPACE['lg']}px; }}
QMenu::item:selected {{ background-color: {t.accent}; color: {t.accent_text}; }}
/* Styling QMenu::item stops Qt auto-greying disabled entries, so a disabled item
   would draw at full strength and just fail to highlight (reads as "broken", not
   "unavailable"). Grey it explicitly, matching QPushButton:disabled above. */
QMenu::item:disabled {{ color: {t.text_disabled}; }}
QMenu::separator {{ height: 1px; background: {t.divider}; margin: {SPACE['xs']}px 0; }}

/* ── splitter / scrollbars ── */
QSplitter::handle {{ background-color: {t.divider}; }}
QScrollBar:vertical {{ background: {t.window}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {t.border}; border-radius: {r['sm']}px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {t.text_disabled}; }}
QScrollBar:horizontal {{ background: {t.window}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {t.border}; border-radius: {r['sm']}px; min-width: 28px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ── misc ── */
QStatusBar {{ color: {t.text_secondary}; }}
QProgressBar {{
    border: 1px solid {t.border}; border-radius: {r['sm']}px; text-align: center;
}}
QProgressBar::chunk {{ background-color: {t.accent}; }}
"""
