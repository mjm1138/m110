"""Update-availability UI over :mod:`m110.updates`.

A background :class:`UpdateCheckWorker` (launch check, throttled by
``updates.should_check``) and a quiet, dismissible :class:`UpdateBanner`
("M110 vX is available — Download · Skip · ✕"). The same worker backs Help →
"Check for updates…", whose result is shown by :func:`show_manual_result`.

Kept out of ``main.py`` so the window just owns a slot; low-chrome per the
minimal-main-window rule (a banner, never a launch modal).
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)

from m110 import updates
from m110.ui import theme


class UpdateCheckWorker(QThread):
    """Fetch + compare the newest release off the UI thread.

    Emits an ``updates.UpdateInfo`` (or ``None`` on failure). ``record=True``
    stamps ``last_update_check`` so the throttle advances; the manual check passes
    ``record=False`` so an explicit check never suppresses the next launch check."""
    done = Signal(object)  # updates.UpdateInfo | None

    def __init__(self, parent=None, *, record: bool = True):
        super().__init__(parent)
        self._record = record

    def run(self):
        info = None
        try:
            info = updates.check()
        except Exception:
            info = None
        if self._record:
            try:
                updates.record_check()
            except Exception:
                pass
        self.done.emit(info)


class UpdateBanner(QFrame):
    """A quiet strip shown at the top of the content area when a newer release
    exists: message + Download + Skip-this-version + close."""

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self._info = info
        self.setObjectName("updateBanner")
        t = theme.active_tokens()
        s = theme.tokens.SPACE
        r = theme.tokens.RADIUS["md"]
        self.setStyleSheet(
            f"#updateBanner {{ background:{t.surface_alt}; "
            f"border:1px solid {t.border}; border-radius:{r}px; }}")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(s["md"], s["sm"], s["sm"], s["sm"])
        lay.setSpacing(s["sm"])

        msg = QLabel(f"M110 {info.latest} is available — you're on {info.current}.")
        lay.addWidget(msg)
        lay.addStretch(1)

        dl = QPushButton("Download")
        dl.setDefault(True)
        dl.clicked.connect(self._download)
        skip = QPushButton("Skip this version")
        skip.clicked.connect(self._skip)
        close = QPushButton("✕")
        close.setFlat(True)
        close.setFixedWidth(28)
        close.setToolTip("Dismiss (shows again next launch)")
        close.clicked.connect(self.hide)
        for b in (dl, skip, close):
            lay.addWidget(b)

    def _download(self):
        QDesktopServices.openUrl(QUrl(self._info.url))

    def _skip(self):
        try:
            updates.skip_version(self._info.latest)
        finally:
            self.hide()


def show_manual_result(parent, info) -> None:
    """Show the outcome of a manual Help → Check for updates."""
    if info is None:
        QMessageBox.information(
            parent, "Check for updates",
            "Couldn't check for updates right now. Please try again later.")
        return
    if info.is_newer:
        box = QMessageBox(parent)
        box.setWindowTitle("Update available")
        box.setText(f"M110 {info.latest} is available.")
        box.setInformativeText(f"You're on {info.current}.")
        dl = box.addButton("Download", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is dl:
            QDesktopServices.openUrl(QUrl(info.url))
    else:
        QMessageBox.information(
            parent, "Check for updates",
            f"You're up to date (M110 {info.current}).")
