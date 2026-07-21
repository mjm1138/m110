"""Reusable image widgets — a self-scaling label, a zoomable/pannable viewport,
and a gallery image viewer.

`ScalableImage` holds a source pixmap and rescales it to the widget's width on
every resize (aspect-preserved, never upscaled past native), used for the detail
hero. `ZoomableImage` is the viewer's display widget — fit-to-window or an
explicit zoom level, with click-drag panning once the content exceeds the
viewport. `ImageViewer` is a full-frame viewer with prev/next navigation over a
list of images (the detail gallery or the Media page), zoom controls, an
optional per-image metadata overlay (only for callers that supply one), and
keyboard shortcuts. The metadata *content* is assembled by callers (e.g.
`detail.py`) — this module stays app-data-agnostic.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import (
    QColor, QGuiApplication, QKeySequence, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout,
)

from m110.ui import theme


class ScalableImage(QLabel):
    """A QLabel that rescales `source` to its current size, aspect preserved,
    never upscaled past native.

    `fit="width"` (the detail hero): height follows the width; the label claims
    that height (min-height), so a vertical layout shows it fully. An optional
    `max_height` caps a tall image.
    `fit="both"` (the viewer): scales into the available box in *both* dimensions
    and claims no minimum size — so the window can be resized smaller in either
    direction (and never forces the dialog larger than the screen)."""

    def __init__(self, pixmap: QPixmap, max_height: int | None = None,
                 fit: str = "width", parent=None):
        super().__init__(parent)
        self._src = pixmap
        self._max_h = max_height
        self._fit = fit
        self.setAlignment(Qt.AlignCenter)
        if fit == "both":
            self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            self.setMinimumSize(1, 1)
        else:
            self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
            self.setMinimumHeight(1)
        self._rescale()

    def setSource(self, pixmap: QPixmap):
        self._src = pixmap
        self._rescale()

    def _rescale(self):
        if self._src is None or self._src.isNull():
            self.clear()
            return
        if self._fit == "both":
            w = max(1, min(self.width(), self._src.width()))
            h = max(1, min(self.height(), self._src.height()))
            scaled = self._src.scaled(w, h, Qt.KeepAspectRatio,
                                      Qt.SmoothTransformation)
            self.setPixmap(scaled)
            return
        w = min(max(1, self.width()), self._src.width())
        scaled = self._src.scaledToWidth(w, Qt.SmoothTransformation)
        if self._max_h and scaled.height() > self._max_h:
            scaled = self._src.scaledToHeight(
                min(self._max_h, self._src.height()), Qt.SmoothTransformation)
        self.setPixmap(scaled)
        self.setMinimumHeight(scaled.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()


class ZoomableImage(QScrollArea):
    """Fit-to-window or explicit-zoom display for the viewer, with click-drag
    panning once the content exceeds the viewport. Zoom is a ratio of native
    resolution (1.0 = 100%); `None` means Fit, which recomputes on resize and
    never upscales past native (mirrors `ScalableImage`'s `fit="both"`).

    Panning is done via an event filter on the viewport, not overridden mouse
    events on the scroll area itself — `QScrollArea` routes mouse input through
    its viewport child widget."""

    zoomChanged = Signal(float)   # effective ratio, emitted whenever it changes

    _STEP = 1.25
    _MIN_ZOOM = 0.05
    _MAX_ZOOM = 8.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._src = QPixmap()
        self._zoom: float | None = None   # None = Fit
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self.setWidget(self._label)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignCenter)
        self.setFrameShape(QScrollArea.NoFrame)
        # QAbstractScrollArea otherwise claims arrow/Home/End/Space keys for its
        # own scrolling before ImageViewer.keyPressEvent ever sees them (panning
        # here is drag-based, not keyboard-based) — never take keyboard focus, so
        # those keys always propagate up to the dialog.
        self.setFocusPolicy(Qt.NoFocus)
        self._dragging = False
        self._drag_origin = None
        self._scroll_origin = (0, 0)
        self.viewport().installEventFilter(self)
        self._apply()

    def setSource(self, pixmap: QPixmap):
        self._src = pixmap
        self._zoom = None      # always land on Fit for a new image
        self._apply()

    def set_zoom(self, zoom: float | None):
        self._zoom = (None if zoom is None
                      else max(self._MIN_ZOOM, min(self._MAX_ZOOM, zoom)))
        self._apply()

    def zoom_in(self):
        self.set_zoom(self.current_zoom() * self._STEP)

    def zoom_out(self):
        self.set_zoom(self.current_zoom() / self._STEP)

    def is_fit(self) -> bool:
        return self._zoom is None

    def current_zoom(self) -> float:
        """Effective ratio right now (the computed fit ratio if in Fit mode)."""
        if self._zoom is not None:
            return self._zoom
        if self._src.isNull() or not self._src.width():
            return 1.0
        w = max(1, min(self.viewport().width(), self._src.width()))
        return w / self._src.width()

    def _apply(self):
        if self._src.isNull():
            self._label.clear()
            return
        if self._zoom is None:
            w = max(1, min(self.viewport().width(), self._src.width()))
            h = max(1, min(self.viewport().height(), self._src.height()))
        else:
            size = self._src.size() * self._zoom
            w, h = max(1, size.width()), max(1, size.height())
        scaled = self._src.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())
        eff = scaled.width() / self._src.width() if self._src.width() else 1.0
        self.zoomChanged.emit(eff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.is_fit():
            self._apply()

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            et = event.type()
            if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._dragging = True
                self._drag_origin = event.position().toPoint()
                self._scroll_origin = (self.horizontalScrollBar().value(),
                                        self.verticalScrollBar().value())
                self.viewport().setCursor(Qt.ClosedHandCursor)
            elif et == QEvent.MouseMove and self._dragging:
                delta = event.position().toPoint() - self._drag_origin
                self.horizontalScrollBar().setValue(self._scroll_origin[0] - delta.x())
                self.verticalScrollBar().setValue(self._scroll_origin[1] - delta.y())
            elif et == QEvent.MouseButtonRelease and self._dragging:
                self._dragging = False
                self.viewport().unsetCursor()
        return super().eventFilter(obj, event)


class ImageViewer(QDialog):
    """Full-frame viewer over a list of images, with zoom/pan + nav.

    Each item is either a `(name, path)` tuple (no metadata — e.g. the Media
    page) or a `{"name", "path", "meta": {...}}` dict (e.g. the object
    gallery, `meta` a display-ready key→value mapping). An Info toggle only
    appears when at least one item actually carries metadata."""

    def __init__(self, items, index: int = 0, parent=None, *, export_stem=None):
        super().__init__(parent)
        self._items = [self._normalize(it) for it in items]
        self._i = max(0, min(index, len(self._items) - 1))
        self._export_stem = export_stem   # object name for export filenames, if known
        self.setWindowTitle("Image viewer")
        # Open at a sensible size that always fits the screen; freely resizable.
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(320, 240)
        self.resize(min(1000, int(avail.width() * 0.8)),
                    min(780, int(avail.height() * 0.8)))

        lay = QVBoxLayout(self)
        self._image = ZoomableImage()
        lay.addWidget(self._image, 1)

        self._info_panel = QLabel(self._image)
        self._info_panel.setTextFormat(Qt.RichText)
        self._info_panel.hide()

        zoom_row = QHBoxLayout()
        self._fit_btn = QPushButton("Fit")
        self._fit_btn.setToolTip("Fit to window (0)")
        self._fit_btn.clicked.connect(lambda: self._image.set_zoom(None))
        self._100_btn = QPushButton("100%")
        self._100_btn.setToolTip("Actual size (1)")
        self._100_btn.clicked.connect(lambda: self._image.set_zoom(1.0))
        self._zoom_out_btn = QPushButton("−")
        self._zoom_out_btn.setToolTip("Zoom out (-)")
        self._zoom_out_btn.clicked.connect(self._image.zoom_out)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setProperty("muted", True)
        self._zoom_label.setAlignment(Qt.AlignCenter)
        self._zoom_label.setMinimumWidth(44)
        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setToolTip("Zoom in (+)")
        self._zoom_in_btn.clicked.connect(self._image.zoom_in)
        self._image.zoomChanged.connect(self._on_zoom_changed)
        zoom_row.addWidget(self._fit_btn)
        zoom_row.addWidget(self._100_btn)
        zoom_row.addWidget(self._zoom_out_btn)
        zoom_row.addWidget(self._zoom_label)
        zoom_row.addWidget(self._zoom_in_btn)
        zoom_row.addStretch(1)

        self._info_btn = None
        if any(it["meta"] for it in self._items):
            self._info_btn = QPushButton("ⓘ Info")
            self._info_btn.setToolTip("Toggle image details (I)")
            self._info_btn.setCheckable(True)
            self._info_btn.toggled.connect(lambda _checked: self._refresh_info_panel())
            zoom_row.addWidget(self._info_btn)

        self._export_btn = QPushButton("⤓ Export…")
        self._export_btn.setToolTip("Export this image sized for web sharing")
        self._export_btn.clicked.connect(self._export_current)
        zoom_row.addWidget(self._export_btn)
        lay.addLayout(zoom_row)

        nav_row = QHBoxLayout()
        self._prev = QPushButton("‹ Prev")
        self._prev.clicked.connect(self.prev)
        self._caption = QLabel()
        self._caption.setAlignment(Qt.AlignCenter)
        self._caption.setProperty("muted", True)
        self._next = QPushButton("Next ›")
        self._next.clicked.connect(self.next)
        nav_row.addWidget(self._prev)
        nav_row.addWidget(self._caption, 1)
        nav_row.addWidget(self._next)
        lay.addLayout(nav_row)

        # Cmd+W / Ctrl+W closes the viewer; Cmd+Q / Ctrl+Q still quits the app
        # (a modal exec() loop would otherwise swallow the quit shortcut).
        QShortcut(QKeySequence.StandardKey.Close, self).activated.connect(self.close)
        QShortcut(QKeySequence.StandardKey.Quit, self).activated.connect(self._quit_app)

        # None of these buttons represents a persistent "selected" state (zoom is
        # continuous, nav is momentary) — without this, Qt auto-picks the first
        # button (Fit) as the dialog's default button and gives it a permanent
        # emphasized outline, which reads as "Fit is active" even when it isn't.
        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False)
            b.setDefault(False)

        # Keep keyboard focus on the dialog itself (not a button, not the
        # scroll area) so arrow/space/nav keys reliably reach keyPressEvent.
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

        self._show_current()

    @staticmethod
    def _normalize(it) -> dict:
        if isinstance(it, dict):
            return {"name": it.get("name", ""), "path": it["path"],
                    "meta": it.get("meta") or {}}
        name, path = it
        return {"name": name, "path": path, "meta": {}}

    def _quit_app(self):
        self.close()
        app = QGuiApplication.instance()
        if app is not None:
            app.quit()

    def _export_current(self):
        it = self._items[self._i]
        if not it.get("path"):
            return
        from m110.ui.export_dialog import ExportShareDialog   # lazy: avoid cycle
        stem = self._export_stem or Path(it["name"]).stem or None
        ExportShareDialog(it["path"], self, default_stem=stem).exec()

    def _show_current(self):
        it = self._items[self._i]
        self._image.setSource(QPixmap(str(it["path"])))
        self._caption.setText(f"{it['name']} · {self._i + 1}/{len(self._items)}")
        self._prev.setEnabled(self._i > 0)
        self._next.setEnabled(self._i < len(self._items) - 1)
        self._refresh_info_panel()

    def next(self):
        if self._i < len(self._items) - 1:
            self._i += 1
            self._show_current()

    def prev(self):
        if self._i > 0:
            self._i -= 1
            self._show_current()

    # ---- zoom readout ----
    def _on_zoom_changed(self, z: float):
        self._zoom_label.setText(f"{round(z * 100)}%")

    # ---- metadata overlay ----
    def _refresh_info_panel(self):
        if self._info_btn is None:
            return
        meta = self._items[self._i]["meta"]
        if not (self._info_btn.isChecked() and meta):
            self._info_panel.hide()
            return
        t = theme.active_tokens()
        bg = QColor(t.raised)
        pad = theme.tokens.SPACE["sm"]
        self._info_panel.setStyleSheet(
            f"background-color: rgba({bg.red()},{bg.green()},{bg.blue()},0.92); "
            f"color:{t.text_primary}; border: 1px solid {t.border}; "
            f"border-radius: {theme.tokens.RADIUS['md']}px; "
            f"padding: {pad}px {pad + 4}px;")
        self._info_panel.setText(
            "<br>".join(f"<b>{k}:</b> {v}" for k, v in meta.items()))
        self._info_panel.adjustSize()
        self._position_info_panel()
        self._info_panel.show()

    def _position_info_panel(self):
        # Bottom-right — the same side as the Info toggle in the zoom row above,
        # so the popover reads as belonging to that button.
        m = 12
        x = self._image.width() - self._info_panel.width() - m
        y = self._image.height() - self._info_panel.height() - m
        self._info_panel.move(max(m, x), max(m, y))
        self._info_panel.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._info_panel.isVisible():
            self._position_info_panel()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space):
            self.next()
        elif key in (Qt.Key_Left, Qt.Key_Up):
            self.prev()
        elif key == Qt.Key_Home:
            self._i = 0
            self._show_current()
        elif key == Qt.Key_End:
            self._i = len(self._items) - 1
            self._show_current()
        elif key in (Qt.Key_Plus, Qt.Key_Equal):
            self._image.zoom_in()
        elif key == Qt.Key_Minus:
            self._image.zoom_out()
        elif key == Qt.Key_0:
            self._image.set_zoom(None)
        elif key == Qt.Key_1:
            self._image.set_zoom(1.0)
        elif key == Qt.Key_I and self._info_btn is not None:
            self._info_btn.toggle()
        elif key == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
