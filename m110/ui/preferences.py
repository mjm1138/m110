"""Preferences dialog — data folder + processing-prep workflows."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QGroupBox, QCheckBox,
)

from m110 import config, processing


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(620, 340)

        lay = QVBoxLayout(self)
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
                      "Changing it takes effect after you restart M110.")
        hint.setStyleSheet("color:#8b949e; font-size:11px")
        lay.addWidget(hint)

        # ── processing-prep workflows ────────────────────────────────────────
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
        lay.addWidget(box)

        btns = QHBoxLayout()
        btns.addStretch(1)
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(save)
        btns.addWidget(cancel)
        lay.addLayout(btns)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose data folder", self._edit.text())
        if d:
            self._edit.setText(d)

    def _save(self):
        path = self._edit.text().strip()
        if not path:
            return
        # Workflows take effect immediately (read at ingest time) — no restart.
        chosen = [wid for wid, cb in self._wf_checks.items()
                  if cb.isEnabled() and cb.isChecked()]
        config.save_setting(processing.SETTING_KEY, chosen)

        root_changed = path != str(config.DATA_ROOT)
        config.save_data_root(path)
        config.ensure_data_root(path)   # create + seed now so it's ready on restart
        msg = "Preferences saved."
        if root_changed:
            msg += f"\n\nData folder set to:\n{path}\nRestart M110 to use it."
        QMessageBox.information(self, "Preferences saved", msg)
        self.accept()
