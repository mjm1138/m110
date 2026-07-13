"""Site-profile editor — author one observing-location profile.

A small form over :mod:`m110.planning_config`'s writers: name, coordinates,
elevation, timezone, an optional physical **horizon** mask (imported ``.hrz``/CSV),
and the light-pollution scalars (Bortle / SQM — the azimuth-dependent glow floor
itself is authored by the light-dome tool in a later pass). Embedded in the
Planning page's "Manage site profiles" section; edits whichever profile the page's
location selector has active.

Coordinates can be entered by hand (the baseline) or filled from a place name via
the optional online geocode (`planning_config.geocode`), which degrades to a
no-op offline.
"""
from __future__ import annotations

from zoneinfo import available_timezones

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QSpinBox, QComboBox, QPushButton, QFileDialog, QMessageBox,
    QInputDialog,
)

from m110 import planning_config as pc


def _slugify(name: str) -> str:
    """A filename-safe stem from a display name (``Dark Site A`` → ``dark-site-a``)."""
    out = []
    for ch in (name or "").strip().lower():
        out.append(ch if ch.isalnum() else "-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "site"


class SiteProfileEditor(QWidget):
    saved = Signal(str)      # profile stem that was saved (name may have changed)
    deleted = Signal(str)    # profile stem that was deleted
    created = Signal(str)    # new profile stem (page should select it)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stem = pc.DEFAULT_PROFILE
        self._horizon_mask = ""     # stored filename (persisted on Save)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self._name = QLineEdit()
        form.addRow("Name:", self._name)

        self._lat = QDoubleSpinBox()
        self._lat.setRange(-90.0, 90.0)
        self._lat.setDecimals(5)
        self._lat.setSuffix("°  (+N)")
        self._lon = QDoubleSpinBox()
        self._lon.setRange(-180.0, 180.0)
        self._lon.setDecimals(5)
        self._lon.setSuffix("°  (+E)")
        form.addRow("Latitude:", self._lat)
        form.addRow("Longitude:", self._lon)

        self._elev = QDoubleSpinBox()
        self._elev.setRange(-430.0, 9000.0)
        self._elev.setDecimals(0)
        self._elev.setSuffix(" m")
        form.addRow("Elevation:", self._elev)

        self._tz = QComboBox()
        self._tz.setEditable(True)
        self._tz.addItems(sorted(available_timezones()))
        form.addRow("Timezone:", self._tz)

        self._bortle = QSpinBox()
        self._bortle.setRange(0, 9)
        self._bortle.setSpecialValueText("unset")     # 0 shows as "unset"
        self._sqm = QDoubleSpinBox()
        self._sqm.setRange(0.0, 22.0)
        self._sqm.setDecimals(2)
        self._sqm.setSpecialValueText("unset")
        self._sqm.setSuffix(" mag/arcsec²")
        form.addRow("Bortle class:", self._bortle)
        form.addRow("SQM (zenith):", self._sqm)
        lay.addLayout(form)

        # Horizon mask row.
        hrow = QHBoxLayout()
        hrow.addWidget(QLabel("Horizon mask:"))
        self._mask_label = QLabel("—")
        self._mask_label.setProperty("caption", True)
        hrow.addWidget(self._mask_label, 1)
        imp = QPushButton("Import…")
        imp.setToolTip("Import a Stellarium/NINA .hrz (or CSV) skyline file "
                       "(e.g. exported from theo.rocks).")
        imp.clicked.connect(self._import_horizon)
        clr = QPushButton("Clear")
        clr.clicked.connect(self._clear_horizon)
        hrow.addWidget(imp)
        hrow.addWidget(clr)
        lay.addLayout(hrow)

        # Actions.
        arow = QHBoxLayout()
        lookup = QPushButton("Look up location…")
        lookup.setToolTip("Fill latitude/longitude from a place name (online).")
        lookup.clicked.connect(self._lookup)
        arow.addWidget(lookup)
        arow.addStretch(1)
        newb = QPushButton("New…")
        newb.clicked.connect(self._new)
        self._delete = QPushButton("Delete")
        self._delete.clicked.connect(self._delete_profile)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._save)
        arow.addWidget(newb)
        arow.addWidget(self._delete)
        arow.addWidget(save)
        lay.addLayout(arow)

        # Dirty tracking: once the user edits a field, a background refresh (window
        # focus, etc.) must NOT reload the form and wipe the unsaved edits — the
        # Planning page checks `is_dirty()` before reloading. `_loading` suppresses
        # the change signals fired by `load()` itself. Cleared on load + Save.
        self._loading = False
        self._dirty = False
        for sig in (self._name.textEdited, self._lat.valueChanged,
                    self._lon.valueChanged, self._elev.valueChanged,
                    self._tz.editTextChanged, self._bortle.valueChanged,
                    self._sqm.valueChanged):
            sig.connect(self._mark_dirty)

        self.load(self._stem)

    # ---- dirty state ----
    def _mark_dirty(self, *_):
        if not self._loading:
            self._dirty = True

    def is_dirty(self) -> bool:
        return self._dirty

    def current_stem(self) -> str:
        return self._stem

    # ---- data ----
    def load(self, stem: str):
        """Populate the form from profile ``stem`` (resets any unsaved edits)."""
        self._loading = True
        try:
            self._stem = stem
            site = pc.load_site(stem)
            self._name.setText(site.name)
            self._lat.setValue(site.latitude_deg)
            self._lon.setValue(site.longitude_deg)
            self._elev.setValue(site.elevation_m)
            i = self._tz.findText(site.timezone)
            if i >= 0:
                self._tz.setCurrentIndex(i)
            else:
                self._tz.setEditText(site.timezone)
            self._bortle.setValue(int(site.bortle))
            self._sqm.setValue(site.sqm_zenith)
            self._horizon_mask = site.horizon_mask
            self._mask_label.setText(site.horizon_mask or "— none —")
            # The default profile must always exist as a fallback.
            self._delete.setEnabled(stem != pc.DEFAULT_PROFILE)
        finally:
            self._loading = False
            self._dirty = False

    def _current_site(self) -> pc.Site:
        return pc.Site(
            name=self._name.text().strip() or "Home",
            latitude_deg=self._lat.value(),
            longitude_deg=self._lon.value(),
            elevation_m=self._elev.value(),
            timezone=self._tz.currentText().strip() or "UTC",
            horizon_mask=self._horizon_mask,
            bortle=int(self._bortle.value()),
            sqm_zenith=self._sqm.value(),
        )

    # ---- actions ----
    def _save(self):
        site = self._current_site()
        try:
            pc.save_site(site, self._stem)
        except Exception as exc:
            QMessageBox.warning(self, "Couldn't save profile", str(exc))
            return
        self._dirty = False
        self.saved.emit(self._stem)

    def _new(self):
        name, ok = QInputDialog.getText(self, "New site profile", "Profile name:")
        if not ok or not name.strip():
            return
        stem = _slugify(name)
        if stem in pc.list_profiles():
            QMessageBox.warning(self, "Profile exists",
                                f"A profile named “{stem}” already exists.")
            return
        pc.save_site(pc.Site(name=name.strip()), stem)
        self.created.emit(stem)

    def _delete_profile(self):
        if self._stem == pc.DEFAULT_PROFILE:
            return
        if QMessageBox.question(
                self, "Delete profile",
                f"Delete the “{self._name.text()}” site profile?") \
                != QMessageBox.StandardButton.Yes:
            return
        pc.delete_profile(self._stem)
        self.deleted.emit(self._stem)

    def _import_horizon(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import horizon mask", "",
            "Horizon files (*.hrz *.csv *.txt);;All files (*)")
        if not path:
            return
        try:
            fname = pc.import_horizon_mask(path, self._stem)
        except Exception as exc:
            QMessageBox.warning(
                self, "Couldn't import mask",
                f"That file didn't parse as a horizon mask.\n\n{exc}")
            return
        self._horizon_mask = fname
        self._mask_label.setText(fname)
        self._mark_dirty()

    def _clear_horizon(self):
        self._horizon_mask = ""
        self._mask_label.setText("— none —")
        self._mark_dirty()

    def _lookup(self):
        query, ok = QInputDialog.getText(
            self, "Look up location", "Place (city, address, landmark):")
        if not ok or not query.strip():
            return
        result = pc.geocode(query)
        if result is None:
            QMessageBox.information(
                self, "Location not found",
                "Couldn't look that up (offline or no match). "
                "Enter latitude/longitude manually.")
            return
        lat, lon, display = result
        self._lat.setValue(lat)
        self._lon.setValue(lon)
        if not self._name.text().strip():
            self._name.setText(query.strip())
        QMessageBox.information(
            self, "Location found",
            f"{display}\n\nlat {lat:.5f}, lon {lon:.5f}\n\n"
            "Set the timezone to match, then Save.")
