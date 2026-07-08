"""Brand assets — the M110 logo + app icon, theme-aware.

The logo (`brand/m110-logo.svg`) is a **monochrome black-ink** hand-drawn "M110"
wordmark on a transparent background (an astronomer's-notebook scrawl). Because the
app follows the OS light/dark appearance, a fixed-black logo would vanish in dark mode
— so the ink is **recolored to a caller-supplied color** at render time (call sites
pass the active theme's text color).

Dropping in a **replacement SVG** needs no code changes as long as it stays *black ink
(#000 / #000000) on transparent*: the recolor matches any near-black `fill` (style or
attribute form) and the crop is by transparent-pixel bounds, so it doesn't depend on a
specific element id. Weight is added by **alpha-dilating** the rendered ink
(`LOGO_STROKE_WIDTH`) so thin lines still read when scaled down — Qt's SVG renderer
silently ignores strokes on this path, so a real SVG stroke won't work. (Re-run
`tools/gen_app_icon.py` to refresh the exported `app-icon.png`.)

The app/dock icon composes the ink on a **fixed parchment tile** — app icons don't theme.
"""
from __future__ import annotations

import re
from pathlib import Path

import math

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtSvg import QSvgRenderer

_BRAND_DIR = Path(__file__).resolve().parent / "brand"
_LOGO_SVG = _BRAND_DIR / "m110-logo.svg"
# Finished full-bleed app-icon artwork: the wordmark over a light equatorial grid
# (with an easter-egg marker at M110's sky position). Used ONLY for the app/dock
# icon tile — the nav-rail / About wordmark stays on the plain `_LOGO_SVG`. Unlike
# the wordmark, this is rendered as-is (no dilation/crop); see `_icon_pixmap`.
_ICON_SVG = _BRAND_DIR / "m110-logo-grid.svg"
_PATH_ID = "path1"          # fast-path crop id for the bundled logo (optional)

# ── tunable ───────────────────────────────────────────────────────────────────
# Extra weight added to the filled glyph so hairline ink stays legible when the
# wordmark is scaled down (nav rail ~26px). It's an **alpha dilation** of the rendered
# ink (in the SVG's viewBox units — the logo's viewBox is 210 tall), NOT an SVG stroke:
# Qt's SVG renderer silently ignores strokes on this complex path, so dilation is the
# reliable knob. Bump it up for a heavier mark; set it to 0 to disable entirely (e.g.
# once a replacement SVG bakes in more weight).
LOGO_STROKE_WIDTH = 1

# Supersample factor: render bigger, dilate + downscale — gives sub-pixel dilation and
# smoother edges on the thin ink at small sizes.
_SUPERSAMPLE = 3

# App-icon logo sizing (fractions of the parchment tile). The wordmark is wide, so it's
# sized by **width** to fill the tile; `ICON_LOGO_MAX_HEIGHT` caps it so a taller logo
# can't overflow vertically.
ICON_LOGO_WIDTH = 0.88
ICON_LOGO_MAX_HEIGHT = 0.72

# Parchment tile palette for the app icon (fixed — icons don't follow the theme).
_PARCHMENT_TOP = QColor("#f1e8d2")
_PARCHMENT_BOT = QColor("#e2d4b6")
_ICON_INK = QColor("#2b2118")     # deep sepia ink (wordmark) on the tile
_ICON_GRID_INK = "#c2c2c2"        # equatorial grid + easter-egg marker (light grey)

# Recolor targets: near-black fills in `style="fill:..."` and `fill="..."` forms.
_FILL_STYLE_RE = re.compile(r"fill:\s*(?:#0{3}|#0{6}|black)\b", re.IGNORECASE)
_FILL_ATTR_RE = re.compile(r'fill=(["\'])\s*(?:#0{3}|#0{6}|black)\s*\1', re.IGNORECASE)

