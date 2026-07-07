"""First-launch welcome — choose where M110 keeps its data, once.

Shown by `main()` only on a genuine first run (`config.is_first_run()`), before the
main window, so a new user picks a data folder instead of the app silently
defaulting to `~/Documents/M110`. Accepting (default or a chosen folder) persists
the preference and bootstraps the store; there's no re-prompt on later launches.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QDialogButtonBox,
)

from m110 import config
from m110.ui import theme


class FirstRunDialog(QDialog):
    TAGLINE = "Complete the catalog."

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to M110")
        self.setModal(True)
        self.setMinimumWidth(560)
        t = theme.active_tokens()
        s = theme.tokens.SPACE

        lay = QVBoxLayout(self)
        lay.setContentsMargins(s["xxl"], s["xl"], s["xxl"], s["lg"])
        lay.setSpacing(s["sm"])

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dpr = self.devicePixelRatioF() or 1.0
        logo.setPixmap(theme.logo_pixmap(60, theme.ink_color(), dpr))
        lay.addWidget(logo)

        tagline = QLabel(self.TAGLINE)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(
            f"color:{t.text_secondary}; font-style:italic; "
            f"font-size:{theme.tokens.FONT_SIZE['section']}px; margin-bottom:{s['md']}px;")
        lay.addWidget(tagline)

        blurb = QLabel(
            "M110 organizes your smart-telescope deep-sky collection — importing, "
            "tracking, and preparing your captures for processing.\n\n"
            "Choose where M110 should keep its data (your captures, catalog, and "
            "renders live here). You can move it later in Preferences.")
        blurb.setWordWrap(True)
        blurb.setStyleSheet(f"color:{t.text_secondary};")
        lay.addWidget(blurb)

        row = QHBoxLayout()
        self._edit = QLineEdit(str(config.DEFAULT_DATA_ROOT))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self._edit, 1)
        row.addWidget(browse)
        lay.addSpacing(s["sm"])
        lay.addLayout(row)

        hint = QLabel("Created (with a starter catalog) if it doesn't exist yet.")
        hint.setProperty("caption", True)
        lay.addWidget(hint)

        buttons = QDialogButtonBox()
        self._ok = buttons.addButton("Get started", QDialogButtonBox.ButtonRole.AcceptRole)
        self._ok.setDefault(True)
        buttons.accepted.connect(self._accept)
        lay.addSpacing(s["md"])
        lay.addWidget(buttons)

    def chosen_path(self) -> str:
        return self._edit.text().strip()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Choose your M110 data folder", self._edit.text())
        if d:
            self._edit.setText(d)

    def _accept(self):
        if self.chosen_path():
            self.accept()


def run_first_run_if_needed() -> None:
    """If this is a genuine first launch, prompt for a data folder and persist it.
    Falls back to the default when the user cancels/closes. Idempotent afterwards:
    the saved preference means `is_first_run()` is False next time. Always leaves a
    bootstrapped store behind (callers need not also call `ensure_data_root`)."""
    if not config.is_first_run():
        config.ensure_data_root()
        return
    dlg = FirstRunDialog()
    chosen = dlg.chosen_path() if dlg.exec() == QDialog.DialogCode.Accepted else ""
    path = Path(chosen).expanduser() if chosen else config.DEFAULT_DATA_ROOT
    config.save_data_root(path)          # persist → no re-prompt next launch
    config.set_data_root(path)           # point the live config at the choice
    config.ensure_data_root(path)
