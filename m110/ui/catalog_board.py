"""The catalog board — one goal drawn as a wall of cells, the Overview's hero
(UI 1.0 Phase 8 · C, critique §2.3: "Complete the catalog" as a picture, not a
table row).

Every member of the goal is a cell, in catalog order (M1 … M110). A captured
member shows its hero image; a bar along the cell's foot fills toward its
integration goal in the status hue (Initial · in progress · Deep). A member not
captured yet is an empty slot on the well carrying its designation. Hover for the
name and status; click a captured cell to open the object.

The data is `goals.board()` (engine, Qt-free); this widget only lays it out and
paints it. One custom-painted widget, not 110 child widgets: it reflows with the
width (`heightForWidth`, justified like the Deep Sky grid) and repaints cheaply.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtWidgets import (
    QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolTip, QWidget,
)

from m110.ui import theme
from m110.ui.image_grid import justify
from m110.ui.theme.tokens import FONT_SIZE, RADIUS, SPACE
from m110.ui.widgets import ThumbnailLoader, defer, status_label

# board state → the capture status whose hue it takes
STATUS_OF = {"initial": "initial", "progress": "in_progress", "deep": "deep_stack"}

CELL_TARGET = 52          # px — the cell side the board aims for before justifying
                          # (110 Messier cells ≈ 7 rows at the default window)
_BAR = 3                  # px — the progress bar along a cell's foot


PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 20     # float 0..1 on a status cell
STATUS_KEY_ROLE = Qt.ItemDataRole.UserRole + 21   # 'deep_stack' | 'in_progress' | …


class StatusBarDelegate(QStyledItemDelegate):
    """A status cell as a mini bar toward the integration goal, in the status
    hue, followed by its label ("Deep", "62%", "Initial") — so a column of
    objects reads as progress at a glance. The cell's text is the label (copy,
    accessibility); the bar comes from `PROGRESS_ROLE` / `STATUS_KEY_ROLE`."""

    BAR_W = 44

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        style = opt.widget.style() if opt.widget else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        status = index.data(STATUS_KEY_ROLE)
        frac = max(0.0, min(1.0, float(index.data(PROGRESS_ROLE) or 0.0)))
        t = theme.active_tokens()
        hue = theme.status_color(status)
        r = QRectF(option.rect).adjusted(SPACE["sm"] - 2, 0, -SPACE["xs"], 0)
        bar = QRectF(r.left(), r.center().y() - 2.5, self.BAR_W, 5)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.control))
        painter.drawRoundedRect(bar, 2.5, 2.5)
        if frac > 0:
            painter.setBrush(hue)
            painter.drawRoundedRect(QRectF(bar.left(), bar.top(),
                                           max(5.0, bar.width() * frac), bar.height()),
                                    2.5, 2.5)
        painter.setPen(hue)
        painter.setFont(opt.font)
        painter.drawText(r.adjusted(self.BAR_W + SPACE["sm"], 0, 0, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width() + self.BAR_W + SPACE["sm"], s.height())


class GoalBar(QWidget):
    """A goal's progress as one thin bar in two segments: deep (the Deep hue),
    then captured-not-deep (the in-progress hue), on the control track. Replaces
    the Goals table's "11/110 (10.0%)" text column."""

    def __init__(self, captured: int, deep: int, total: int, parent=None):
        super().__init__(parent)
        self.captured, self.deep, self.total = int(captured), int(deep), max(0, int(total))
        self.setFixedHeight(SPACE["sm"])
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        pct = 100 * self.captured / self.total if self.total else 0
        self.setToolTip(f"{self.captured} of {self.total} captured ({pct:.0f}%) · "
                        f"{self.deep} deep")

    def segments(self, width: float) -> tuple[float, float]:
        """Pixel widths of the deep and the captured-not-deep segments."""
        if not self.total:
            return 0.0, 0.0
        deep = width * min(self.deep, self.total) / self.total
        cap = width * min(self.captured, self.total) / self.total
        return deep, max(0.0, cap - deep)

    def paintEvent(self, _event):
        t = theme.active_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        rad = r.height() / 2
        clip = QPainterPath()
        clip.addRoundedRect(r, rad, rad)
        p.setClipPath(clip)
        p.fillRect(r, QColor(t.control))
        deep_w, cap_w = self.segments(r.width())
        p.fillRect(QRectF(r.left(), r.top(), deep_w, r.height()), QColor(t.status_deep))
        p.fillRect(QRectF(r.left() + deep_w, r.top(), cap_w, r.height()),
                   QColor(t.status_progress))
        p.end()


