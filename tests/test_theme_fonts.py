"""Bundled monospace loads and is returned by mono_font()."""
import pytest

from m110.ui.theme import fonts


def test_mono_font_loads(qapp):
    fam = fonts.load_fonts()
    if fam is None:
        pytest.skip("bundled mono font not present")
    assert fam  # a real family name (e.g. "JetBrains Mono")
    f = fonts.mono_font(13)
    assert f.family() == fam
    assert f.pointSize() == 13


def test_mono_font_idempotent(qapp):
    assert fonts.load_fonts() == fonts.load_fonts()