_svg_text: str | None = None
_logo_cache: dict[tuple[int, int], QPixmap] = {}   # (px_height, rgba) -> pixmap
_icon_svg_cache: bytes | None = None               # recolored app-icon artwork


def _load_svg() -> str:
    global _svg_text
    if _svg_text is None:
        _svg_text = _LOGO_SVG.read_text(encoding="utf-8")
    return _svg_text


def _renderer(color: QColor) -> QSvgRenderer:
    """A QSvgRenderer for the logo, ink recolored to `color` (fill only; weight is
    applied later by dilation — QtSvg won't stroke this path)."""
    c = color.name()
    svg = _FILL_STYLE_RE.sub(f"fill:{c}", _load_svg())
    svg = _FILL_ATTR_RE.sub(f'fill="{c}"', svg)
    return QSvgRenderer(svg.encode("utf-8"))


def _alpha_bounds(img: QImage, threshold: int = 8) -> QRect:
    """Bounding box of the non-transparent pixels (id-independent crop)."""
    w, h = img.width(), img.height()
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if (img.pixel(x, y) >> 24) & 0xFF > threshold:
                minx, maxx = min(minx, x), max(maxx, x)
                miny, maxy = min(miny, y), max(maxy, y)
    if maxx < 0:
        return QRect(0, 0, w, h)
    return QRect(minx, miny, maxx - minx + 1, maxy - miny + 1)


def _dilate(src: QImage, grow_px: float) -> QImage:
    """Grow the ink outward by ~`grow_px` — stamp the glyph around two concentric rings
    (+ center). A reliable, renderer-independent 'bolder' that thickens any logo."""
    if grow_px <= 0.4:
        return src
    steps = max(12, int(math.ceil(grow_px)) * 8)
    out = QImage(src.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    for radius in (grow_px, grow_px * 0.5):        # two rings avoid an interior gap
        for i in range(steps):
            ang = 2 * math.pi * i / steps
            p.drawImage(QPointF(math.cos(ang) * radius, math.sin(ang) * radius), src)
    p.drawImage(0, 0, src)                          # solid center on top
    p.end()
    return out


def _render_cropped(r: QSvgRenderer, px_h: int) -> QPixmap:
    """Render the ink recolored, weight-dilated, and tight-cropped to `px_h` px tall.
    Renders the whole viewBox supersampled (its natural margin gives the dilation room),
    dilates, crops to the ink (bundled path bounds fast-path, else transparent-pixel
    autocrop so a replacement SVG with any ids still works), then scales down."""
    vb = r.viewBoxF()
    bounds = r.boundsOnElement(_PATH_ID)
    if not bounds.isEmpty():
        pad = bounds.height() * 0.06
        bounds.adjust(-pad, -pad, pad, pad)
        scale = (px_h * _SUPERSAMPLE) / bounds.height()    # px per viewBox unit
    else:
        scale = (px_h * _SUPERSAMPLE) / vb.height()
    rw, rh = max(1, round(vb.width() * scale)), max(1, round(vb.height() * scale))
    img = QImage(rw, rh, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, rw, rh))
    p.end()

    img = _dilate(img, LOGO_STROKE_WIDTH * scale)
    if not bounds.isEmpty():
        crop = QRect(round(bounds.x() * scale), round(bounds.y() * scale),
                     round(bounds.width() * scale), round(bounds.height() * scale))
        img = img.copy(crop.intersected(img.rect()))
    else:
        img = img.copy(_alpha_bounds(img))
    img = img.scaledToHeight(px_h, Qt.TransformationMode.SmoothTransformation)
    return QPixmap.fromImage(img)


