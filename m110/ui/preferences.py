"""Preferences dialog — data folder + processing-prep workflows."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QGroupBox, QCheckBox, QComboBox,
)

from m110 import config, processing
from m110.ui import theme


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(620, 340)

        from m110.ui.theme import tokens
        s = tokens.SPACE
        lay = QVBoxLayout(self)
        lay.setContentsMargins(s["lg"], s["lg"], s["lg"], s["lg"])
        lay.setSpacing(s["md"])
        lay.addWidget(QLabel("Data folder — where M110 stores its catalog, "
                             "captures, and renders:"))

        row = QHBoxLayout()
        self._edit = QLineEdit(str(config.DATA_ROOT))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self._edit)
        row.addWidget(browse)
        lay.addLayout(row)

        hint = QLabel(f"Default: {config.DEFAULT_DATA_ROOT}\n"
                      "The folder is created (with a starter catalog) if it doesn't exist. "
                      "Changing it applies on Close and takes effect after you restart M110.")
        hint.setProperty("caption", True)
        lay.addWidget(hint)

        # ── processing-prep workflows (persist live on toggle) ───────────────
        box = QGroupBox("Prepare objects for processing in:")
        bl = QVBoxLayout(box)
        bl.addWidget(QLabel(
            "M110 sets up a ready-to-go working folder for each object as you "
            "ingest it — pick your stacking app(s)."))
        enabled = set(processing.enabled_workflow_ids())
        self._wf_checks = {}
        for w in processing.WORKFLOWS:
            cb = QCheckBox(w.label if w.available else f"{w.label}  (soon)")
            cb.setChecked(w.available and w.id in enabled)
            cb.setEnabled(w.available)
            if not w.available:
                cb.setToolTip("Support for this workflow is coming.")
            bl.addWidget(cb)
            self._wf_checks[w.id] = cb
        # Wire after building so the initial setChecked() can't fire a half-built save.
        for cb in self._wf_checks.values():
            cb.toggled.connect(self._save_workflows)
        lay.addWidget(box)

        # ── appearance (theme) ───────────────────────────────────────────────
        appearance = QGroupBox("Appearance")
        al = QHBoxLayout(appearance)
        al.addWidget(QLabel("Theme:"))
        self._theme_combo = QComboBox()
        for mode, label in (("system", "Follow system"), ("light", "Light"),
                            ("dark", "Dark")):
            self._theme_combo.addItem(label, mode)
        cur = config.get_setting(theme.SETTING_KEY, "system")
        idx = self._theme_combo.findData(cur)
        self._theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        # Apply live as the user changes it (no restart; mirrors the workflows).
        self._theme_combo.currentIndexChanged.connect(
            lambda *_: theme.set_mode(self._theme_combo.currentData()))
        al.addWidget(self._theme_combo, 1)
        lay.addWidget(appearance)

        # Goals (catalogs / custom lists) are managed on the Goals page, not here.

        # Settings here persist live (workflows + theme); only the data folder is
        # applied on Close (it needs a restart), so a single Close button suffices
        # — no "Save" (#62).
        btns = QHBoxLayout()
        btns.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self._close)
        btns.addWidget(close)
        lay.addLayout(btns)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose data folder", self._edit.text())
        if d:
            self._edit.setText(d)

    def _save_workflows(self, *_):
        """Persist the processing-workflow selection immediately (read at ingest
        time — no restart)."""
        chosen = [wid for wid, cb in self._wf_checks.items()
                  if cb.isEnabled() and cb.isChecked()]
        config.save_setting(processing.SETTING_KEY, chosen)

    def _close(self):
        """Apply a data-folder change (if any) on the way out, then close.
        Workflows + theme were already persisted live."""
        path = self._edit.text().strip()
        if path and path != str(config.DATA_ROOT):
            config.save_data_root(path)
            config.ensure_data_root(path)   # create + seed now, ready on restart
            QMessageBox.information(
                self, "Restart needed",
                f"Data folder set to:\n{path}\n\nRestart M110 to use it.")
        self.accept()
