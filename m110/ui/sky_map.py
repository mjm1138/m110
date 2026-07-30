"""Sky-map view: a pannable, zoomable star chart with clickable objects.

The chart itself arrives as a finished SVG document from `m110.skymap` (drawn by
uranometria), so this widget only has to put it on screen and turn a click back
into an object. It paints with `QSvgRenderer` rather than a web view — the whole
point of the static-SVG mode is that M110 doesn't ship a browser engine to draw
one chart (ROADMAP item 12).

Everything is one transform: the document is a fixed 1000×1000 viewBox, so a
scale and a centre point map document coordinates to widget coordinates and back.
Hit-testing a marker is then just a distance check against the positions
`skymap.render` hands back — no scene graph, and no second copy of the geometry.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from m110 import skymap
from m110.ui.theme import active_tokens
from m110.ui.widgets import make_segment

DOC_SIZE = 1000.0          # uranometria's viewBox is always 0 0 1000 1000
MARKER_R = 8.5             # uranometria.chart.MARKER_R — the ring radius
MIN_HIT_PX = 11.0          # a comfortable click target when zoomed out
MIN_ZOOM, MAX_ZOOM = 1.0, 16.0
ZOOM_STEP = 1.15


class SkyMapCanvas(QWidget):
    """The chart surface: paints one hemisphere and reports clicks on objects."""

    object_clicked = Signal(str)      # slug
    object_hovered = Signal(str)      # slug, or "" when nothing is under the cursor

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(240, 240)
        self._renderer: QSvgRenderer | None = None
        self._markers: list[dict] = []
        self._zoom = 1.0
        self._centre = QPointF(DOC_SIZE / 2, DOC_SIZE / 2)
        self._drag_from: QPointF | None = None
        self._panned = False
        self._hover: str | None = None
        self._selected: str | None = None
        self._message = ""

    # ---- content -------------------------------------------------------
    def set_chart(self, chart: dict | None):
        """Show one hemisphere (a `skymap.render` entry), or nothing."""
        if chart is None:
            self._renderer, self._markers = None, []
        else:
            self._renderer = QSvgRenderer(chart["svg"].encode())
            self._markers = chart["objects"]
        self.reset_view()

    def set_message(self, text: str):
        """A line drawn over the chart (an empty sky says why it's empty)."""
        if text != self._message:
            self._message = text
            self.update()

    def set_selected(self, slug: str | None):
        if slug != self._selected:
            self._selected = slug
            self.update()

    def selected(self) -> str | None:
        return self._selected

    def reset_view(self):
        self._zoom = 1.0
        self._centre = QPointF(DOC_SIZE / 2, DOC_SIZE / 2)
        self.update()

    # ---- coordinate mapping --------------------------------------------
    def _scale(self) -> float:
        """Document units → pixels. The disc fits the short edge at zoom 1."""
        return min(self.width(), self.height()) / DOC_SIZE * self._zoom

    def _to_widget(self, x: float, y: float) -> QPointF:
        s = self._scale()
        return QPointF(self.width() / 2 + (x - self._centre.x()) * s,
                       self.height() / 2 + (y - self._centre.y()) * s)

    def _to_doc(self, pos) -> QPointF:
        s = self._scale()
        return QPointF(self._centre.x() + (pos.x() - self.width() / 2) / s,
                       self._centre.y() + (pos.y() - self.height() / 2) / s)

    def _marker_at(self, pos) -> dict | None:
        """The object under a widget position, nearest first. The hit radius is
        the drawn ring, but never smaller than a comfortable click target — at
        zoom 1 the ring is only a few pixels across."""
        s = self._scale()
        radius = max(MARKER_R * s, MIN_HIT_PX)
        best, best_d = None, radius
        for m in self._markers:
            p = self._to_widget(m["x"], m["y"])
            d = ((p.x() - pos.x()) ** 2 + (p.y() - pos.y()) ** 2) ** 0.5
            if d <= best_d:
                best, best_d = m, d
        return best

    # ---- painting ------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        tokens = active_tokens()
        painter.fillRect(self.rect(), QColor(tokens.window))
        if self._renderer is not None:
            origin = self._to_widget(0, 0)
            side = DOC_SIZE * self._scale()
            self._renderer.render(painter, QRectF(origin.x(), origin.y(), side, side))
            self._paint_rings(painter)
        if self._message:
            self._paint_message(painter, tokens)
        painter.end()

    def _paint_message(self, painter: QPainter, tokens):
        """A line across the middle of the chart — for an empty sky, where the
        disc is drawn but has nothing on it and the reason is worth saying."""
        painter.save()
        rect = self.rect().adjusted(24, 0, -24, 0)
        font = painter.font()
        # The app sets its fonts in pixels, so pointSizeF() is -1 here — scale
        # whichever unit this font actually carries.
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * 1.1)
        elif font.pixelSize() > 0:
            font.setPixelSize(round(font.pixelSize() * 1.1))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text = metrics.elidedText(self._message, Qt.ElideRight, rect.width() - 32)
        box = metrics.boundingRect(text).adjusted(-16, -10, 16, 10)
        box.moveCenter(self.rect().center())
        bg = QColor(tokens.window)
        bg.setAlpha(232)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(box, 8, 8)
        painter.setPen(QColor(tokens.text_secondary))
        painter.drawText(box, Qt.AlignCenter, text)
        painter.restore()

    def _paint_rings(self, painter: QPainter):
        """Selection and hover rings, drawn over the chart rather than baked into
        it — they change far more often than the document does."""
        tokens = active_tokens()
        s = self._scale()
        for m in self._markers:
            if m["slug"] == self._selected:
                color, width, pad = QColor(tokens.accent), 2.5, 7.0
            elif m["slug"] == self._hover:
                color, width, pad = QColor(tokens.text_secondary), 1.5, 5.0
            else:
                continue
            p = self._to_widget(m["x"], m["y"])
            r = max(MARKER_R * s, MIN_HIT_PX) + pad
            painter.setPen(QPen(color, width))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(p, r, r)

    # ---- interaction ---------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_from = QPointF(event.position())
            self._panned = False

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag_from is not None:
            delta = pos - self._drag_from
            if self._panned or delta.manhattanLength() > 3:
                # Drag past a small threshold before panning, so a click that
                # wobbles by a pixel still selects instead of nudging the chart.
                self._panned = True
                s = self._scale()
                self._centre -= QPointF(delta.x() / s, delta.y() / s)
                self._drag_from = QPointF(pos)
                self.setCursor(Qt.ClosedHandCursor)
                self.update()
            return
        hit = self._marker_at(pos)
        slug = hit["slug"] if hit else None
        self.setCursor(Qt.PointingHandCursor if hit else Qt.ArrowCursor)
        self.setToolTip(hit["disp"] if hit else "")
        if slug != self._hover:
            self._hover = slug
            self.object_hovered.emit(slug or "")
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        was_pan, self._drag_from = self._panned, None
        self.setCursor(Qt.ArrowCursor)
        if was_pan:
            return
        hit = self._marker_at(event.position())
        if hit:
            self.object_clicked.emit(hit["slug"])

    def wheelEvent(self, event):
        """Zoom about the cursor, so the sky under it stays put."""
        steps = event.angleDelta().y() / 120.0
        if not steps:
            return
        anchor_doc = self._to_doc(event.position())
        zoom = self._zoom * (ZOOM_STEP ** steps)
        self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        after = self._to_doc(event.position())
        self._centre += anchor_doc - after
        self.update()

    def mouseDoubleClickEvent(self, event):
        self.reset_view()


