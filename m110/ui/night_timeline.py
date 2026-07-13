"""Altitude-vs-time timeline for a night's plan (`NightTimeline`).

Paints each planned target's altitude curve across the astro-dark window (X = time
dusk→dawn, Y = 0–90°), with the min-altitude floor line and axis ticks. Fed the
``plan`` dict from ``planning.plan_night`` (each entry carries a ``samples`` series
of ``(local_time, alt, clear)``). Theme-token colors; repaints on theme change.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget

from m110.ui import theme
from m110.planning import SEASON_MIN_ALT

# A small, distinguishable palette that reads in light + dark (cycled per target).
_SERIES = ["#4c8dff", "#e0663a", "#3fb27f", "#c65fd0", "#d6a63c",
           "#3fb8c0", "#e05a7d", "#8a7be0"]
_MARGIN_L, _MARGIN_R, _MARGIN_T, _MARGIN_B = 34, 12, 10, 22


class NightTimeline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._plan = None
        self.setMinimumHeight(200)
        if theme.manager() is not None:
            theme.manager().changed.connect(self.update)

    def set_plan(self, plan: dict | None):
        self._plan = plan
        self.update()

    def paintEvent(self, _event):
        t = theme.active_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        axis = QColor(t.border)
        muted = QColor(t.text_secondary)

        plan = self._plan or {}
        window = plan.get("window") or (None, None)
        dusk, dawn = window
        entries = plan.get("entries") or []

        if not dusk or not dawn:
            p.setPen(muted)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "No astronomical darkness / nothing planned.")
            return

        x0, x1 = _MARGIN_L, w - _MARGIN_R
        y0, y1 = _MARGIN_T, h - _MARGIN_B                 # y0 = top (90°), y1 = bottom (0°)
        span = (dawn - dusk).total_seconds() or 1.0

        def X(tm):
            return x0 + (x1 - x0) * ((tm - dusk).total_seconds() / span)

        def Y(alt):
            return y1 - (y1 - y0) * (max(0.0, min(90.0, alt)) / 90.0)

        small = QFont(self.font())
        small.setPointSizeF(max(7.0, self.font().pointSizeF() - 2))
        p.setFont(small)

        # Altitude gridlines + labels (0/30/60/90).
        for alt in (0, 30, 60, 90):
            yy = Y(alt)
            pen = QPen(axis)
            pen.setStyle(Qt.PenStyle.DashLine if alt == SEASON_MIN_ALT else Qt.PenStyle.SolidLine)
            pen.setColor(QColor(t.accent) if alt == SEASON_MIN_ALT else axis)
            p.setPen(pen)
            p.drawLine(int(x0), int(yy), int(x1), int(yy))
            p.setPen(muted)
            p.drawText(QRectF(0, yy - 7, x0 - 3, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{alt}°")

        # Hour ticks along the bottom.
        p.setPen(muted)
        from datetime import timedelta
        tick = dusk.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        while tick < dawn:
            xx = X(tick)
            p.drawLine(int(xx), int(y1), int(xx), int(y1 + 3))
            p.drawText(QRectF(xx - 16, y1 + 4, 32, 14),
                       Qt.AlignmentFlag.AlignCenter, tick.strftime("%H"))
            tick += timedelta(hours=1)

        # Each target's altitude curve; a dot + label at its transit peak.
        for i, e in enumerate(entries):
            color = QColor(_SERIES[i % len(_SERIES)])
            samples = e.get("samples") or []
            if not samples:
                continue
            pts = [QPointF(X(tm), Y(alt)) for tm, alt, _clear in samples]
            pen = QPen(color)
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawPolyline(pts)
            # label at the transit sample (highest)
            ti = max(range(len(samples)), key=lambda k: samples[k][1])
            tx, talt = X(samples[ti][0]), Y(samples[ti][1])
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(tx, talt), 2.5, 2.5)
            label = (e.get("slug") or "").upper()
            p.setPen(color)
            p.drawText(QRectF(tx - 40, talt - 15, 80, 12),
                       Qt.AlignmentFlag.AlignCenter, label)
        p.end()
