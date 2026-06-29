"""Journal page — a reverse-chronological feed of object cards.

Every captured object gets a card (header · hero · stats · rendered notes if any),
plus any non-captured object with real journal notes. Ordered by latest image
activity (finished/processed render or in-device stack mtime; reprocessing
re-orders to the top). Cards link to the Catalog detail via `open_object`."""
from __future__ import annotations

import re
import time
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QFrame, QPushButton, QTextBrowser,
)

from m110 import config, derived, objects, catalog
from m110.ui.widgets import status_label

_HEADING_LINE_RE = re.compile(r"(?m)^\s{0,3}#.*$")   # a whole ATX heading line
_THUMB_W = 220


def _body_markdown(body: str) -> str | None:
    """Rendered journal markdown if there's content beyond headings/whitespace,
    else None (a fresh stub has only its `# id — name` heading + a comment that
    `journal_to_markdown` strips)."""
    md = objects.journal_to_markdown(body or "")
    leftover = _HEADING_LINE_RE.sub("", md)   # drop heading lines entirely
    return md if leftover.strip() else None


def _date_epoch(d: str) -> float:
    try:
        return time.mktime(datetime.strptime(d, "%Y-%m-%d").timetuple())
    except Exception:
        return 0.0


class JournalPage(QWidget):
    open_object = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignTop)

        title = QLabel("<h2>Journal</h2>")
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

        self._cards: list[tuple[QFrame, str]] = []   # (card, haystack)
        self.reload()

    def _clear(self):
        self._cards.clear()
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()

    def card_count(self) -> int:
        return len(self._cards)

    def reload(self):
        self._clear()
        bs = derived.totals_by_slug()
        cat = catalog.load_library()

        entries: list[tuple[float, str]] = []
        for slug in bs:
            imgs = derived.images_for(slug)
            key = imgs[0].get("mtime", 0.0) if imgs else _date_epoch(
                bs[slug].get("last_capture", ""))
            entries.append((key, slug))
        for slug in cat:
            if slug in bs:
                continue
            _, body = objects.read_journal(slug)
            if _body_markdown(body):
                jp = objects.journal_path(slug)
                key = jp.stat().st_mtime if jp.is_file() else 0.0
                entries.append((key, slug))
        entries.sort(key=lambda x: x[0], reverse=True)

        for _, slug in entries:
            self._add_card(slug, cat.get(slug, {}), bs.get(slug))

        if not self._cards:
            self._lay.addWidget(QLabel("<i>No captured objects or notes yet.</i>"))
        self._lay.addStretch(1)
        self._apply_filter()

    def _add_card(self, slug, entry, totals):
        oid = entry.get("id", slug)
        name = entry.get("name", "")
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        cl = QVBoxLayout(card)

        head = QPushButton(f"{oid} — {name}" if name else oid)
        head.setStyleSheet("text-align:left; font-weight:bold; border:none;")
        head.setCursor(Qt.PointingHandCursor)
        head.clicked.connect(lambda _=False, s=slug: self.open_object.emit(s))
        cl.addWidget(head)

        body_row = QHBoxLayout()
        hp = objects.hero_path(slug)
        if hp and hp.is_file():
            pm = QPixmap(str(hp))
            if not pm.isNull():
                thumb = QLabel()
                thumb.setPixmap(pm.scaledToWidth(
                    _THUMB_W, Qt.SmoothTransformation))
                thumb.setAlignment(Qt.AlignTop)
                body_row.addWidget(thumb, 0)

        right = QVBoxLayout()
        if totals:
            captured = True
            stats = " · ".join(filter(None, [
                status_label(totals.get("status"), captured),
                f"{totals.get('integration_hms', '')} integration"
                if totals.get("integration_hms") else "",
                f"last capture {totals.get('last_capture')}"
                if totals.get("last_capture") else "",
            ]))
            sl = QLabel(stats)
            sl.setProperty("muted", True)
            right.addWidget(sl)

        _, raw_body = objects.read_journal(slug)
        md = _body_markdown(raw_body)
        if md:
            tb = QTextBrowser()
            tb.setMarkdown(md)
            tb.setOpenExternalLinks(True)
            tb.setMaximumHeight(220)
            right.addWidget(tb)
        right.addStretch(1)
        body_row.addLayout(right, 1)
        cl.addLayout(body_row)

        self._lay.addWidget(card)
        hay = f"{oid} {name} {md or ''}".lower()
        self._cards.append((card, hay))

    def _apply_filter(self):
        q = self._search.text().strip().lower()
        for card, hay in self._cards:
            card.setVisible(q in hay if q else True)
