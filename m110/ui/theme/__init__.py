"""Theme façade — the design-system entry point for `m110/ui/`.

`install(app)` once at startup; everything else reads the active palette through
the convenience helpers here (so call sites never hardcode color/spacing). Lives
under `m110/ui/` only — the engine stays Qt-free.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont

from .fonts import mono_font
from .brand import app_icon, logo_icon, logo_pixmap
from .manager import MODES, NIGHT_PREV_KEY, SETTING_KEY, ThemeManager, resolve, system_scheme
from .night import NIGHT_DIM, display_image, display_pixmap, is_night, night_image
from .qss import build_qss
from . import tokens
from .tokens import DARK, LIGHT, NIGHT, Tokens, active, on_well

__all__ = [
    "install", "manager", "set_mode", "active_tokens", "mono_font",
    "status_color", "muted_color", "ink_color", "Tokens", "LIGHT", "DARK", "NIGHT",
    "MODES", "on_well", "well_text_color", "well_muted_color",
    "SETTING_KEY", "build_qss", "resolve", "system_scheme",
    "app_icon", "logo_icon", "logo_pixmap",
    "NIGHT_PREV_KEY", "NIGHT_DIM", "display_image", "display_pixmap", "is_night",
    "night_image", "set_night",
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


def set_night(on: bool) -> None:
    if _MANAGER is not None:
        _MANAGER.set_night(on)


def active_tokens() -> Tokens:
    return active()


def status_color(status: str | None, *, well: bool = False) -> QColor:
    """Theme color for a capture status ('deep_stack'/'in_progress'/'initial');
    muted otherwise. `well=True` gives the hue for drawing on the image well, which
    is dark in every theme."""
    t = on_well() if well else active()
    return QColor({"deep_stack": t.status_deep,
                   "in_progress": t.status_progress,
                   "initial": t.status_initial}.get(status, t.text_secondary))


def muted_color() -> QColor:
    return QColor(active().text_secondary)


def well_text_color() -> QColor:
    return QColor(active().well_text)


def well_muted_color() -> QColor:
    return QColor(active().well_muted)


def ink_color() -> QColor:
    """The active theme's primary text color — the logo's ink."""
    return QColor(active().text_primary)