class CatalogBoard(QWidget):
    """`set_cells(cells, thumbs, names)`: `cells` from `goals.board()`; `thumbs`
    ``{slug: hero path}`` for the captured ones; `names` ``{slug: common name}``
    for tooltips. Emits `object_activated(slug)` — deferred past the mouse
    handler — when a captured cell is clicked."""

    object_activated = Signal(str)

    def __init__(self, parent=None, loader: ThumbnailLoader | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        sp = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self.setAccessibleName("Catalog board")
        self._loader = loader or ThumbnailLoader(self)
        self._cells: list[dict] = []
        self._thumbs: dict[str, Path] = {}
        self._names: dict[str, str] = {}
        self._pixmaps: dict[str, QPixmap] = {}
        self._decoded_px = 0
        self._hover = -1
        self._gap = SPACE["xs"]
        self._pad = SPACE["sm"]

    # ---- data ----
    def set_cells(self, cells: list[dict], thumbs: dict | None = None,
                  names: dict | None = None):
        self._cells = list(cells)
        self._thumbs = {k: Path(v) for k, v in (thumbs or {}).items() if v}
        self._names = dict(names or {})
        keep = {c["slug"] for c in self._cells}
        self._pixmaps = {k: v for k, v in self._pixmaps.items() if k in keep}
        self._decoded_px = 0
        self._hover = -1
        self.updateGeometry()
        self._request_thumbnails()
        self.update()

    def cells(self) -> list[dict]:
        return self._cells

    # ---- geometry ----
    def grid(self, width: int | None = None) -> tuple[int, int]:
        """``(columns, cell)`` for `width` (default: the widget's)."""
        w = (self.width() if width is None else width) - 2 * self._pad
        return justify(w, CELL_TARGET, self._gap)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if not self._cells:
            return 2 * self._pad
        cols, cell = self.grid(width)
        rows = -(-len(self._cells) // cols)
        return 2 * self._pad + rows * cell

    def sizeHint(self) -> QSize:
        return QSize(640, self.heightForWidth(640))

    def minimumSizeHint(self) -> QSize:
        # One row, not heightForWidth(min width): a layout adds the minimum height
        # to its own, and at three cells wide 110 members are ~37 rows — the
        # Overview grew thousands of px of empty page under its sections.
        # The real height comes from heightForWidth at the real width.
        return QSize(CELL_TARGET * 3, CELL_TARGET + 2 * self._pad)

    def cell_rect(self, i: int) -> QRectF:
        """The painted square of cell `i` (its grid slot less half a gap each side)."""
        cols, cell = self.grid()
        r, c = divmod(i, cols)
        half = self._gap / 2
        return QRectF(self._pad + c * cell + half, self._pad + r * cell + half,
                      cell - self._gap, cell - self._gap)

    def index_at(self, pos) -> int:
        pos = QPointF(pos)
        cols, cell = self.grid()
        x, y = pos.x() - self._pad, pos.y() - self._pad
        if x < 0 or y < 0 or cell <= 0:
            return -1
        c, r = int(x // cell), int(y // cell)
        i = r * cols + c
        if c >= cols or i >= len(self._cells) or not self.cell_rect(i).contains(pos):
            return -1
        return i

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._request_thumbnails()

    # ---- thumbnails ----
    def _request_thumbnails(self):
        """Decode heroes at the cell's device-pixel size; again only if cells grow."""
        if not self._cells or self.width() <= 0:
            return
        _cols, cell = self.grid()
        px = int((cell - self._gap) * max(1.0, self.devicePixelRatioF()))
        if px <= self._decoded_px:
            return
        self._decoded_px = px
        for c in self._cells:
            path = self._thumbs.get(c["slug"])
            if path is not None and c["state"] != "missing":
                self._loader.request(path, px,
                                     lambda pm, s=c["slug"]: self._on_thumb(s, pm),
                                     crop="square")

    def _on_thumb(self, slug: str, pm):
        if pm is None or not any(c["slug"] == slug for c in self._cells):
            return
        old = self._pixmaps.get(slug)
        if old is not None and old.width() > pm.width():
            return
        self._pixmaps[slug] = pm
        self.update()

    # ---- painting ----
    def paintEvent(self, _event):
        w = theme.on_well()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(w.well))
        p.drawRoundedRect(QRectF(self.rect()), RADIUS["md"], RADIUS["md"])
        font = QFont(self.font())
        font.setPixelSize(FONT_SIZE["caption"])
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        fm = QFontMetricsF(font)
        for i, c in enumerate(self._cells):
            self._paint_cell(p, i, c, w, fm)
        p.end()

    def _paint_cell(self, p: QPainter, i: int, c: dict, w, fm: QFontMetricsF):
        r = self.cell_rect(i)
        radius = RADIUS["sm"]
        shape = QPainterPath()
        shape.addRoundedRect(r, radius, radius)
        state = c["state"]
        missing = state == "missing"
        pm = self._pixmaps.get(c["slug"])
        status_hue = theme.status_color(STATUS_OF.get(state), well=True)
        p.save()
        p.setClipPath(shape)
        if missing:
            slot = QColor(w.surface)
            slot.setAlpha(150)                       # an empty slot, quieter than a tile
            p.fillRect(r, slot)
        elif pm is not None and not pm.isNull():
            side = min(pm.width(), pm.height())
            p.drawPixmap(r, pm, QRectF((pm.width() - side) / 2, (pm.height() - side) / 2,
                                       side, side))
            g = QLinearGradient(QPointF(0, r.bottom() - r.height() * 0.5),
                                QPointF(0, r.bottom()))
            clear, scrim = QColor(w.well), QColor(w.well)
            clear.setAlpha(0)
            scrim.setAlpha(200)
            g.setColorAt(0, clear)
            g.setColorAt(1, scrim)
            p.fillRect(r, g)
        else:                                        # captured, no hero image yet
            tint = QColor(status_hue)
            tint.setAlpha(60)
            p.fillRect(r, QColor(w.surface))
            p.fillRect(r, tint)
        if not missing:
            track = QColor(w.well)
            track.setAlpha(180)
            foot = QRectF(r.left(), r.bottom() - _BAR, r.width(), _BAR)
            p.fillRect(foot, track)
            frac = max(0.08, min(1.0, float(c.get("progress") or 0.0)))
            p.fillRect(QRectF(foot.left(), foot.top(), foot.width() * frac, _BAR),
                       status_hue)
        if i == self._hover and not missing:
            hover = QColor(w.well_text)          # a lift, in the well's own ink
            hover.setAlpha(22)
            p.fillRect(r, hover)
        p.restore()
        p.setPen(QColor(w.well_muted if missing else w.well_text))
        label_rect = r.adjusted(SPACE["xs"], 0, -2, -(_BAR + 2))
        text = fm.elidedText(c["label"], Qt.TextElideMode.ElideRight, label_rect.width())
        p.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, text)

    # ---- interaction ----
    def tooltip_for(self, i: int) -> str:
        c = self._cells[i]
        name = self._names.get(c["slug"])
        head = f"{c['label']} — {name}" if name and name != c["label"] else c["label"]
        if c["state"] == "missing":
            return f"{head}\nNot captured yet"
        st = STATUS_OF.get(c["state"])
        return f"{head}\n{status_label(st, True, c.get('progress'))}"

    def mouseMoveEvent(self, event):
        i = self.index_at(event.position())
        if i != self._hover:
            self._hover = i
            clickable = i >= 0 and self._cells[i]["state"] != "missing"
            self.setCursor(Qt.CursorShape.PointingHandCursor if clickable
                           else Qt.CursorShape.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = -1
        self.unsetCursor()
        self.update()
        super().leaveEvent(event)

    def event(self, e):
        if e.type() == e.Type.ToolTip:
            i = self.index_at(e.pos())
            if i >= 0:
                QToolTip.showText(e.globalPos(), self.tooltip_for(i), self)
            else:
                QToolTip.hideText()
                e.ignore()
            return True
        return super().event(e)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            i = self.index_at(event.position())
            if i >= 0 and self._cells[i]["state"] != "missing":
                slug = self._cells[i]["slug"]
                # Opening an object switches pages: never from inside the handler.
                defer(self, lambda: self.object_activated.emit(slug))
        super().mouseReleaseEvent(event)
