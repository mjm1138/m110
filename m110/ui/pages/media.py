"""Media page — browse non-catalog media (lunar/planetary/scenery) that ingest
drops into `Media/<Category>_photo|_video/`. Photos open in the image viewer;
videos open in the OS default player. Read-only."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QListWidget, QListWidgetItem, QPushButton,
)

from m110 import media
from m110.ui.image_viewer import ImageViewer


def _fmt_size(n: int) -> str:
    mb = n / (1024 ** 2)
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB" if mb >= 1 \
        else f"{n / 1024:.0f} KB"


class MediaPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignTop)

        title = QLabel("<h2>Media</h2>")
        title.setTextFormat(Qt.RichText)
        outer.addWidget(title)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        outer.addWidget(self._search)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, 1)

        self._sections: list[tuple[QWidget, str]] = []   # (widget, haystack)
        self._galleries: list[tuple[QListWidget, list]] = []
        self.reload()

    def _clear(self):
        self._sections.clear()
        self._galleries.clear()
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()

    def section_count(self) -> int:
        return len(self._sections)

    def reload(self):
        self._clear()
        cats = media.scan()
        for c in cats:
            self._add_section(c)
        if not cats:
            self._lay.addWidget(QLabel(
                "<i>No media yet — ingest lunar/planetary/scenery "
                "photos or videos.</i>"))
        self._lay.addStretch(1)
        self._apply_filter()

    def _add_section(self, c: dict):
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 8)
        head = QLabel(f"<b>{c['category']}</b> · {len(c['items'])} {c['kind']}"
                      f"{'s' if len(c['items']) != 1 else ''}")
        head.setTextFormat(Qt.RichText)
        bl.addWidget(head)

        if c["kind"] == "photo":
            gallery = QListWidget()
            gallery.setViewMode(QListWidget.IconMode)
            gallery.setIconSize(QSize(160, 160))
            gallery.setResizeMode(QListWidget.Adjust)
            gallery.setMovement(QListWidget.Static)
            gallery.setSpacing(6)
            gallery.setMinimumHeight(200)
            paths = []
            for it in c["items"]:
                gallery.addItem(QListWidgetItem(QIcon(str(it["path"])), it["name"]))
                paths.append((it["name"], str(it["path"])))
            gallery.itemDoubleClicked.connect(
                lambda item, g=gallery, ps=paths: self._open(g, ps, item))
            self._galleries.append((gallery, paths))
            bl.addWidget(gallery)
        else:                                            # video → open externally
            for it in c["items"]:
                row = QHBoxLayout()
                row.addWidget(QLabel(it["name"]))
                sz = QLabel(_fmt_size(it["size_bytes"]))
                sz.setStyleSheet("color:#8b949e")
                row.addWidget(sz)
                row.addStretch(1)
                btn = QPushButton("Open")
                btn.setToolTip("Open in your default video player")
                btn.clicked.connect(
                    lambda _=False, p=str(it["path"]): QDesktopServices.openUrl(
                        QUrl.fromLocalFile(p)))
                row.addWidget(btn)
                bl.addLayout(row)

        self._lay.addWidget(box)
        hay = (c["category"] + " " + c["kind"] + " "
               + " ".join(i["name"] for i in c["items"])).lower()
        self._sections.append((box, hay))

    def _open(self, gallery, paths, item):
        row = gallery.row(item)
        if 0 <= row < len(paths):
            ImageViewer(list(paths), row, parent=self).exec()

    def _apply_filter(self):
        q = self._search.text().strip().lower()
        for box, hay in self._sections:
            box.setVisible(q in hay if q else True)
