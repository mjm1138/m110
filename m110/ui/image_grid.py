"""Reusable image-grid component — a generic tile-per-item grid, zoomable via
tile size: square image tiles with the title overlaid bottom-left on a soft
gradient and a status dot + label bottom-right (UI 1.0, mock A), laid out by a
`JustifiedGridView` so every row fills the width.

No imports from `m110.catalog`/`m110.objects`/`m110.derived` — this module
knows nothing about catalog objects. The first consumer (`m110/ui/pages/
catalog.py`, the Library grid) adapts its own data into `TileItem`; a future
cross-object image browser (UI_ROADMAP Phase 4+) can reuse `TileModel`/
`TileDelegate` as-is for a different dataset.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap,
)
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate

from m110.ui import theme
from m110.ui.theme.fonts import serif_font
from m110.ui.theme.tokens import FONT_SIZE, RADIUS, SPACE
from m110.ui.widgets import ThumbnailLoader, status_label

# Tile (zoom) size bounds, shared by every consumer of this grid. The slider sets
# the *target* side; `JustifiedGridView` stretches it to fill each row.
GRID_ZOOM_MIN = 80
GRID_ZOOM_MAX = 220
GRID_ZOOM_DEFAULT = 140

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
STATUS_ROLE = Qt.ItemDataRole.UserRole + 2
SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 3
MUTED_ROLE = Qt.ItemDataRole.UserRole + 4
BADGE_ROLE = Qt.ItemDataRole.UserRole + 5
STATUS_TEXT_ROLE = Qt.ItemDataRole.UserRole + 6

_DOT = 6.0          # status dot diameter (px)


@dataclass
class TileItem:
    """One tile's display data. `key` is an opaque identity (e.g. a catalog
    slug) — callers use it to map a tile back to their own model."""
    key: str
    thumb_path: Path | None
    title: str
    subtitle: str = ""                # not drawn: part of the tooltip
    status: str | None = None
    status_text: str | None = None   # status label override (else the status's label)
    muted: bool = False
    badge: str = ""     # short glyph drawn over the thumbnail (e.g. "▶" for video)
    tooltip: str = ""   # the hover text; else title, status and subtitle


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
        if role == Qt.ItemDataRole.ToolTipRole:
            # The caption carries the title and status only; the rest is on hover
            # (and the whole title, when the tile had to elide it).
            return it.tooltip or "\n".join(
                x for x in (it.title, it.status_text, it.subtitle) if x)
        if role == KEY_ROLE:
            return it.key
        if role == STATUS_ROLE:
            return it.status
        if role == STATUS_TEXT_ROLE:
            return it.status_text
        if role == SUBTITLE_ROLE:
            return it.subtitle
        if role == MUTED_ROLE:
            return it.muted
        if role == BADGE_ROLE:
            return it.badge
        return None

    def request_thumbnails(self, loader: ThumbnailLoader, size: int):
        """Kick off async decodes for every item with a thumbnail source, at
        `size` device pixels. Call after `set_items()` and again when the tiles
        grow (`JustifiedGridView.tileSideChanged`) — cache hits for a
        previously-seen size return instantly."""
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
        old = self._pixmaps.get(key)
        if old is not None and not old.isNull() and old.width() > pm.width():
            return   # a smaller decode finished after a sharper one — keep the sharp one
        self._pixmaps[key] = pm
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])


class TileDelegate(QStyledItemDelegate):
    """Paints one tile: the image fills a rounded square (center-cropped), the
    title sits bottom-left over a gradient that fades to the well colour, and a
    status dot + label sits bottom-right. A tile without an image is an empty well
    slot carrying its title. Selection is a brass outline, so the picture stays
    the brightest thing in the cell. Every colour is read from the active theme at
    paint time.

    The **cell** is the whole grid cell (`JustifiedGridView` sets it); the tile is
    the cell inset by half the gap on every side. `serif` sets titles in the
    display serif (object designations); `elide` picks where a long title is cut
    (filenames keep both ends)."""

    def __init__(self, tile_size: int, parent=None, *, serif: bool = True,
                 elide: Qt.TextElideMode = Qt.TextElideMode.ElideRight):
        super().__init__(parent)
        self._gap = SPACE["sm"]
        self._cell = int(tile_size) + self._gap
        self._serif = serif
        self._elide = elide

    def set_tile_size(self, size: int):
        """The tile's side in px (the image square, without the gap)."""
        self._cell = int(size) + self._gap

    def set_cell(self, cell: int, gap: int):
        self._cell, self._gap = int(cell), int(gap)

    def tile_side(self) -> int:
        return self._cell - self._gap

    def sizeHint(self, option, index):
        return QSize(self._cell, self._cell)

    # ---- geometry, kept apart from painting so tests can check it ----
    def tile_rect(self, cell_rect) -> QRectF:
        half = self._gap / 2
        return QRectF(cell_rect).adjusted(half, half, -half, -half)

    def title_font(self, side: float) -> QFont:
        big = side >= 120
        if self._serif:
            return serif_font(FONT_SIZE["section"] if big else FONT_SIZE["body"])
        f = QFont()
        f.setPixelSize(FONT_SIZE["body"] if big else FONT_SIZE["caption"])
        return f

    @staticmethod
    def status_font() -> QFont:
        f = QFont()
        f.setPixelSize(FONT_SIZE["caption"])
        return f

    def caption_layout(self, tile: QRectF, title: str, status_text: str | None):
        """Where the caption goes: ``(title_text, title_rect, status_rect | None,
        show_label)``. The status keeps its dot; its label is dropped first when
        space runs out, and only then does the title elide — the designation is
        the tile's identity."""
        pad = SPACE["sm"]
        tf = QFontMetricsF(self.title_font(tile.width()))
        sf = QFontMetricsF(self.status_font())
        line_h = max(tf.height(), sf.height())
        top = tile.bottom() - pad - line_h
        avail = tile.width() - 2 * pad
        status_rect, show_label, status_w = None, False, 0.0
        if status_text:
            label_w = _DOT + SPACE["xs"] + sf.horizontalAdvance(status_text)
            if tf.horizontalAdvance(title) + SPACE["sm"] + label_w <= avail:
                status_w, show_label = label_w, True
            else:
                status_w = _DOT
            status_rect = QRectF(tile.right() - pad - status_w, top, status_w, line_h)
        title_w = max(0.0, avail - (status_w + SPACE["sm"] if status_text else 0.0))
        text = tf.elidedText(title, self._elide, title_w)
        return text, QRectF(tile.left() + pad, top, title_w, line_h), status_rect, show_label

    def paint(self, painter, option, index):
        title = index.data(Qt.ItemDataRole.DisplayRole) or ""
        status = index.data(STATUS_ROLE)
        muted = bool(index.data(MUTED_ROLE))
        badge = index.data(BADGE_ROLE) or ""
        pm = index.data(Qt.ItemDataRole.DecorationRole)
        status_text = None
        if status and not muted:
            status_text = index.data(STATUS_TEXT_ROLE) or status_label(status, True)

        w = theme.on_well()
        tile = self.tile_rect(option.rect)
        radius = RADIUS["md"]
        shape = QPainterPath()
        shape.addRoundedRect(tile, radius, radius)
        state = option.state

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setClipPath(shape)
        if isinstance(pm, QPixmap) and not pm.isNull():
            # Cover the square: the short side fills the tile, the rest is cropped.
            pw, ph = pm.width(), pm.height()
            side = min(pw, ph)
            painter.drawPixmap(tile, pm, QRectF((pw - side) / 2, (ph - side) / 2,
                                                side, side))
            # The caption's scrim: transparent → the well colour over the bottom 45%.
            g = QLinearGradient(QPointF(0, tile.bottom() - tile.height() * 0.45),
                                QPointF(0, tile.bottom()))
            clear, scrim = QColor(w.well), QColor(w.well)
            clear.setAlpha(0)
            scrim.setAlpha(215)
            g.setColorAt(0.0, clear)
            g.setColorAt(1.0, scrim)
            painter.fillRect(tile, g)
        else:
            painter.fillRect(tile, QColor(w.surface))       # an empty slot on the well
        if state & QStyle.StateFlag.State_MouseOver and not state & QStyle.StateFlag.State_Selected:
            painter.fillRect(tile, QColor(255, 255, 255, 14))
        painter.setClipping(False)

        text, title_rect, status_rect, show_label = self.caption_layout(
            tile, title, status_text)
        painter.setFont(self.title_font(tile.width()))
        painter.setPen(QColor(w.well_muted if muted else w.well_text))
        painter.drawText(title_rect,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        if status_rect is not None:
            cy = status_rect.center().y()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.status_color(status, well=True))
            painter.drawEllipse(QPointF(status_rect.left() + _DOT / 2, cy), _DOT / 2, _DOT / 2)
            if show_label:
                painter.setFont(self.status_font())
                painter.setPen(QColor(w.well_text))
                painter.drawText(status_rect.adjusted(_DOT + SPACE["xs"], 0, 0, 0),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 status_text)
        if badge:
            self._paint_badge(painter, tile, badge)
        if state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(theme.active_tokens().accent), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(tile.adjusted(1, 1, -1, -1), radius, radius)
        painter.restore()

    @staticmethod
    def _paint_badge(painter, tile: QRectF, text: str):
        """A small rounded glyph in the tile's top-left corner — marks content that
        isn't a still image (a video). Top-left, clear of the caption, so it reads
        at every zoom level and on an empty slot."""
        side = max(14.0, tile.width() * 0.16)
        pad = SPACE["xs"]
        rect = QRectF(tile.left() + pad, tile.top() + pad, side, side)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 140))
        painter.drawRoundedRect(rect, RADIUS["sm"], RADIUS["sm"])
        f = QFont(painter.font())
        f.setPixelSize(int(max(9.0, side * 0.55)))
        painter.setFont(f)
        painter.setPen(QColor(255, 255, 255, 230))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


