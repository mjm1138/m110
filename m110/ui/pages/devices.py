"""Devices page — every telescope M110 has seen, as a first-class view.

A device is *discovered* (each TELESCOP a capture names, each
``Calibration/<device>/`` library); what the user says about it — a nickname,
the model when M110 can't tell, retired — lives in the per-store registry
(`devices.devices.toml`). Everything else is read from ``derived/devices.json``
(`calibration.device_rollup`, written on every Sync), so the page is instant
and needs no worker.

Layout follows the Library: a device list on the left, the selected device's
detail on the right — identity, the objects it shot, its dark library, its
captures and its sensor health. A Seestar dark-subtracts on the telescope, so
which library dark a capture got is *inferred* (calibration rule v2); the dark
library and the captures name a dark the same way ("Oct 15 21:52 · 13.9 °C"),
and selecting a row in either table highlights its partners in the other.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QSpinBox,
    QLineEdit, QMenu, QPushButton, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from m110 import config, derived, devices, integration_goals, refresh
from m110 import planning_config as pc
from m110.planning_config import DEVICE_PRESETS
from m110.ui import theme
from m110.ui.widgets import (
    CollapsibleSection, NumItem, ROW_THUMB_SIZE, ThumbnailLoader, connect_context_menu,
    dark_gap_item, defer, fit_table_height, make_numeric, make_table, reveal_in_manager,
    reveal_label,
)

_LIST_COLS = ["Device", "Last capture", "Integration", "Model"]
_OBJ_COLS = ["Object", "Integration", "Sessions", "Frames"]
_LIB_COLS = ["Dark", "Exp (s)", "Gain", "Frames", "Median", "Hot px", "Captures"]
_CAP_COLS = ["Date", "Object", "Frames", "Sensor (°C)", "Dark", "Link"]


def _num(v, fmt="{:g}") -> NumItem:
    return make_numeric(NumItem("—" if v is None else fmt.format(v),
                                -1e9 if v is None else v))


def _hm(minutes: float | None) -> NumItem:
    m = int(round(minutes or 0))
    return make_numeric(NumItem(f"{m // 60}:{m % 60:02d}", minutes or 0.0))


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


class DevicesPage(QWidget):
    """The Devices nav page: a device list and the selected device's detail."""

    open_object = Signal(str)
    # A telescope's model or optics changed, which moves integration goals and so
    # statuses; derived data is already rebuilt.
    goals_changed = Signal()
    # A telescope's name, the planning telescope or its limits changed: pages that
    # show telescopes (Planning's picker, session tables) must re-read them.
    devices_changed = Signal()

    def __init__(self, parent=None, devices_data: list[dict] | None = None):
        super().__init__(parent)
        self._fixed = devices_data              # tests inject; else derived.load_devices()
        self._devices: list[dict] = []
        self._current: dict | None = None
        self._syncing = False                   # cross-selection re-entrancy guard
        self._thumbs = ThumbnailLoader(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Horizontal)
        lay.addWidget(self.splitter)

        # ── left: the device list ──
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        self.show_retired = QCheckBox("Show retired")
        self.show_retired.toggled.connect(lambda _on: self._fill_list())
        ll.addWidget(self.show_retired)
        self.device_list = make_table(_LIST_COLS, stretch_last=True)
        # the rollup's order is the meaningful one (most recent capture first,
        # retired last) — not an alphabetical sort of the labels
        self.device_list.setSortingEnabled(False)
        self.device_list.itemSelectionChanged.connect(self._on_device_selected)
        ll.addWidget(self.device_list, 1)
        self._empty = QLabel("No devices yet — import from a telescope; M110 learns "
                             "each one from the captures it brings in.")
        self._empty.setWordWrap(True)
        ll.addWidget(self._empty)
        self.splitter.addWidget(left)

        # ── right: the selected device ──
        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setAlignment(Qt.AlignTop)
        self._heading = QLabel()
        self._heading.setTextFormat(Qt.RichText)
        self._heading.setWordWrap(True)
        self._body.addWidget(self._heading)

        self._id_sec = CollapsibleSection("Identity")
        form = QFormLayout()
        self.nickname = QLineEdit()
        self.nickname.setPlaceholderText("e.g. Backyard S50")
        self.nickname.textChanged.connect(self._on_identity_edited)
        form.addRow("Nickname", self.nickname)
        self.model = QComboBox()
        self.model.addItem("Recognised from its headers", None)
        for key, dev in DEVICE_PRESETS.items():
            self.model.addItem(dev.name, key)
        self.model.currentIndexChanged.connect(self._on_identity_edited)
        form.addRow("Model", self.model)
        self.serial = QLabel()
        form.addRow("Serial / TELESCOP", self.serial)
        self.retired = QCheckBox("Retired — hide it from the list and pickers")
        self.retired.toggled.connect(self._on_identity_edited)
        form.addRow("", self.retired)
        self._id_sec.body.addLayout(form)
        btns = QHBoxLayout()
        btns.addStretch(1)
        self.revert_btn = QPushButton("Revert")
        self.revert_btn.clicked.connect(self._revert_identity)
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save_identity)
        btns.addWidget(self.revert_btn)
        btns.addWidget(self.save_btn)
        self._id_sec.body.addLayout(btns)

        # planning (PR B): the active planning telescope + its limit overrides
        self._plan_sec = CollapsibleSection("Planning")
        prow = QHBoxLayout()
        self.planning_state = QLabel()
        prow.addWidget(self.planning_state, 1)
        self.use_for_planning = QPushButton("Use for planning")
        self.use_for_planning.clicked.connect(self._use_for_planning)
        prow.addWidget(self.use_for_planning)
        self._plan_sec.body.addLayout(prow)
        pform = QFormLayout()
        self.ceiling = QDoubleSpinBox()
        self.ceiling.setRange(30.0, 90.0)
        self.ceiling.setDecimals(1)
        self.ceiling.setSuffix(" °")
        self.ceiling.valueChanged.connect(self._on_limits_edited)
        pform.addRow("Start ceiling", self.ceiling)
        self.ceiling_hard = QCheckBox("Hard — the telescope refuses to start above it")
        self.ceiling_hard.toggled.connect(self._on_limits_edited)
        pform.addRow("", self.ceiling_hard)
        self.floor = QDoubleSpinBox()
        self.floor.setRange(0.0, 60.0)
        self.floor.setDecimals(1)
        self.floor.setSuffix(" °")
        self.floor.valueChanged.connect(self._on_limits_edited)
        pform.addRow("Low-altitude floor", self.floor)
        self.max_exposure = QSpinBox()
        self.max_exposure.setRange(1, 600)
        self.max_exposure.setSuffix(" s")
        self.max_exposure.valueChanged.connect(self._on_limits_edited)
        pform.addRow("Longest exposure", self.max_exposure)
        self.default_exposure = QSpinBox()
        self.default_exposure.setRange(1, 600)
        self.default_exposure.setSuffix(" s")
        self.default_exposure.valueChanged.connect(self._on_limits_edited)
        pform.addRow("Default exposure", self.default_exposure)
        self.gain = QSpinBox()
        self.gain.setRange(0, 1000)
        self.gain.valueChanged.connect(self._on_limits_edited)
        pform.addRow("Gain", self.gain)
        self._plan_sec.body.addLayout(pform)
        lbtns = QHBoxLayout()
        self.limits_note = QLabel()
        self.limits_note.setWordWrap(True)
        lbtns.addWidget(self.limits_note, 1)
        self.limits_defaults_btn = QPushButton("Model defaults")
        self.limits_defaults_btn.clicked.connect(self._limits_to_defaults)
        self.limits_save_btn = QPushButton("Save limits")
        self.limits_save_btn.clicked.connect(self._save_limits)
        lbtns.addWidget(self.limits_defaults_btn)
        lbtns.addWidget(self.limits_save_btn)
        self._plan_sec.body.addLayout(lbtns)

        # optics (#184): the f-ratio that scales this telescope's integration goals
        self._optics_sec = CollapsibleSection("Optics")
        self.optics_summary = QLabel()
        self.optics_summary.setWordWrap(True)
        self.optics_summary.setTextFormat(Qt.RichText)
        self._optics_sec.body.addWidget(self.optics_summary)
        self._optics_form = QWidget()
        oform = QFormLayout(self._optics_form)
        oform.setContentsMargins(0, 0, 0, 0)
        self.aperture = QDoubleSpinBox()
        self.focal_length = QDoubleSpinBox()
        self.pixel = QDoubleSpinBox()
        for spin, top, suffix, label in ((self.aperture, 1000.0, " mm", "Aperture"),
                                         (self.focal_length, 5000.0, " mm", "Focal length"),
                                         (self.pixel, 30.0, " µm", "Pixel size")):
            spin.setRange(0.0, top)
            spin.setDecimals(2 if spin is self.pixel else 1)
            spin.setSuffix(suffix)
            spin.setSpecialValueText("unknown")       # 0 = not entered
            oform.addRow(label, spin)
        obtns = QHBoxLayout()
        obtns.addStretch(1)
        self.optics_save_btn = QPushButton("Save optics")
        self.optics_save_btn.clicked.connect(self._save_optics)
        obtns.addWidget(self.optics_save_btn)
        oform.addRow(obtns)
        self._optics_sec.body.addWidget(self._optics_form)

        self._obj_sec = CollapsibleSection("Objects")
        self.objects_table = make_table(_OBJ_COLS)
        self.objects_table.sortByColumn(1, Qt.DescendingOrder)     # most integration first
        self.objects_table.itemDoubleClicked.connect(self._on_object_activated)
        self._obj_sec.body.addWidget(self.objects_table)

        self._lib_sec = CollapsibleSection("Dark library")
        self.library_table = make_table(_LIB_COLS)
        self.library_table.sortByColumn(0, Qt.AscendingOrder)      # oldest dark first
        self.library_table.setIconSize(QSize(ROW_THUMB_SIZE, ROW_THUMB_SIZE))
        self.library_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.library_table.itemSelectionChanged.connect(self._on_dark_selected)
        connect_context_menu(self.library_table, self._show_library_menu)
        self._lib_sec.body.addWidget(self.library_table)

        self._cap_sec = CollapsibleSection("Captures")
        self.captures_table = make_table(_CAP_COLS)
        self.captures_table.sortByColumn(0, Qt.DescendingOrder)    # newest capture first
        self.captures_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.captures_table.itemSelectionChanged.connect(self._on_capture_selected)
        self.captures_table.itemDoubleClicked.connect(self._on_capture_activated)
        connect_context_menu(self.captures_table, self._show_capture_menu)
        self._cap_sec.body.addWidget(self.captures_table)

        self._health_sec = CollapsibleSection("Sensor health")
        self.level_chart = SensorChart("Dark level (median ADU) vs temperature", "median")
        self.hot_chart = SensorChart("Hot pixels vs temperature", "hot_px")
        self._health_sec.body.addWidget(self.level_chart)
        self._health_sec.body.addWidget(self.hot_chart)

        for sec in (self._id_sec, self._plan_sec, self._optics_sec, self._obj_sec,
                    self._lib_sec, self._cap_sec, self._health_sec):
            self._body.addWidget(sec)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(body)
        self.splitter.addWidget(self._scroll)
        self.splitter.setSizes([420, 640])

        self.reload()

    # ── data ──────────────────────────────────────────────────────────────────

    def reload(self):
        """Re-read the rollup + registry; keep the selected device if it remains."""
        keep = self._current["device"] if self._current else None
        self._devices = ([n for n in map(derived.normalize_device, self._fixed) if n]
                         if self._fixed is not None else derived.load_devices())
        self._fill_list(select=keep)

    def restyle(self):
        if self._current:
            self._show_device(self._current)

    def select_device(self, key: str) -> bool:
        for r in range(self.device_list.rowCount()):
            if self.device_list.item(r, 0).data(Qt.UserRole) == key:
                self.device_list.selectRow(r)
                return True
        return False

    def _visible_devices(self) -> list[dict]:
        return [d for d in self._devices
                if self.show_retired.isChecked() or not d.get("retired")]

    def _fill_list(self, select: str | None = None):
        if select is None and self._current:
            select = self._current["device"]
        t = self.device_list
        t.blockSignals(True)
        t.setRowCount(0)
        muted = theme.muted_color()
        for d in self._visible_devices():
            r = t.rowCount()
            t.insertRow(r)
            name = QTableWidgetItem(d.get("label") or d["device"])
            name.setData(Qt.UserRole, d["device"])
            items = [name,
                     NumItem(d["totals"].get("last_capture") or "—",
                             d["totals"].get("last_capture") or ""),
                     _hm(d["totals"].get("integration_min")),
                     QTableWidgetItem(d.get("model") or "—")]
            for c, it in enumerate(items):
                if d.get("retired"):
                    it.setForeground(muted)
                    it.setToolTip("Retired")
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.blockSignals(False)
        has = t.rowCount() > 0
        self._empty.setVisible(not has)
        self._scroll.setVisible(has)
        if not has:
            self._current = None
            return
        if not (select and self.select_device(select)):
            t.selectRow(0)
        self._on_device_selected()

    def _on_device_selected(self):
        rows = self.device_list.selectionModel().selectedRows()
        if not rows:
            return
        key = self.device_list.item(rows[0].row(), 0).data(Qt.UserRole)
        d = next((x for x in self._devices if x["device"] == key), None)
        if d is not None:
            self._show_device(d)

    # ── one device ────────────────────────────────────────────────────────────

    def _show_device(self, d: dict):
        self._current = d
        darks = [m for m in d.get("masters", []) if m.get("tier") == "darks"]
        tot = d.get("totals", {})
        bits = []
        if d.get("model"):
            bits.append(d["model"])
        if tot.get("sessions"):
            m = int(round(tot.get("integration_min") or 0))
            bits.append(f"{m // 60} h {m % 60:02d} m over {tot['nights']} night"
                        f"{'s' if tot['nights'] != 1 else ''}, {tot['objects']} object"
                        f"{'s' if tot['objects'] != 1 else ''}")
        if d.get("darks_applied_on_device"):
            bits.append("subs are dark-subtracted on the telescope; its darks are kept "
                        "for reference and never applied again")
        sub = theme.active_tokens().text_secondary
        self._heading.setText(f"<b>{d.get('label') or d['device']}</b>"
                              f"<br><span style='color:{sub}'>{' · '.join(bits)}</span>")
        self._load_identity(d)
        self._fill_objects(d.get("objects", []))
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
        self._id_sec.setVisible(d["device"] != devices.UNKNOWN)
        self._plan_sec.setVisible(d["device"] != devices.UNKNOWN and not d.get("retired"))
        self._load_planning(d)
        self._optics_sec.setVisible(d["device"] != devices.UNKNOWN)
        self._load_optics(d)

    # identity (the registry) ------------------------------------------------

    def _load_identity(self, d: dict):
        for w in (self.nickname, self.model, self.retired):
            w.blockSignals(True)
        self.nickname.setText(d.get("nickname") or "")
        i = self.model.findData(d.get("preset") if devices.preset_key(d["device"]) is None
                                else None)
        self.model.setCurrentIndex(max(i, 0))
        self.serial.setText(d["device"])
        self.retired.setChecked(bool(d.get("retired")))
        for w in (self.nickname, self.model, self.retired):
            w.blockSignals(False)
        self._set_dirty(False)

    def _identity_fields(self) -> dict:
        return {"nickname": self.nickname.text().strip() or None,
                "preset": self.model.currentData(),
                "retired": self.retired.isChecked()}

    def _on_identity_edited(self, *_):
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool):
        self.save_btn.setEnabled(dirty)
        self.revert_btn.setEnabled(dirty)

    def _revert_identity(self):
        if self._current:
            self._load_identity(self._current)

    def _save_identity(self):
        if not self._current:
            return
        key = self._current["device"]
        f = self._identity_fields()
        model_before = integration_goals.model_key(key)
        devices.save_device(key, **f)
        # reflect it now; the next Sync rewrites devices.json with the same facts
        reg = devices.load_registry()
        for d in self._devices:
            if d["device"] == key:
                d["nickname"] = f["nickname"]
                d["retired"] = f["retired"]
                d["preset"] = devices.effective_preset(key, reg)
                d["model"] = devices.model_name(key, reg)
                d["label"] = devices.label(key, reg)
        self._set_dirty(False)
        self._fill_list(select=key if (not f["retired"] or self.show_retired.isChecked())
                        else None)
        if integration_goals.model_key(key) != model_before:
            self._goals_moved()               # a new model means different goals
        else:
            self.devices_changed.emit()       # a new name or retirement shows elsewhere

    # optics -----------------------------------------------------------------

    def _load_optics(self, d: dict):
        """A recognised telescope shows its model's published optics (read-only);
        one no preset describes can have them entered here, which is what gives it
        a calibrated integration-goal default."""
        key = d["device"]
        preset = devices.effective_preset(key)
        if preset in DEVICE_PRESETS:
            dev = DEVICE_PRESETS[preset]
            optics = {"aperture_mm": dev.aperture_mm, "focal_length_mm": dev.focal_length_mm,
                      "pixel_um": dev.pixel_um}
        else:
            optics = devices.load_registry().get(key, {}).get("optics", {})
        self._optics_form.setVisible(preset not in DEVICE_PRESETS)
        for spin, name in ((self.aperture, "aperture_mm"),
                           (self.focal_length, "focal_length_mm"), (self.pixel, "pixel_um")):
            spin.setValue(optics.get(name) or 0.0)
        self.optics_summary.setText(self._optics_text(key, optics, preset in DEVICE_PRESETS))

    @staticmethod
    def _optics_text(key: str, optics: dict, recognised: bool) -> str:
        ap, fl, px = (optics.get(n) for n in ("aperture_mm", "focal_length_mm", "pixel_um"))
        bits = []
        if ap:
            bits.append(f"{ap:g} mm aperture")
        if fl:
            bits.append(f"{fl:g} mm focal length")
        if ap and fl:
            bits.append(f"f/{fl / ap:.1f}")
        if px:
            bits.append(f"{px:g} µm pixels")
        model = integration_goals.model_key(key)
        factor, calibrated = integration_goals.speed_factor(model)
        if model == integration_goals.REFERENCE_MODEL:
            scale = "The reference telescope: integration-goal defaults are its numbers."
        elif calibrated:
            scale = (f"Integration goals here are ×{factor:.2f} the S50's "
                     f"({'faster' if factor < 1 else 'slower' if factor > 1 else 'same'} "
                     f"f-ratio).")
        else:
            scale = ("Its f-ratio is unknown, so its integration goals use the S50's "
                     "numbers — enter the aperture and focal length to scale them.")
        source = "From the model's published specs. " if recognised else ""
        head = " · ".join(bits) if bits else "No optics entered."
        return f"{head}<br><span>{source}{scale}</span>"

    def _save_optics(self):
        if not self._current:
            return
        key = self._current["device"]
        optics = {name: spin.value() for spin, name in (
            (self.aperture, "aperture_mm"), (self.focal_length, "focal_length_mm"),
            (self.pixel, "pixel_um")) if spin.value() > 0}
        devices.save_device(key, optics=optics or None)
        self.optics_summary.setText(self._optics_text(key, optics, False))
        self._goals_moved()

    def _goals_moved(self):
        """Statuses depend on a telescope's model and optics: rebuild derived data
        (no scan) and let the shell reload — deferred, as that reload rebuilds this
        page under the button that asked for it."""
        refresh.rederive()
        defer(self, self.goals_changed.emit)

    # planning (the active telescope + its limits) ------------------------------

    _LIMIT_NAMES = {"start_alt_ceiling_deg": "start ceiling", "ceiling_is_hard": "hard ceiling",
                    "low_alt_floor_deg": "low-altitude floor",
                    "max_exposure_s": "longest exposure",
                    "default_exposure_s": "default exposure", "gain": "gain"}

    _LIMIT_WIDGETS = (("start_alt_ceiling_deg", "ceiling"), ("ceiling_is_hard", "ceiling_hard"),
                      ("low_alt_floor_deg", "floor"), ("max_exposure_s", "max_exposure"),
                      ("default_exposure_s", "default_exposure"), ("gain", "gain"))

    def _model_defaults(self, key: str):
        preset = devices.effective_preset(key)
        return DEVICE_PRESETS.get(preset or "", pc.Device())

    def _load_planning(self, d: dict):
        key = d["device"]
        active = pc.active_device_key() == key
        self.planning_state.setText("<b>Planning plans for this telescope.</b>" if active
                                    else "Planning plans for another telescope.")
        self.use_for_planning.setVisible(not active)
        self._show_limits(pc.device_for(key))
        self._refresh_limits_note(key)

    def _show_limits(self, dev):
        widgets = [getattr(self, w) for _, w in self._LIMIT_WIDGETS]
        for w in widgets:
            w.blockSignals(True)
        self.ceiling.setValue(dev.start_alt_ceiling_deg or 90.0)
        self.ceiling_hard.setChecked(bool(dev.ceiling_is_hard))
        self.floor.setValue(dev.low_alt_floor_deg)
        self.max_exposure.setValue(int(dev.max_exposure_s))
        self.default_exposure.setValue(int(dev.default_exposure_s))
        self.gain.setValue(int(dev.gain))
        for w in widgets:
            w.blockSignals(False)
        self.limits_save_btn.setEnabled(False)

    def _limits_overrides(self, key: str) -> dict:
        """The edited limits that differ from the telescope's model defaults —
        only those are stored, so a later preset correction still reaches it."""
        base = self._model_defaults(key)
        vals = {"start_alt_ceiling_deg": self.ceiling.value(),
                "ceiling_is_hard": self.ceiling_hard.isChecked(),
                "low_alt_floor_deg": self.floor.value(),
                "max_exposure_s": self.max_exposure.value(),
                "default_exposure_s": self.default_exposure.value(),
                "gain": self.gain.value()}
        return {k: v for k, v in vals.items() if getattr(base, k) != v}

    def _refresh_limits_note(self, key: str):
        changed = self._limits_overrides(key)
        model = devices.model_name(key) or "Seestar S50 defaults"
        self.limits_note.setText(f"Your changes to the {model} limits: "
                                 + ", ".join(self._LIMIT_NAMES[k] for k in changed)
                                 if changed else f"Using the {model} limits.")
        self.limits_defaults_btn.setEnabled(bool(changed))

    def _on_limits_edited(self, *_):
        self.limits_save_btn.setEnabled(True)
        if self._current:
            self._refresh_limits_note(self._current["device"])

    def _limits_to_defaults(self):
        if self._current:
            self._show_limits(self._model_defaults(self._current["device"]))
            self.limits_save_btn.setEnabled(True)
            self._refresh_limits_note(self._current["device"])

    def _save_limits(self):
        if not self._current:
            return
        key = self._current["device"]
        devices.save_device(key, planning=self._limits_overrides(key) or None)
        self.limits_save_btn.setEnabled(False)
        self._refresh_limits_note(key)
        self.devices_changed.emit()

    def _use_for_planning(self):
        if self._current:
            pc.set_active_device(self._current["device"])
            self._load_planning(self._current)
            self.devices_changed.emit()

    # objects ------------------------------------------------------------------

    def _fill_objects(self, objs: list[dict]):
        t = self.objects_table
        t.setSortingEnabled(False)
        t.setRowCount(0)
        for o in objs:
            r = t.rowCount()
            t.insertRow(r)
            name = QTableWidgetItem(o.get("id") or o["slug"])
            name.setData(Qt.UserRole, o["slug"])
            t.setItem(r, 0, name)
            t.setItem(r, 1, _hm(o.get("integration_min")))
            t.setItem(r, 2, _num(o.get("session_count")))
            t.setItem(r, 3, _num(o.get("frames")))
        t.resizeColumnsToContents()
        t.setSortingEnabled(True)
        fit_table_height(t, max_rows=8)
        self._obj_sec.set_title(f"Objects ({len(objs)})")

    def _on_object_activated(self, item):
        slug = self.objects_table.item(item.row(), 0).data(Qt.UserRole)
        if slug:
            defer(self, lambda: self.open_object.emit(slug))

    # dark library ------------------------------------------------------------

    def _fill_library(self, darks: list[dict]):
        t = self.library_table
        t.blockSignals(True)
        t.setSortingEnabled(False)
        t.setRowCount(0)
        for m in darks:
            r = t.rowCount()
            t.insertRow(r)
            item = NumItem(m.get("label") or m["file"], m.get("made") or m["file"])
            item.setData(Qt.UserRole, m["file"])
            item.setData(Qt.UserRole + 1, m.get("rel"))
            item.setToolTip(m.get("rel", m["file"]))
            t.setItem(r, 0, item)
            if m.get("preview"):
                self._thumbs.request(Path(config.DATA_ROOT) / m["preview"], ROW_THUMB_SIZE,
                                     lambda pm, it=item: _set_icon(it, pm))
            t.setItem(r, 1, _num(m.get("exptime")))
            t.setItem(r, 2, _num(m.get("gain")))
            t.setItem(r, 3, _num(m.get("frames")))
            t.setItem(r, 4, _num(m.get("median"), "{:.0f}"))
            t.setItem(r, 5, _num(m.get("hot_px")))
            t.setItem(r, 6, _num(m.get("captures")))
        t.resizeColumnsToContents()
        if any(m.get("preview") for m in darks):     # icons arrive after the resize
            t.setColumnWidth(0, t.columnWidth(0) + ROW_THUMB_SIZE + 8)
        t.setSortingEnabled(True)
        t.blockSignals(False)
        fit_table_height(t, max_rows=8)
        self._lib_sec.set_title(f"Dark library ({len(darks)})")

    def _dark_file(self, row: int) -> str | None:
        it = self.library_table.item(row, 0)
        return it.data(Qt.UserRole) if it else None

    def _dark_path(self, file: str) -> Path | None:
        for m in (self._current or {}).get("masters", []):
            if m["file"] == file and m.get("rel"):
                return Path(config.DATA_ROOT) / m["rel"]
        return None

    # captures ----------------------------------------------------------------

    def _fill_captures(self, caps: list[dict]):
        t = self.captures_table
        t.blockSignals(True)
        t.setSortingEnabled(False)
        t.setRowCount(0)
        for c in sorted(caps, key=lambda c: (c.get("date") or "", c.get("object_dir") or ""),
                        reverse=True):
            r = t.rowCount()
            t.insertRow(r)
            date = NumItem(c.get("date", ""), c.get("date", ""))
            date.setData(Qt.UserRole, c)
            t.setItem(r, 0, date)
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
        t.blockSignals(False)
        fit_table_height(t, max_rows=10)
        self._cap_sec.set_title(f"Captures ({len(caps)})")

    def _capture(self, row: int) -> dict | None:
        it = self.captures_table.item(row, 0)
        return it.data(Qt.UserRole) if it else None

    def _on_capture_activated(self, item):
        obj = self.captures_table.item(item.row(), 1)
        slug = obj.data(Qt.UserRole) if obj is not None else None
        if slug:
            # never open a window from inside the item view's own handler
            defer(self, lambda: self.open_object.emit(slug))

    # cross-selection ---------------------------------------------------------

    def _on_capture_selected(self):
        if self._syncing:
            return
        refs = set()
        for idx in self.captures_table.selectionModel().selectedRows():
            refs |= set((self._capture(idx.row()) or {}).get("dark_refs") or [])
        self._select_rows(self.library_table, lambda r: self._dark_file(r) in refs)

    def _on_dark_selected(self):
        if self._syncing:
            return
        files = {self._dark_file(i.row())
                 for i in self.library_table.selectionModel().selectedRows()}
        self._select_rows(self.captures_table,
                          lambda r: bool(files & set((self._capture(r) or {})
                                                     .get("dark_refs") or [])))

    def _select_rows(self, table: QTableWidget, match) -> None:
        """Select exactly the rows of `table` where `match(row)`, scroll to the
        first — without re-triggering the other table's handler."""
        self._syncing = True
        try:
            sel = QItemSelection()
            first = None
            last_col = table.columnCount() - 1
            for r in range(table.rowCount()):
                if match(r):
                    sel.select(table.model().index(r, 0), table.model().index(r, last_col))
                    first = r if first is None else first
            table.selectionModel().select(sel, QItemSelectionModel.ClearAndSelect)
            if first is not None:
                table.scrollToItem(table.item(first, 0))
        finally:
            self._syncing = False

    # context menus (built headless-testably, executed off the view's handler) -

    def _library_menu(self, row: int):
        menu = QMenu(self)
        file = self._dark_file(row)
        path = self._dark_path(file) if file else None
        actions = {"reveal": menu.addAction(reveal_label())}
        actions["reveal"].setEnabled(path is not None)
        actions["captures"] = menu.addAction("Select the captures it served")
        return menu, actions

    def _show_library_menu(self, pos):
        it = self.library_table.itemAt(pos)
        if it is None:
            return
        row = it.row()
        menu, actions = self._library_menu(row)
        chosen = menu.exec(self.library_table.viewport().mapToGlobal(pos))
        file = self._dark_file(row)
        if chosen is actions["reveal"] and file:
            reveal_in_manager(self._dark_path(file))
        elif chosen is actions["captures"] and file:
            self._select_rows(self.library_table, lambda r: self._dark_file(r) == file)
            self._on_dark_selected()

    def _capture_menu(self, row: int):
        menu = QMenu(self)
        cap = self._capture(row) or {}
        refs = cap.get("dark_refs") or []
        labels = cap.get("dark_labels") or refs
        actions: dict = {}
        if len(refs) == 1:
            actions[("dark", refs[0])] = menu.addAction(f"{reveal_label()}: dark {labels[0]}")
        elif refs:
            sub = menu.addMenu(f"{reveal_label()}: a dark it used")
            for ref, lab in zip(refs, labels):
                actions[("dark", ref)] = sub.addAction(lab)
        for key, act in actions.items():
            act.setEnabled(self._dark_path(key[1]) is not None)
        actions["lights"] = menu.addAction(f"{reveal_label()}: its lights folder")
        actions["lights"].setEnabled(bool(cap.get("lights_rel")))
        menu.addSeparator()
        actions["open"] = menu.addAction("Open object")
        actions["open"].setEnabled(bool(cap.get("slugs")))
        return menu, actions

    def _show_capture_menu(self, pos):
        it = self.captures_table.itemAt(pos)
        if it is None:
            return
        row = it.row()
        menu, actions = self._capture_menu(row)
        chosen = menu.exec(self.captures_table.viewport().mapToGlobal(pos))
        self._run_capture_action(row, chosen, actions)

    def _run_capture_action(self, row: int, chosen, actions: dict):
        cap = self._capture(row) or {}
        for key, act in actions.items():
            if chosen is not act:
                continue
            if isinstance(key, tuple):
                reveal_in_manager(self._dark_path(key[1]))
            elif key == "lights":
                reveal_in_manager(Path(config.DATA_ROOT) / cap["lights_rel"])
            elif key == "open" and cap.get("slugs"):
                self.open_object.emit(cap["slugs"][0])
