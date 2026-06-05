"""Preferences dialog — choose where M110 stores its data."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox,
)

from m110 import config


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(620, 160)

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
        config.save_data_root(path)
        config.ensure_data_root(path)  # create + seed now so it's ready on restart
        QMessageBox.information(
            self, "Preferences saved",
            f"Data folder set to:\n{path}\n\nRestart M110 to use it.")
        self.accept()