def logo_pixmap(height: int, color: QColor, dpr: float = 1.0) -> QPixmap:
    """The wordmark recolored to `color`, tight-cropped to the ink, `height` logical px
    tall (width follows the ink's aspect). Crisp on HiDPI when `dpr` is passed. Cached
    by (pixel height, color)."""
    px_h = max(1, int(round(height * dpr)))
    key = (px_h, int(color.rgba()))
    pm = _logo_cache.get(key)
    if pm is None:
        pm = _render_cropped(_renderer(color), px_h)
        _logo_cache[key] = pm
    pm = QPixmap(pm)          # shallow copy so per-caller dpr doesn't mutate the cache
    pm.setDevicePixelRatio(dpr)
    return pm


def logo_icon(height: int, color: QColor) -> QIcon:
    return QIcon(logo_pixmap(height, color))


def _icon_svg_bytes() -> bytes:
    """The app-icon artwork recolored for the parchment tile (cached): near-black
    wordmark fill+stroke → sepia ink; the light grid strokes (`#dcdcdc`) and the
    easter-egg marker fill (`#f2f2f2`) → the grid grey. Rendered as-is (this is a
    finished composition, not the adaptive wordmark), so no dilation/crop."""
    global _icon_svg_cache
    if _icon_svg_cache is None:
        svg = _ICON_SVG.read_text(encoding="utf-8")
        ink = _ICON_INK.name()
        svg = re.sub(r"fill:\s*#0{6}", f"fill:{ink}", svg, flags=re.IGNORECASE)
        svg = re.sub(r"stroke:\s*#0{6}", f"stroke:{ink}", svg, flags=re.IGNORECASE)
        svg = re.sub(r"stroke:\s*#dcdcdc", f"stroke:{_ICON_GRID_INK}", svg, flags=re.IGNORECASE)
        svg = re.sub(r"fill:\s*#f2f2f2", f"fill:{_ICON_GRID_INK}", svg, flags=re.IGNORECASE)
        _icon_svg_cache = svg.encode("utf-8")
    return _icon_svg_cache


def _icon_pixmap(size: int) -> QPixmap:
    """One square app-icon pixmap: the finished icon artwork on a rounded parchment
    tile, inset with a transparent margin so it matches the visual weight of other
    dock icons. Uses `_ICON_SVG` (full-bleed grid + wordmark) as finished art —
    rendered whole and clipped to the squircle — falling back to the composed plain
    wordmark if that file is absent."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Inset tile (~80% of the canvas — the macOS icon grid leaves breathing room).
    margin = size * 0.10
    tile = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    grad = QLinearGradient(tile.topLeft(), tile.bottomLeft())
    grad.setColorAt(0.0, _PARCHMENT_TOP)
    grad.setColorAt(1.0, _PARCHMENT_BOT)
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    radius = tile.width() * 0.2237                 # macOS squircle-ish corner
    p.drawRoundedRect(tile, radius, radius)
    if _ICON_SVG.exists():
        # Finished art: render the whole viewBox into the tile, clipped to the
        # squircle so the full-bleed grid respects the rounded corners.
        clip = QPainterPath()
        clip.addRoundedRect(tile, radius, radius)
        p.setClipPath(clip)
        QSvgRenderer(_icon_svg_bytes()).render(p, tile)
    else:
        # Legacy fallback: the plain wordmark sized by width to fill the tile.
        aspect = logo_pixmap(100, _ICON_INK).width() / 100.0
        target_h = (tile.width() * ICON_LOGO_WIDTH) / aspect
        target_h = min(target_h, tile.height() * ICON_LOGO_MAX_HEIGHT)
        logo = logo_pixmap(max(1, int(round(target_h))), _ICON_INK)
        p.drawPixmap(int(tile.center().x() - logo.width() / 2),
                     int(tile.center().y() - logo.height() / 2), logo)
    p.end()
    return pm


def app_icon() -> QIcon:
    """The application / dock / window icon — the ink logo on a parchment tile, at the
    standard icon sizes. Theme-independent by design."""
    icon = QIcon()
    for s in (16, 32, 64, 128, 256, 512):
        icon.addPixmap(_icon_pixmap(s))
    return icon
