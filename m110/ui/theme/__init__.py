"""Theme façade — the design-system entry point for `m110/ui/`.

`install(app)` once at startup; everything else reads the active palette through
the convenience helpers here (so call sites never hardcode color/spacing). Lives
under `m110/ui/` only — the engine stays Qt-free.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont

from .fonts import mono_font
from .brand import app_icon, logo_icon, logo_pixmap
from .manager import MODES, SETTING_KEY, ThemeManager, resolve, system_scheme
from .qss import build_qss
from . import tokens
from .tokens import DARK, LIGHT, Tokens, active

__all__ = [
    "install", "manager", "set_mode", "active_tokens", "mono_font",
    "status_color", "muted_color", "ink_color", "Tokens", "LIGHT", "DARK", "MODES",
    "SETTING_KEY", "build_qss", "resolve", "system_scheme",
    "app_icon", "logo_icon", "logo_pixmap",
]

_MANAGER: ThemeManager | None = None


def install(app) -> ThemeManager:
    """Create + apply the theme manager for `app` (reads the saved `ui_theme`,
    default 'system'). Stores a singleton; safe to call once at startup."""
    global _MANAGER
    _MANAGER = ThemeManager(app)
    return _MANAGER


def manager() -> ThemeManager | None:
    return _MANAGER


def set_mode(mode: str) -> None:
    if _MANAGER is not None:
        _MANAGER.set_mode(mode)


def active_tokens() -> Tokens:
    return active()


def status_color(status: str | None) -> QColor:
    """Theme color for a capture status ('deep_stack'/'initial'); muted otherwise."""
    t = active()
    return QColor({"deep_stack": t.status_deep,
                   "initial": t.status_initial}.get(status, t.text_secondary))


def muted_color() -> QColor:
    return QColor(active().text_secondary)


def ink_color() -> QColor:
    """The active theme's primary text color — the logo's ink."""
    return QColor(active().text_primary)
