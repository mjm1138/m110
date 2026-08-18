"""Detail pane for one media file — the Media scope's counterpart to
`detail.DetailPane`.

Deliberately much smaller than the object detail pane: a media file has no
journal, no sessions and no processing state, so this is a preview plus the file
facts plus the three things you actually want to do with it (open it, find it on
disk, export a copy). Kept in its own module rather than bolted onto `detail.py`,
which is entirely catalog-object-shaped.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from m110 import media
from m110.ui.image_viewer import ScalableImage
from m110.ui.theme.tokens import SPACE
from m110.ui.widgets import defer, open_in_default, reveal_in_manager

_PREVIEW_MAX_H = 320


def fmt_size(n: int) -> str:
    mb = n / (1024 ** 2)
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    if mb >= 1:
        return f"{mb:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} bytes"


def fmt_date(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return ""


class MediaDetailPane(QWidget):
    """Preview + facts + actions for the selected media item.

    `open_requested` lets the host decide *how* to open (the page opens photos in
    the shared `ImageViewer` positioned within the current filtered set, which
    only the page knows); videos are handed straight to the OS player here.
    """

    open_requested = Signal(object)      # MediaItem
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._item: media.MediaItem | None = None

        lay = QVBoxLayout(self)
        # Side margins only — the pane sits hard against the splitter handle on
        # the left and the window edge on the right, and with zero margins the
        # title, the ✕ and the action row all butt into them. Top/bottom stay 0
        # so the title still lines up with the list's own first row.
        lay.setContentsMargins(SPACE["sm"], 0, SPACE["sm"], 0)

        head = QHBoxLayout()
        self._title = QLabel()
        self._title.setTextFormat(Qt.RichText)
        self._title.setWordWrap(True)
        head.addWidget(self._title, 1)
        close = QPushButton("✕")
        close.setToolTip("Close")
        close.setFixedWidth(28)
        close.clicked.connect(self.closed)
        head.addWidget(close)
        lay.addLayout(head)

        # The preview is swapped rather than repainted: `ScalableImage` holds its
        # source and refits on every resize, so the preview tracks the splitter
        # instead of sitting at one baked-in size.
        self._preview_box = QVBoxLayout()
        self._preview_box.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._preview_box)

        self._facts = QFormLayout()
        self._facts.setLabelAlignment(Qt.AlignRight)
        lay.addLayout(self._facts)

        btns = QHBoxLayout()
        self._open_btn = QPushButton("Open")
        self._open_btn.clicked.connect(self._on_open)
        self._reveal_btn = QPushButton("Reveal")
        self._reveal_btn.setToolTip("Show this file in the file manager")
        self._reveal_btn.clicked.connect(self._on_reveal)
        self._export_btn = QPushButton("Export…")
        self._export_btn.setToolTip("Export a shareable copy")
        self._export_btn.clicked.connect(self.export_current)
        for b in (self._open_btn, self._reveal_btn, self._export_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)
        lay.addStretch(1)

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    # ---- content ----
    def show_item(self, item: media.MediaItem | None):
        self._item = item
        while self._facts.count():
            w = self._facts.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        if item is None:
            self._title.clear()
            self._set_preview(None)
            for b in (self._open_btn, self._reveal_btn, self._export_btn):
                b.setEnabled(False)
            return

        self._title.setText(f"<b>{item.name}</b>")
        poster = media.poster_for(item)
        self._set_preview(poster)

        rows = [("Category", item.category),
                ("Kind", "Video" if item.kind == "video" else "Photo"),
                ("Date", fmt_date(item.captured)),
                ("Size", fmt_size(item.size_bytes))]
        if item.subfolder:
            rows.insert(1, ("Folder", item.subfolder))
        dims = self._dimensions(poster if item.kind == "video" else item.path)
        if dims:
            rows.append(("Dimensions", dims))
        for label, value in rows:
            if not value:
                continue
            v = QLabel(str(value))
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._facts.addRow(QLabel(label), v)

        self._open_btn.setEnabled(True)
        self._open_btn.setText("Play" if item.kind == "video" else "Open")
        self._reveal_btn.setEnabled(True)
        # Export renders through the image pipeline, so it needs a still.
        self._export_btn.setEnabled(item.kind == "photo")

    def _set_preview(self, poster: Path | None):
        while self._preview_box.count():
            w = self._preview_box.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        if poster is None or not Path(poster).is_file():
            return
        pm = QPixmap(str(poster))
        if pm.isNull():
            return
        self._preview_box.addWidget(
            ScalableImage(pm, max_height=_PREVIEW_MAX_H, fit="width"))

    @staticmethod
    def _dimensions(path: Path | None) -> str:
        if path is None:
            return ""
        size = QImageReader(str(path)).size()
        return f"{size.width()} × {size.height()}" if size.isValid() else ""

    # ---- actions ----
    def _on_open(self):
        if self._item is None:
            return
        if self._item.kind == "video":
            open_in_default(self._item.path)
        else:
            self.open_requested.emit(self._item)

    def _on_reveal(self):
        if self._item is not None:
            reveal_in_manager(self._item.path)

    def export_current(self):
        """Export the shown item — also the page's right-click entry point."""
        if self._item is None or self._item.kind != "photo":
            return
        item = self._item                       # snapshot: a reload may land first
        def run():
            from m110.ui.export_dialog import ExportShareDialog
            ExportShareDialog(item.path, parent=self,
                              default_stem=item.path.stem).exec()
        defer(self, run)