def justify(width: int, target: int, gap: int) -> tuple[int, int]:
    """``(columns, cell)`` for a justified row: as many `target`-sized tiles as
    fit in `width`, then every cell widened so the row fills it. A cell is a tile
    plus one `gap` (half each side), so ``columns * cell <= width`` and what's
    left over is under a pixel per column."""
    width, target, gap = max(1, int(width)), max(1, int(target)), max(0, int(gap))
    cols = max(1, width // (target + gap))      # every cell carries its own gap
    return cols, max(gap + 1, width // cols)


class JustifiedGridView(QListView):
    """An icon-mode list whose rows fill the width (Lightroom, Photos), instead of
    leaving a ragged gap on the right (critique §2.4).

    The Tile size slider sets a *target* side; the view fits as many columns as
    that allows and stretches the tiles to fill the row — again on every resize
    (window, splitter, detail pane, scrollbar). `tileSideChanged` fires, debounced,
    once the tiles outgrow the size their thumbnails were decoded at, so the page
    can ask for sharper ones."""

    tileSideChanged = Signal(int)

    def __init__(self, target: int, parent=None, **delegate_opts):
        super().__init__(parent)
        self.setProperty("well", True)                 # images sit on the dark well
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)                    # hover highlight
        self._gap = SPACE["sm"]
        self._target = int(target)
        self._cols = 1
        self._delegate = TileDelegate(self._target, self, **delegate_opts)
        self.setItemDelegate(self._delegate)
        # Qt lays a wrapping icon view out inside the viewport *minus a vertical
        # scrollbar's width* whenever the bar is as-needed — shown or not, overlay
        # (macOS) or not. That strip is always empty on the right; an equal margin
        # on the left centres the rows between two even gutters.
        self.setViewportMargins(self._reserved_scrollbar(), 0, 0, 0)
        self._decoded_px = 0
        self._side_timer = QTimer(self)
        self._side_timer.setSingleShot(True)
        self._side_timer.setInterval(200)
        self._side_timer.timeout.connect(self._emit_side)
        self._relayout()

    def tile_delegate(self) -> TileDelegate:
        return self._delegate

    def target_size(self) -> int:
        return self._target

    def set_target_size(self, size: int):
        self._target = int(size)
        self._relayout()

    def columns(self) -> int:
        return self._cols

    def tile_side(self) -> int:
        return self._delegate.tile_side()

    def thumbnail_px(self) -> int:
        """The size to decode thumbnails at: the tile in device pixels (sharp on
        a Retina display, where the logical size would be blurred 2×)."""
        return max(1, int(self.tile_side() * max(1.0, self.devicePixelRatioF())))

    def note_decoded(self, px: int):
        """The page requested thumbnails at `px` — only a bigger tile re-requests."""
        self._decoded_px = max(self._decoded_px, int(px))

    def _reserved_scrollbar(self) -> int:
        if self.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAsNeeded:
            return 0
        return self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None,
                                        self.verticalScrollBar())

    def layout_width(self) -> int:
        """The width Qt wraps rows at (`QListViewPrivate::prepareItemsLayout`): the
        largest viewport less the reserved scrollbar strip. A row of exactly this
        width still fits (Qt wraps on `>` its last pixel), hence the −1."""
        return self.maximumViewportSize().width() - self._reserved_scrollbar() - 1

    def _relayout(self):
        cols, cell = justify(self.layout_width(), self._target, self._gap)
        self._cols = cols
        self._delegate.set_cell(cell, self._gap)
        self.setGridSize(QSize(cell, cell))
        self.doItemsLayout()
        if self.thumbnail_px() > self._decoded_px:
            self._side_timer.start()

    def _emit_side(self):
        px = self.thumbnail_px()
        if px > self._decoded_px:
            self._decoded_px = px
            self.tileSideChanged.emit(px)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()
