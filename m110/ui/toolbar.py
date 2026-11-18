"""The header bar — the window's toolbar (UI_ROADMAP → 1.0 redesign → Toolbar).

Left: the current place's **title** (Newsreader) and **subtitle** ("65 objects ·
316.8 h"). Right: that page's own controls — view switcher, catalog picker, search —
which each page builds as `header_controls` and the shell hands over here when the
page is shown. One bar, contents swapped per place; the stacked control rows that
sat above the Library grid are gone.

Why not `QToolBar` + `setUnifiedTitleAndToolBarOnMac`: prototyped on cocoa
(2026-11-17), Qt 6 draws the unified toolbar *below* a separate native title strip
(light, when the app theme is dark) and every embedded widget paints its own
background, so it reads as two bars. Instead the window extends its content under
the title bar (`Qt.ExpandedClientAreaHint`, Qt ≥ 6.9, macOS) and this bar sits at
the very top beside a full-height sidebar, with the traffic lights over the
sidebar — the layout of Finder, Mail or Photos. Off macOS (or on older Qt) the
platform title bar stays and this is simply the first row of the window.

Because the bar now occupies the title-bar area, it is also the window's drag
handle: pressing on empty bar starts a system move, and double-clicking zooms.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from m110.ui import theme
from m110.ui.theme import icons
from m110.ui.theme.fonts import serif_font
from m110.ui.theme.tokens import FONT_SIZE, SPACE

HEIGHT = 52                  # a macOS unified toolbar with a title + subtitle
TRAFFIC_LIGHT_INSET = 78     # clear of the window buttons when the sidebar is hidden


class DragArea(QWidget):
    """A patch of window chrome that moves the window when dragged (and zooms on
    double-click), for the parts of the title-bar band we draw ourselves."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_empty(event):
            handle = self.window().windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_empty(event):
            w = self.window()
            w.showNormal() if w.isMaximized() else w.showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _on_empty(self, event) -> bool:
        child = self.childAt(event.position().toPoint())
        return child is None or isinstance(child, QLabel)


class HeaderBar(DragArea):
    """Title + subtitle on the left, the current page's controls on the right."""

    toggle_sidebar = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("headerBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(HEIGHT)
        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE["md"], 0, SPACE["md"], 0)
        row.setSpacing(SPACE["sm"])

        self.sidebar_btn = QToolButton()
        self.sidebar_btn.setObjectName("headerButton")
        self.sidebar_btn.setToolTip("Show or hide the sidebar")
        self.sidebar_btn.setAccessibleName("Toggle Sidebar")
        self.sidebar_btn.setAutoRaise(True)
        self.sidebar_btn.clicked.connect(self.toggle_sidebar)
        row.addWidget(self.sidebar_btn)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(0)
        self.title = QLabel()
        self.title.setObjectName("headerTitle")
        self.title.setProperty("type", "heading")
        self.title.setFont(serif_font(FONT_SIZE["heading"]))
        self.subtitle = QLabel()
        self.subtitle.setObjectName("headerSubtitle")
        self.subtitle.setProperty("caption", True)
        titles.addStretch(1)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        titles.addStretch(1)
        row.addLayout(titles)
        row.addStretch(1)

        self._controls_row = QHBoxLayout()
        self._controls_row.setContentsMargins(0, 0, 0, 0)
        self._controls_row.setSpacing(SPACE["sm"])
        row.addLayout(self._controls_row)
        self._adopted: list[QWidget] = []
        self._current: QWidget | None = None
        self.title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.restyle()

    # ---- content ----
    def adopt(self, controls: QWidget) -> None:
        """Take ownership of a page's `header_controls` (hidden until shown)."""
        if controls in self._adopted:
            return
        controls.setParent(self)
        controls.hide()
        self._controls_row.addWidget(controls)
        self._adopted.append(controls)

    def set_place(self, title: str, subtitle: str = "",
                  controls: QWidget | None = None) -> None:
        self.title.setText(title)
        self.set_subtitle(subtitle)
        if self._current is not None and self._current is not controls:
            self._current.hide()
        if controls is not None:
            self.adopt(controls)
            controls.show()
        self._current = controls

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))

    def current_controls(self) -> QWidget | None:
        return self._current

    def set_leading_inset(self, px: int) -> None:
        """Room for the window buttons when nothing else (the sidebar) clears them."""
        m = self.layout().contentsMargins()
        self.layout().setContentsMargins(SPACE["md"] + px, m.top(), m.right(), m.bottom())

    def restyle(self) -> None:
        self.sidebar_btn.setIcon(icons.icon("panel-left", "text_secondary"))
        _ = theme  # icons follow the active tokens
