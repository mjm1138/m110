"""Theme manager — resolve light/dark, apply the QSS, follow the system appearance.

`Mode` is the user's choice ("system" | "light" | "dark" | "night"); when it's
"system" we resolve the concrete scheme from `QStyleHints.colorScheme()` and (when Qt
exposes it) re-apply live on `colorSchemeChanged`. On older Qt (< 6.8, no signal) the
shell's focus-in re-check keeps "follow system" working via `refresh_system()`.

**Night** is only ever chosen explicitly (View › Night Vision, Settings ›
Appearance) — a system has no night appearance to follow. While it's on, the native
parts QSS can't reach (menus, scroll bars, file dialogs) are asked for the dark
appearance; they can't be tinted red, but dark is the least light they can give.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal

from m110 import config
from . import fonts, tokens
from .qss import build_qss

SETTING_KEY = "ui_theme"
MODES = ("system", "light", "dark", "night")
NIGHT_PREV_KEY = "ui_theme_before_night"    # what View › Night Vision returns to


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
    """Map a Mode to a concrete 'light'/'dark'/'night'."""
    if mode in ("dark", "light", "night"):
        return mode
    return system_scheme()


class ThemeManager(QObject):
    changed = Signal()        # theme (re)applied — consumers repaint programmatic colors

    def __init__(self, app):
        super().__init__(app)
        self._app = app
        self._forced_dark = False
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
        # Release (or take) the native scheme *before* resolving, so leaving night
        # for "system" reads the system's appearance, not the forced dark.
        self._force_native_dark(self._mode == "night")
        t = tokens.THEMES[resolve(self._mode)]
        tokens.set_active(t)
        self._app.setStyleSheet(build_qss(t))
        self.changed.emit()

    def _force_native_dark(self, on: bool) -> None:
        """Night forces the native (non-QSS) parts dark; otherwise they follow the
        system as before. `setColorScheme` is Qt ≥ 6.8; older Qt keeps the system's.
        Touched only on a change: setting it re-emits `colorSchemeChanged`, and an
        app that never went to night never overrides the system at all."""
        if on == self._forced_dark:
            return
        self._forced_dark = on
        hints = self._app.styleHints()
        if hasattr(hints, "setColorScheme"):
            hints.setColorScheme(Qt.ColorScheme.Dark if on else Qt.ColorScheme.Unknown)

    def set_mode(self, mode: str) -> None:
        """User picked a Mode in Settings — persist + apply live."""
        mode = mode if mode in MODES else "system"
        if mode == "night" and self._mode != "night":
            config.save_setting(NIGHT_PREV_KEY, self._mode)
        self._mode = mode
        config.save_setting(SETTING_KEY, self._mode)
        self.apply()

    @property
    def night(self) -> bool:
        return self._mode == "night"

    def set_night(self, on: bool) -> None:
        """View › Night Vision: on → night; off → whatever was chosen before it."""
        if on == self.night:
            return
        if on:
            self.set_mode("night")
        else:
            prev = config.get_setting(NIGHT_PREV_KEY, "system")
            self.set_mode(prev if prev in MODES and prev != "night" else "system")

    def refresh_system(self) -> None:
        """Re-apply if we're following the system and its scheme changed (called by
        the signal on new Qt, or by the shell on focus-in for the fallback)."""
        if self._mode == "system" and tokens.active().name != system_scheme():
            self.apply()
