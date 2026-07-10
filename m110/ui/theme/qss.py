"""Generate the app-wide Qt stylesheet from a `Tokens` palette.

One `build_qss(tokens)` produces the whole sheet; the manager installs it via
`app.setStyleSheet`, so every window/dialog inherits it. Selectors are kept broad
and token-driven — page-level polish (pill chips, alt rows, row heights) is Phase 1.
"""
from __future__ import annotations

from .tokens import FONT_SIZE, RADIUS, SPACE, Tokens


def build_qss(t: Tokens) -> str:
    r = RADIUS
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
#segControl QToolButton#segButton {{
    border: 1px solid {t.border};
    border-left-width: 0px;             /* shared edges collapse to one line */
    border-radius: 0px;
    padding: 3px 12px;
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

/* ── nav rail (left) ── */
QListWidget#navRail {{
    background-color: {t.surface};
    border: none;
    border-right: 1px solid {t.border};
    padding-top: {SPACE['sm']}px;
}}
QListWidget#navRail::item {{
    padding: {SPACE['sm']}px {SPACE['md']}px;
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
QTableView::item, QTableWidget::item {{ padding: {SPACE['xs']}px {SPACE['sm']}px; }}
QHeaderView::section {{
    background-color: {t.surface_alt};
    color: {t.text_secondary};
    padding: {SPACE['xs']}px {SPACE['sm']}px;
    border: none;
    border-bottom: 1px solid {t.border};
    border-right: 1px solid {t.divider};
}}
QTableCornerButton::section {{ background-color: {t.surface_alt}; border: none; }}

/* ── buttons ── */
QPushButton {{
    background-color: {t.surface};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: {r['sm']}px;
    padding: {SPACE['xs']}px {SPACE['md']}px;
    /* Guarantee vertical room for the label — a styled QPushButton in a tight
       layout (esp. on macOS) otherwise clips its text top-and-bottom. */
    min-height: {SPACE['xl'] - SPACE['xs']}px;
}}
QPushButton:hover {{ background-color: {t.surface_alt}; }}
QPushButton:pressed {{ background-color: {t.selection_bg}; }}
QPushButton:default {{ border-color: {t.accent}; }}
QPushButton:disabled {{ color: {t.text_disabled}; border-color: {t.divider}; }}

/* ── inputs ── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {t.surface};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: {r['sm']}px;
    padding: {SPACE['xs']}px {SPACE['sm']}px;
    selection-background-color: {t.selection_bg};
    selection-color: {t.selection_text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {t.focus_ring};
}}
QComboBox QAbstractItemView {{
    background-color: {t.raised};
    border: 1px solid {t.border};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}

/* ── checkboxes / groupboxes ── */
QCheckBox {{ spacing: {SPACE['sm']}px; }}
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
