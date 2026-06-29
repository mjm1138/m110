"""Theme manager — resolve light/dark, apply the QSS, follow the system appearance.

`Mode` is the user's choice ("system" | "light" | "dark"); when it's "system" we
resolve the concrete scheme from `QStyleHints.colorScheme()` and (when Qt exposes it)
re-apply live on `colorSchemeChanged`. On older Qt (< 6.8, no signal) the shell's
focus-in re-check keeps "follow system" working via `refresh_system()`.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal

from m110 import config
from . import fonts, tokens
from .qss import build_qss

SETTING_KEY = "ui_theme"
MODES = ("system", "light", "dark")


def system_scheme() -> str:
    """The OS appearance as 'light'/'dark' (best-effort; defaults to light)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    try:
        if app is not None and app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            return "dark"
    except Exception:
        pass
    return "light"


def resolve(mode: str) -> str:
    """Map a Mode to a concrete 'light'/'dark'."""
    if mode == "dark":
        return "dark"
    if mode == "light":
        return "light"
    return system_scheme()


class ThemeManager(QObject):
    changed = Signal()        # theme (re)applied — consumers repaint programmatic colors

    def __init__(self, app):
        super().__init__(app)
        self._app = app
        self._mode = config.get_setting(SETTING_KEY, "system")
        if self._mode not in MODES:
            self._mode = "system"
        fonts.load_fonts()
        # Follow live OS appearance changes when Qt exposes the signal (≥ 6.8).
        hints = app.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self.refresh_system())
        self.apply()

    @property
    def mode(self) -> str:
        return self._mode

    def apply(self, mode: str | None = None) -> None:
        if mode is not None:
            self._mode = mode if mode in MODES else "system"
        t = tokens.THEMES[resolve(self._mode)]
        tokens.set_active(t)
        self._app.setStyleSheet(build_qss(t))
        self.changed.emit()

    def set_mode(self, mode: str) -> None:
        """User picked a Mode in Preferences — persist + apply live."""
        self._mode = mode if mode in MODES else "system"
        config.save_setting(SETTING_KEY, self._mode)
        self.apply()

    def refresh_system(self) -> None:
        """Re-apply if we're following the system and its scheme changed (called by
        the signal on new Qt, or by the shell on focus-in for the fallback)."""
        if self._mode == "system" and tokens.active().name != system_scheme():
            self.apply()
