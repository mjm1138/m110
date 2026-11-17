"""Lucide icons: bundled, licensed, recolored from tokens, state-aware."""
import re

import pytest

from m110.ui.theme import icons, tokens


def test_lucide_license_and_icons_ship_with_the_package():
    assert (icons.LUCIDE_DIR / "LICENSE.txt").is_file()
    names = icons.available()
    for n in ("house", "layout-grid", "film", "book-open", "download", "layers",
              "moon", "telescope", "search", "info", "image-down",
              "chevron-left", "chevron-right", "panel-left"):
        assert n in names, n


def test_every_bundled_svg_strokes_in_current_color():
    """Recoloring works by replacing currentColor — an SVG with a baked-in color
    would silently ignore the theme."""
    for p in icons.LUCIDE_DIR.glob("*.svg"):
        text = p.read_text()
        assert "currentColor" in text, p.name
        assert not re.search(r'(stroke|fill)="#', text), p.name


def test_pixmap_is_recolored_from_the_token(qapp):
    from PySide6.QtGui import QColor
    pm = icons.pixmap("plus", "#d9a648", 16, 2.0)
    img = pm.toImage()
    assert img.width() == 32 and pm.devicePixelRatio() == 2.0
    seen = {QColor(img.pixel(x, y)).name() for x in range(32) for y in range(32)
            if QColor.fromRgba(img.pixel(x, y)).alpha() > 250}
    assert seen == {"#d9a648"}


def test_icon_has_state_pixmaps_and_follows_the_theme(qapp):
    from PySide6.QtGui import QIcon
    tokens.set_active(tokens.DARK)
    dark = icons.icon("house")
    assert not dark.isNull()
    assert not dark.pixmap(16, QIcon.Mode.Disabled).isNull()
    tokens.set_active(tokens.LIGHT)
    light = icons.icon("house")
    assert light.cacheKey() != dark.cacheKey()


def test_unknown_icon_names_fail_loudly():
    with pytest.raises(KeyError):
        icons.pixmap("no-such-icon", "#ffffff")


def test_no_unicode_stand_ins_remain_in_the_viewer():
    """The critique's "⤓ Export…", "ⓘ Info", "‹ Prev" — replaced by Lucide icons."""
    from pathlib import Path
    src = (Path(icons.__file__).parents[1] / "image_viewer.py").read_text()
    for glyph in ("⤓", "ⓘ", "‹", "›"):
        assert glyph not in src
