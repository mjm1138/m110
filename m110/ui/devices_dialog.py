"""Tools → Devices… — each telescope M110 has seen: its calibration library,
the captures each master dark served, and how its sensor looks over time.

Read-only, built from ``derived/devices.json`` (`calibration.device_rollup`,
written on every Sync), so it opens instantly and needs no worker. A Seestar
dark-subtracts on the telescope, so its library is reference data: which dark a
capture got is *inferred* (rule v1) and every link says whether it was confirmed
by time + temperature or only inferred.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QLabel, QScrollArea, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from m110 import calibration, config, derived
from m110.ui import theme
from m110.ui.widgets import (
    CollapsibleSection, NumItem, ROW_THUMB_SIZE, ThumbnailLoader, dark_gap_item,
    defer, fit_table_height, make_numeric, make_table,
)

_LIB_COLS = ["Made (device clock)", "Exp (s)", "Temp (°C)", "Gain", "Frames",
             "Median", "Hot px", "Captures"]
_CAP_COLS = ["Date", "Object", "Frames", "Sensor (°C)", "Dark", "Link"]


def _num(v, fmt="{:g}") -> NumItem:
    return make_numeric(NumItem("—" if v is None else fmt.format(v),
                                -1e9 if v is None else v))


def _set_icon(item: QTableWidgetItem, pm) -> None:
    """Thumbnail callback: the decode can land after the table was refilled for
    another device, when `item` is gone."""
    if pm is None:
        return
    try:
        item.setIcon(QIcon(pm))
    except RuntimeError:
        pass


class SensorChart(QWidget):
    """A small scatter of one master-dark statistic against sensor temperature,
    newest masters drawn in the accent color. Hand-painted like `NightTimeline`,
    colors from theme tokens only."""

    _ML, _MR, _MT, _MB = 46, 12, 22, 26

    def __init__(self, title: str, key: str, parent=None):
        super().__init__(parent)
        self._title, self._key = title, key
        self._masters: list[dict] = []
        self.setMinimumHeight(170)
        if theme.manager() is not None:
            theme.manager().changed.connect(self.update)

    def set_masters(self, masters: list[dict]):
        self._masters = [m for m in masters
                         if m.get("temp_c") is not None and m.get(self._key) is not None]
        self.update()

    def points(self) -> list[tuple[float, float]]:
        return [(m["temp_c"], float(m[self._key])) for m in self._masters]

    def paintEvent(self, _event):
        t = theme.active_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        muted, axis = QColor(t.text_secondary), QColor(t.border)
        p.setPen(QColor(t.text_primary))
        p.drawText(self._ML, 14, self._title)
        pts = self.points()
        if not pts:
            p.setPen(muted)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No masters yet.")
            return
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        xlo, xhi = min(xs) - 1, max(xs) + 1
        ylo, yhi = min(ys), max(ys)
        pad = (yhi - ylo) * 0.15 or max(abs(yhi) * 0.05, 1.0)
        ylo, yhi = ylo - pad, yhi + pad
        x0, x1, y0, y1 = self._ML, w - self._MR, self._MT, h - self._MB

        def X(v):
            return x0 + (x1 - x0) * (v - xlo) / (xhi - xlo)

        def Y(v):
            return y1 - (y1 - y0) * (v - ylo) / (yhi - ylo)

        p.setPen(QPen(axis, 1))
        p.drawLine(x0, y1, x1, y1)
        p.drawLine(x0, y0, x0, y1)
        p.setPen(muted)
        p.drawText(x0, h - 20, 80, 16, Qt.AlignmentFlag.AlignLeft, f"{xlo + 1:g} °C")
        p.drawText(x1 - 80, h - 20, 80, 16, Qt.AlignmentFlag.AlignRight, f"{xhi - 1:g} °C")
        p.drawText(2, int(y0) + 4, f"{yhi - pad:.0f}")
        p.drawText(2, int(y1), f"{ylo + pad:.0f}")
        order = sorted(range(len(self._masters)),
                       key=lambda i: self._masters[i].get("made") or "")
        newest = order[-1]
        for i in order:
            x, y = pts[i]
            c = QColor(t.accent) if i == newest else muted
            p.setPen(QPen(c, 1))
            p.setBrush(c)
            p.drawEllipse(QPointF(X(x), Y(y)), 4, 4)


class DevicesDialog(QDialog):
    """Per-device calibration library, captures and sensor health."""

    open_object = Signal(str)

    def __init__(self, parent=None, devices: list[dict] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Devices")
        self.resize(900, 680)
        self._devices = devices if devices is not None else derived.load_devices()
        self._thumbs = ThumbnailLoader(self)

        lay = QVBoxLayout(self)
        self._picker = QComboBox()
        for d in self._devices:
            self._picker.addItem(d.get("label") or d["device"], d["device"])
        self._picker.setVisible(len(self._devices) > 1)
        self._picker.currentIndexChanged.connect(self._show_index)
        lay.addWidget(self._picker)
        self._heading = QLabel()
        self._heading.setTextFormat(Qt.RichText)
        self._heading.setWordWrap(True)
        lay.addWidget(self._heading)

        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setAlignment(Qt.AlignTop)
        self._lib_sec = CollapsibleSection("Dark library")
        self.library_table = make_table(_LIB_COLS)
        self.library_table.setIconSize(QSize(ROW_THUMB_SIZE, ROW_THUMB_SIZE))
        self._lib_sec.body.addWidget(self.library_table)
        self._cap_sec = CollapsibleSection("Captures")
        self.captures_table = make_table(_CAP_COLS)
        self.captures_table.itemDoubleClicked.connect(self._on_capture_activated)
        self._cap_sec.body.addWidget(self.captures_table)
        self._health_sec = CollapsibleSection("Sensor health")
        self.level_chart = SensorChart("Dark level (median ADU) vs temperature", "median")
        self.hot_chart = SensorChart("Hot pixels vs temperature", "hot_px")
        self._health_sec.body.addWidget(self.level_chart)
        self._health_sec.body.addWidget(self.hot_chart)
        for sec in (self._lib_sec, self._cap_sec, self._health_sec):
            self._body.addWidget(sec)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        if self._devices:
            self._show_index(0)
        else:
            self._heading.setText("No devices yet — import from a telescope, then Sync.")
            body.setVisible(False)

    # ── one device ────────────────────────────────────────────────────────────

    def _show_index(self, i: int):
        if not 0 <= i < len(self._devices):
            return
        d = self._devices[i]
        darks = [m for m in d.get("masters", []) if m.get("tier") == "darks"]
        note = ("Subs from this telescope are dark-subtracted on the telescope; "
                "these darks are kept for reference and never applied again. Which "
                "dark a capture got is inferred from time and temperature."
                if d.get("darks_applied_on_device") else "")
        self._heading.setText(f"<b>{d.get('label') or d['device']}</b>"
                              f"<br><span style='color:{theme.active_tokens().text_secondary}'>"
                              f"{note}</span>")
        self._fill_library(darks)
        self._fill_captures(d.get("captures", []))
        self.level_chart.set_masters(darks)
        self.hot_chart.set_masters(darks)
        # a telescope with no library has nothing to chart, and a dark link only
        # exists for one that dark-subtracts on board
        self._lib_sec.setVisible(bool(darks))
        self._health_sec.setVisible(bool(darks))
        linked = bool(d.get("darks_applied_on_device"))
        for col in (4, 5):
            self.captures_table.setColumnHidden(col, not linked)

    def _fill_library(self, darks: list[dict]):
        t = self.library_table
        t.setSortingEnabled(False)
        t.setRowCount(0)
        for m in darks:
            r = t.rowCount()
            t.insertRow(r)
            made = (m.get("made") or "").replace("T", " ")
            item = NumItem(made or m["file"], made or m["file"])
            item.setToolTip(m.get("rel", m["file"]))
            t.setItem(r, 0, item)
            if m.get("preview"):
                self._thumbs.request(Path(config.DATA_ROOT) / m["preview"], ROW_THUMB_SIZE,
                                     lambda pm, it=item: _set_icon(it, pm))
            t.setItem(r, 1, _num(m.get("exptime")))
            t.setItem(r, 2, _num(m.get("temp_c")))
            t.setItem(r, 3, _num(m.get("gain")))
            t.setItem(r, 4, _num(m.get("frames")))
            t.setItem(r, 5, _num(m.get("median"), "{:.0f}"))
            t.setItem(r, 6, _num(m.get("hot_px")))
            t.setItem(r, 7, _num(m.get("captures")))
        t.resizeColumnsToContents()
        if any(m.get("preview") for m in darks):     # icons arrive after the resize
            t.setColumnWidth(0, t.columnWidth(0) + ROW_THUMB_SIZE + 8)
        t.setSortingEnabled(True)
        fit_table_height(t, max_rows=8)
        self._lib_sec.set_title(f"Dark library ({len(darks)})")

    def _fill_captures(self, caps: list[dict]):
        t = self.captures_table
        t.setSortingEnabled(False)
        t.setRowCount(0)
        for c in sorted(caps, key=lambda c: (c.get("date") or "", c.get("object_dir") or ""),
                        reverse=True):
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, NumItem(c.get("date", ""), c.get("date", "")))
            obj = QTableWidgetItem(c.get("object_dir", ""))
            if c.get("slugs"):
                obj.setData(Qt.UserRole, c["slugs"][0])
            t.setItem(r, 1, obj)
            t.setItem(r, 2, _num(c.get("frames")))
            lo, hi = c.get("temp_min"), c.get("temp_max")
            t.setItem(r, 3, NumItem("—" if lo is None else f"{lo:g}–{hi:g}",
                                    -1e9 if hi is None else hi))
            t.setItem(r, 4, dark_gap_item(c))
            t.setItem(r, 5, QTableWidgetItem(c.get("dark_link") or "—"))
        t.resizeColumnsToContents()
        t.setSortingEnabled(True)
        fit_table_height(t, max_rows=10)
        self._cap_sec.set_title(f"Captures ({len(caps)})")

    def _on_capture_activated(self, item):
        obj = self.captures_table.item(item.row(), 1)
        slug = obj.data(Qt.UserRole) if obj is not None else None
        if slug:
            # never open/close a window from inside the item view's own handler
            defer(self, lambda: self._go(slug))

    def _go(self, slug: str):
        self.open_object.emit(slug)
        self.accept()
