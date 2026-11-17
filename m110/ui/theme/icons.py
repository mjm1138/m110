"""Lucide icons, recolored from the active tokens.

The bundled SVGs (`icons/lucide/*.svg`, ISC — see `icons/lucide/LICENSE.txt`) are
Lucide's own files, untouched: each strokes in `currentColor`, which we replace with
a token hex before rasterizing. Only the icons the app uses are bundled; add one by
copying its SVG from the same Lucide release.

`icon(name)` returns a QIcon with Normal / Disabled / Selected / Active pixmaps at 1×
and 2×, so a QToolButton or list item recolors itself on state with no extra code.
Results are cached per (name, theme, role, size); a theme switch simply misses the
cache, so call sites re-request their icons from `restyle()`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import tokens

LUCIDE_DIR = Path(__file__).resolve().parent / "icons" / "lucide"
DEFAULT_SIZE = 16


def available() -> list[str]:
    return sorted(p.stem for p in LUCIDE_DIR.glob("*.svg"))


@lru_cache(maxsize=None)
def _svg(name: str) -> str:
    path = LUCIDE_DIR / f"{name}.svg"
    if not path.is_file():
        raise KeyError(f"no bundled Lucide icon {name!r} (have: {', '.join(available())})")
    return path.read_text(encoding="utf-8")


def pixmap(name: str, color: str, size: int = DEFAULT_SIZE, dpr: float = 2.0) -> QPixmap:
    """`name` rasterized in `color` (#rrggbb) at `size` logical px."""
    data = QByteArray(_svg(name).replace("currentColor", color).encode())
    renderer = QSvgRenderer(data)
    px = max(1, round(size * dpr))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


@lru_cache(maxsize=512)
def _icon(name: str, theme_name: str, role: str, selected_role: str, size: int) -> QIcon:
    t = tokens.ALL_THEMES[theme_name]
    ic = QIcon()
    for dpr in (1.0, 2.0):
        ic.addPixmap(pixmap(name, getattr(t, role), size, dpr), QIcon.Mode.Normal)
        ic.addPixmap(pixmap(name, t.text_disabled, size, dpr), QIcon.Mode.Disabled)
        ic.addPixmap(pixmap(name, getattr(t, selected_role), size, dpr),
                     QIcon.Mode.Selected)
        ic.addPixmap(pixmap(name, getattr(t, selected_role), size, dpr),
                     QIcon.Mode.Active)
    return ic


def icon(name: str, role: str = "text_secondary", *, selected_role: str = "text_primary",
         size: int = DEFAULT_SIZE, theme: tokens.Tokens | None = None) -> QIcon:
    """A Lucide icon in the active theme. `role` colors the normal state (muted by
    default, like a macOS sidebar glyph); `selected_role` the selected/active state."""
    t = theme or tokens.active()
    return _icon(name, t.name, role, selected_role, size)
