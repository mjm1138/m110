"""Night vision for images (UI Phase 8 · F).

The night palette is red on black, but an astro image is the brightest thing on
screen, and a full-colour one undoes the point. So in night mode every image the app
draws goes through `night_image`: luminance mapped onto the red channel only, at
`NIGHT_DIM` of full brightness. Green and blue are zero, so nothing the screen shows
reaches beyond red.

Call sites never test the theme themselves: they pass what they're about to show
through `display_image` / `display_pixmap`, which is the identity outside night.
Decoded caches (e.g. `widgets.ThumbnailLoader`) keep the *original* image and filter
on the way out, so toggling night only needs a repaint from cache, not a re-decode.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap

from . import tokens

NIGHT_DIM = 0.5             # peak red, as a fraction of full brightness


def is_night() -> bool:
    return tokens.active().name == "night"


def night_image(img: QImage, dim: float = NIGHT_DIM) -> QImage:
    """`img` as red monochrome: R = luminance × `dim`, G = B = 0, alpha kept."""
    if img.isNull():
        return img
    src = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h, bpl = src.width(), src.height(), src.bytesPerLine()
    px = np.frombuffer(src.constBits(), np.uint8, count=bpl * h)
    px = px.reshape(h, bpl)[:, : w * 4].reshape(h, w, 4)      # B, G, R, A (little-endian)
    lum = (0.0722 * px[..., 0] + 0.7152 * px[..., 1] + 0.2126 * px[..., 2])
    out = np.zeros((h, w, 4), np.uint8)
    out[..., 2] = np.clip(lum * dim, 0, 255).astype(np.uint8)
    out[..., 3] = px[..., 3]
    res = QImage(out.data, w, h, w * 4, QImage.Format.Format_ARGB32).copy()
    res.setDevicePixelRatio(img.devicePixelRatio())
    return res


def display_image(img: QImage) -> QImage:
    """What to show for `img` in the current theme."""
    return night_image(img) if is_night() and not img.isNull() else img


def display_pixmap(src) -> QPixmap:
    """A QPixmap to show for `src` (QImage, QPixmap, or a path) in the current theme."""
    if isinstance(src, QPixmap):
        if not is_night() or src.isNull():
            return src
        return QPixmap.fromImage(night_image(src.toImage()))
    if not isinstance(src, QImage):
        src = QImage(str(src))
    return QPixmap.fromImage(display_image(src))
