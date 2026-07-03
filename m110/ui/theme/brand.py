"""Brand assets — the M110 logo + app icon, theme-aware.

The logo (`brand/m110-logo.svg`) is a single-color hand-inked "M110" wordmark (an
astronomer's-notebook scrawl). Because the app follows the OS light/dark appearance,
a fixed-black logo would vanish in dark mode — so it's **recolored to a caller-supplied
ink at render time** (call sites pass the active theme's text color). The app/dock icon
composes that ink on a **fixed parchment tile** — app icons don't theme.

All colors come from the caller / tokens; this module hardcodes only the parchment tile
palette (which is intentionally theme-independent).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_BRAND_DIR = Path(__file__).resolve().parent / "brand"
_LOGO_SVG = _BRAND_DIR / "m110-logo.svg"
_PATH_ID = "path1"          # id of the single ink path in the source SVG

# Parchment tile palette for the app icon (fixed — icons don't follow the theme).
_PARCHMENT_TOP = QColor("#f1e8d2")
_PARCHMENT_BOT = QColor("#e2d4b6")
_ICON_INK = QColor("#2b2118")     # deep sepia ink on the tile

_svg_text: str | None = None
_logo_cache: dict[tuple[int, int], QPixmap] = {}   # (px_height, rgba) -> pixmap


def _load_svg() -> str:
    global _svg_text
    if _svg_text is None:
        _svg_text = _LOGO_SVG.read_text(encoding="utf-8")
    return _svg_text


def _renderer(color: QColor) -> QSvgRenderer:
    """A QSvgRenderer for the logo with its ink recolored to `color`."""
    svg = _load_svg().replace("fill:#000000", f"fill:{color.name()}")
    return QSvgRenderer(svg.encode("utf-8"))


def logo_pixmap(height: int, color: QColor, dpr: float = 1.0) -> QPixmap:
    """The wordmark recolored to `color`, tight-cropped to the ink, `height` logical
    px tall (width follows the ink's aspect). Crisp on HiDPI when `dpr` is passed.
    Cached by (pixel height, color)."""
    px_h = max(1, int(round(height * dpr)))
    key = (px_h, int(color.rgba()))
    pm = _logo_cache.get(key)
    if pm is None:
        r = _renderer(color)
        bounds = r.boundsOnElement(_PATH_ID)      # tight ink rect, in viewBox units
        if bounds.isEmpty():
            bounds = QRectF(r.viewBoxF())
        pad = bounds.height() * 0.05               # a hair of breathing room
        bounds.adjust(-pad, -pad, pad, pad)
        aspect = bounds.width() / bounds.height() if bounds.height() else 1.0
        px_w = max(1, round(px_h * aspect))
        pm = QPixmap(px_w, px_h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.setViewBox(bounds)                       # map the ink rect onto the target → crop
        r.render(p, QRectF(0, 0, px_w, px_h))
        p.end()
        _logo_cache[key] = pm
    pm = QPixmap(pm)          # shallow copy so per-caller dpr doesn't mutate the cache entry
    pm.setDevicePixelRatio(dpr)
    return pm


def logo_icon(height: int, color: QColor) -> QIcon:
    return QIcon(logo_pixmap(height, color))


def _icon_pixmap(size: int) -> QPixmap:
    """One square app-icon pixmap: ink logo centered on a rounded parchment tile."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Rounded parchment tile with a subtle top→bottom aged gradient.
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, _PARCHMENT_TOP)
    grad.setColorAt(1.0, _PARCHMENT_BOT)
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    radius = size * 0.22
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    # Ink logo, fit within ~74% of the tile width.
    logo = logo_pixmap(int(size * 0.44), _ICON_INK)
    max_w = size * 0.74
    if logo.width() > max_w:
        logo = logo.scaledToWidth(int(max_w), Qt.TransformationMode.SmoothTransformation)
    p.drawPixmap(int((size - logo.width()) / 2), int((size - logo.height()) / 2), logo)
    p.end()
    return pm


def app_icon() -> QIcon:
    """The application / dock / window icon — the ink logo on a parchment tile, at the
    standard icon sizes. Theme-independent by design."""
    icon = QIcon()
    for s in (16, 32, 64, 128, 256, 512):
        icon.addPixmap(_icon_pixmap(s))
    return icon
