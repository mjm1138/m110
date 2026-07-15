"""View a saved field guide — the Markdown rendered with Qt's native
``QTextBrowser.setMarkdown`` (no external renderer/dependency), with Copy + Close.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser, QPushButton, QApplication,
)

from m110 import fieldguide


class FieldGuideDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self._path = Path(path)
        self.setWindowTitle(self._path.name)
        self.resize(640, 560)
        lay = QVBoxLayout(self)

        self._view = QTextBrowser()
        self._view.setOpenExternalLinks(True)
        try:
            self._view.setMarkdown(fieldguide.read(self._path))
        except OSError as exc:
            self._view.setPlainText(f"Couldn't read this field guide:\n{exc}")
        lay.addWidget(self._view)

        btns = QHBoxLayout()
        copy = QPushButton("Copy")
        copy.clicked.connect(self._copy)
        btns.addWidget(copy)
        btns.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        lay.addLayout(btns)

    def _copy(self):
        try:
            QApplication.clipboard().setText(fieldguide.read(self._path))
        except OSError:
            pass