class SkyMapView(QWidget):
    """The map surface plus its chrome: a hemisphere toggle (only when the
    selection actually spans both), a reset, and the status legend."""

    object_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._charts: list[dict] = []
        self.canvas = SkyMapCanvas()
        self.canvas.object_clicked.connect(self.object_clicked)

        self._hemi_seg, self._hemi_group, self._hemi_btns = make_segment(
            [("north", "N"), ("south", "S")], "north")
        self._hemi_btns["north"].clicked.connect(lambda: self._show_hemisphere(0))
        self._hemi_btns["south"].clicked.connect(lambda: self._show_hemisphere(1))
        self._hemi_seg.hide()               # only when there are two discs

        self._legend = QLabel()
        self._legend.setProperty("caption", "true")
        self._note = QLabel()
        self._note.setProperty("muted", "true")
        self._note.setWordWrap(True)
        self._note.hide()

        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        row.addWidget(self._hemi_seg)
        row.addSpacing(8)
        row.addWidget(self._legend)
        row.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.canvas, 1)
        lay.addWidget(self._note)
        lay.addLayout(row)
        self.restyle()

    def set_charts(self, charts: list[dict], warnings: list[str] | None = None,
                   empty_message: str = ""):
        """Show a `skymap.render` result.

        `empty_message` is drawn over the chart when nothing is plotted — the
        sky is still there, with a line saying why it's bare.
        """
        self._charts = charts
        self._hemi_seg.setVisible(len(charts) > 1)
        self._legend.setVisible(True)
        if not self._hemi_btns["north"].isChecked():
            self._hemi_btns["north"].setChecked(True)
        self._show_hemisphere(0)
        plotted = sum(len(c["objects"]) for c in charts)
        self.canvas.set_message("" if plotted else empty_message)
        self._legend.setVisible(bool(plotted))
        note = next((w for w in (warnings or []) if "no coordinates" in w), "")
        self._note.setText(note)
        self._note.setVisible(bool(note))

    def show_unavailable(self, message: str):
        """The chart library isn't installed — say so instead of an empty box."""
        self._charts = []
        self.canvas.set_chart(None)
        self._hemi_seg.hide()
        self._legend.hide()
        self._note.setText(message)
        self._note.show()

    def charts(self) -> list[dict]:
        """The rendered charts (one per hemisphere), as `skymap.render` returned
        them — so a host can ask what is currently drawn."""
        return self._charts

    def set_selected(self, slug: str | None):
        """Ring the selected object, switching discs if it's on the other one."""
        self.canvas.set_selected(slug)
        if slug is None or len(self._charts) < 2:
            return
        for i, chart in enumerate(self._charts):
            if any(m["slug"] == slug for m in chart["objects"]):
                if i != self._index:
                    self._hemi_btns[chart["hemisphere"]].setChecked(True)
                    self._show_hemisphere(i)
                return

    @property
    def _index(self) -> int:
        return 1 if self._hemi_btns["south"].isChecked() else 0

    def _show_hemisphere(self, i: int):
        keep = self.canvas.selected()          # set_chart resets the view, not the ring
        chart = self._charts[i] if i < len(self._charts) else None
        self.canvas.set_chart(chart)
        self.canvas.set_selected(keep)

    def restyle(self):
        """Theme changed — recolor the legend swatches and repaint."""
        colors = status_colors()
        self._legend.setText(
            "  ".join(
                f'<span style="color:{colors[key]}">●</span> {label}'
                for key, label in (
                    (skymap.STATUS_DEEP, "Deep"),
                    (skymap.STATUS_INITIAL, "Captured"),
                    (skymap.STATUS_UNCAPTURED, "Not yet shot"),
                )
            )
        )
        self.canvas.update()


