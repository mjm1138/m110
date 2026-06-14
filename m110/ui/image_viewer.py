"""Reusable image widgets — a self-scaling label and a gallery image viewer.

`ScalableImage` holds a source pixmap and rescales it to the widget's width on
every resize (aspect-preserved, never upscaled past native), used for the detail
hero. `ImageViewer` is a lightweight full-frame viewer with prev/next navigation
over a list of images (the detail gallery), driven by buttons or ←/→ keys.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)


class ScalableImage(QLabel):
    """A QLabel that keeps `source` scaled to its current width (aspect kept,
    capped at the image's native size and an optional max height)."""

    def __init__(self, pixmap: QPixmap, max_height: int | None = None, parent=None):
        super().__init__(parent)
        self._src = pixmap
        self._max_h = max_height
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.setMinimumHeight(1)
        self._rescale()

    def setSource(self, pixmap: QPixmap):
        self._src = pixmap
        self._rescale()

    def _rescale(self):
        if self._src is None or self._src.isNull():
            return
        avail_w = max(1, self.width())
        w = min(avail_w, self._src.width())
        scaled = self._src.scaledToWidth(w, Qt.SmoothTransformation)
        if self._max_h and scaled.height() > self._max_h:
            scaled = self._src.scaledToHeight(
                min(self._max_h, self._src.height()), Qt.SmoothTransformation)
        self.setPixmap(scaled)
        self.setMinimumHeight(scaled.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()


class ImageViewer(QDialog):
    """Full-frame viewer over a list of (label, path) images, with nav."""

    def __init__(self, items: list[tuple[str, str]], index: int = 0, parent=None):
        super().__init__(parent)
        self._items = items
        self._i = max(0, min(index, len(items) - 1))
        self.setWindowTitle("Image viewer")
        self.resize(900, 700)

        lay = QVBoxLayout(self)
        self._image = ScalableImage(QPixmap())
        self._image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        lay.addWidget(self._image, 1)

        row = QHBoxLayout()
        self._prev = QPushButton("‹ Prev")
        self._prev.clicked.connect(self.prev)
        self._caption = QLabel()
        self._caption.setAlignment(Qt.AlignCenter)
        self._caption.setStyleSheet("color:#8b949e")
        self._next = QPushButton("Next ›")
        self._next.clicked.connect(self.next)
        row.addWidget(self._prev)
        row.addWidget(self._caption, 1)
        row.addWidget(self._next)
        lay.addLayout(row)

        self._show_current()

    def _show_current(self):
        label, path = self._items[self._i]
        self._image.setSource(QPixmap(str(path)))
        self._caption.setText(f"{label} · {self._i + 1}/{len(self._items)}")
        self._prev.setEnabled(self._i > 0)
        self._next.setEnabled(self._i < len(self._items) - 1)

    def next(self):
        if self._i < len(self._items) - 1:
            self._i += 1
            self._show_current()

    def prev(self):
        if self._i > 0:
            self._i -= 1
            self._show_current()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space):
            self.next()
        elif event.key() in (Qt.Key_Left, Qt.Key_Up):
            self.prev()
        elif event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
