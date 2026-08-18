"""Reusable image-grid component — a generic tile-per-item grid (thumbnail +
title + optional subtitle + optional status chip), zoomable via tile size.

No imports from `m110.catalog`/`m110.objects`/`m110.derived` — this module
knows nothing about catalog objects. The first consumer (`m110/ui/pages/
catalog.py`, the Library grid) adapts its own data into `TileItem`; a future
cross-object image browser (UI_ROADMAP Phase 4+) can reuse `TileModel`/
`TileDelegate` as-is for a different dataset.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
)

from m110.ui import theme
from m110.ui.theme import active_tokens, muted_color, status_color
from m110.ui.widgets import ThumbnailLoader, paint_status_chip, status_label

# Tile (zoom) size bounds, shared by every consumer of this grid.
GRID_ZOOM_MIN = 80
GRID_ZOOM_MAX = 220
GRID_ZOOM_DEFAULT = 140

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
STATUS_ROLE = Qt.ItemDataRole.UserRole + 2
SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 3
MUTED_ROLE = Qt.ItemDataRole.UserRole + 4
BADGE_ROLE = Qt.ItemDataRole.UserRole + 5


@dataclass
class TileItem:
    """One tile's display data. `key` is an opaque identity (e.g. a catalog
    slug) — callers use it to map a tile back to their own model."""
    key: str
    thumb_path: Path | None
    title: str
    subtitle: str = ""
    status: str | None = None
    muted: bool = False
    badge: str = ""     # short glyph drawn over the thumbnail (e.g. "\u25b6" for video)


class TileModel(QAbstractListModel):
    """A flat list of `TileItem` with async thumbnail loading wired through a
    shared `ThumbnailLoader` (the "square" crop tuning — tiles are big enough
    to keep more of the frame than the row-icon crop)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[TileItem] = []
        self._pixmaps: dict[str, QPixmap] = {}   # key -> decoded thumbnail

    def set_items(self, items: list[TileItem]):
        self.beginResetModel()
        self._items = list(items)
        keys = {it.key for it in self._items}
        self._pixmaps = {k: v for k, v in self._pixmaps.items() if k in keys}
        self.endResetModel()

    def items(self) -> list[TileItem]:
        return self._items

    def index_of(self, key: str) -> QModelIndex:
        for row, it in enumerate(self._items):
            if it.key == key:
                return self.index(row)
        return QModelIndex()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        it = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return it.title
        if role == Qt.ItemDataRole.DecorationRole:
            return self._pixmaps.get(it.key)
        if role == KEY_ROLE:
            return it.key
        if role == STATUS_ROLE:
            return it.status
        if role == SUBTITLE_ROLE:
            return it.subtitle
        if role == MUTED_ROLE:
            return it.muted
        if role == BADGE_ROLE:
            return it.badge
        return None

    def request_thumbnails(self, loader: ThumbnailLoader, size: int):
        """Kick off async decodes for every item with a thumbnail source.
        Call after `set_items()` and again whenever the tile (zoom) size
        changes — cache hits for a previously-seen size return instantly."""
        for it in self._items:
            if it.thumb_path is None:
                continue
            loader.request(it.thumb_path, size,
                            lambda pm, key=it.key: self._on_thumb(key, pm),
                            crop="square")

    def _on_thumb(self, key: str, pm):
        if pm is None:
            return
        idx = self.index_of(key)
        if not idx.isValid():
            return   # a stale callback landed after set_items() dropped this key
        self._pixmaps[key] = pm
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])


class TileDelegate(QStyledItemDelegate):
    """Paints one tile: a square thumbnail (or a muted placeholder), an
    elided title, and a status-chip + subtitle line. Colors/spacing all come
    from the active theme; `set_tile_size` drives the zoom slider."""

    def __init__(self, tile_size: int, parent=None):
        super().__init__(parent)
        self._tile_size = tile_size

    def set_tile_size(self, size: int):
        self._tile_size = size

    def sizeHint(self, option, index):
        s = theme.tokens.SPACE
        text_h = option.fontMetrics.height() * 2 + s["xs"]
        side = self._tile_size + s["sm"] * 2
        return QSize(side, side + text_h)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        title = index.data(Qt.ItemDataRole.DisplayRole) or ""
        subtitle = index.data(SUBTITLE_ROLE) or ""
        status = index.data(STATUS_ROLE)
        muted = bool(index.data(MUTED_ROLE))
        badge = index.data(BADGE_ROLE) or ""
        pm = index.data(Qt.ItemDataRole.DecorationRole)

        s = theme.tokens.SPACE
        pad = s["sm"]
        rect = option.rect
        thumb_side = min(self._tile_size, rect.width() - pad * 2)
        thumb_rect = QRectF(rect.left() + (rect.width() - thumb_side) / 2,
                             rect.top() + pad, thumb_side, thumb_side)

        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        if isinstance(pm, QPixmap) and not pm.isNull():
            scaled = pm.scaled(int(thumb_side), int(thumb_side),
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            x = thumb_rect.left() + (thumb_rect.width() - scaled.width()) / 2
            y = thumb_rect.top() + (thumb_rect.height() - scaled.height()) / 2
            painter.drawPixmap(int(x), int(y), scaled)
        else:
            painter.setBrush(QColor(active_tokens().surface_alt))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(thumb_rect, 4, 4)
        if badge:
            self._paint_badge(painter, thumb_rect, badge)
        painter.restore()

        fm = option.fontMetrics
        title_rect = QRectF(rect.left() + pad, thumb_rect.bottom() + s["xs"],
                             rect.width() - pad * 2, fm.height())
        painter.save()
        painter.setPen(muted_color() if muted else QColor(active_tokens().text_primary))
        elided = fm.elidedText(title, Qt.TextElideMode.ElideMiddle, int(title_rect.width()))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
        painter.restore()

        caption_rect = QRectF(rect.left() + pad, title_rect.bottom(),
                               rect.width() - pad * 2, fm.height())
        x = caption_rect.left()
        if status and not muted:
            text = status_label(status, True)
            chip_w = fm.horizontalAdvance(text) + 16
            chip_h = fm.height()
            chip_rect = QRectF(x, caption_rect.top() + (caption_rect.height() - chip_h) / 2,
                               chip_w, chip_h)
            paint_status_chip(painter, chip_rect, text, status_color(status))
            x = chip_rect.right() + s["xs"]
        remaining = caption_rect.right() - x
        if subtitle and remaining > 12:
            sub_rect = QRectF(x, caption_rect.top(), remaining, caption_rect.height())
            painter.save()
            painter.setPen(muted_color())
            elided_sub = fm.elidedText(subtitle, Qt.TextElideMode.ElideRight, int(remaining))
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             elided_sub)
            painter.restore()

    @staticmethod
    def _paint_badge(painter, thumb_rect: QRectF, text: str):
        """A small rounded glyph in the thumbnail's bottom-left corner.

        Marks a tile whose content isn't a still image (a video). Drawn over the
        thumbnail rather than in the caption row so it survives at every zoom
        level and reads even on the muted no-thumbnail placeholder."""
        side = max(14.0, thumb_rect.width() * 0.16)
        pad = 4.0
        rect = QRectF(thumb_rect.left() + pad,
                      thumb_rect.bottom() - side - pad, side, side)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 140))
        painter.drawRoundedRect(rect, 3, 3)
        f = painter.font()
        f.setPointSizeF(max(7.0, side * 0.5))
        painter.setFont(f)
        painter.setPen(QColor(255, 255, 255, 230))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