def status_colors() -> dict:
    """Marker colors for the current theme, keyed by `skymap` status.

    The map speaks the same color language as the status chips everywhere else
    (`theme.status_color`), so a green ring on the chart and a green chip in the
    table mean the same thing.
    """
    from m110.ui.theme import status_color

    return {
        skymap.STATUS_DEEP: status_color(skymap.STATUS_DEEP).name(),
        skymap.STATUS_INITIAL: status_color(skymap.STATUS_INITIAL).name(),
        skymap.STATUS_UNCAPTURED: active_tokens().text_secondary,
    }


def chart_palette() -> dict:
    """uranometria palette for the current theme, so the chart's sky, grid and
    constellation lines sit in the app rather than on top of it."""
    t = active_tokens()
    return {
        "sky": t.surface,           # the disc
        "deep": t.window,           # around it
        "grid": t.divider,          # declination circles + hour spokes
        "equator": t.border,        # the equator and the rim
        "aster": t.border,          # constellation figures
        "conname": t.text_disabled,
        "dim": t.text_secondary,    # hour / declination labels
        "ecliptic": t.text_disabled,
        # Stars keep their own colour temperature; only the neutral tint follows
        # the theme, so a light chart doesn't paint white stars on white sky.
        "star": t.text_primary,
    }
