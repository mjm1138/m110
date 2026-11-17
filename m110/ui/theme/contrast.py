"""Color math for the design tokens — WCAG contrast and CIE L*.

Pure Python (no Qt), so the palette checks in `tests/test_theme_contrast.py` run
anywhere and say *why* a color fails, in the same units the critique used.
"""
from __future__ import annotations


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    """WCAG relative luminance (0 black … 1 white) of `#rrggbb`."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def lightness(hex_color: str) -> float:
    """CIE L* (0 … 100) — perceptual lightness, for the surface-ladder spacing."""
    y = luminance(hex_color)
    return 116 * y ** (1 / 3) - 16 if y > 216 / 24389 else y * 24389 / 27


def ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two colors (1 … 21)."""
    a, b = sorted((luminance(fg), luminance(bg)))
    return (b + 0.05) / (a + 0.05)
