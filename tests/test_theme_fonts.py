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


# ---- 1.0 type: Newsreader, lining numerals, the scale, section labels ----

def test_newsreader_is_bundled_and_registers(qapp):
    """The serif ships in the package (roman + italic + its OFL), so a frozen build
    collects it via package-data; it registers as the 'Newsreader' family."""
    for p in fonts.SERIF_FILES:
        assert p.is_file(), p
    assert (fonts.SERIF_FILES[0].parent / "Newsreader-OFL.txt").is_file()
    fonts.load_fonts()
    assert fonts.serif_family() == "Newsreader"


def test_serif_font_forces_lining_numerals(qapp):
    """Newsreader defaults to old-style figures, which set "M1" as "Mı"."""
    from PySide6.QtGui import QFont
    f = fonts.serif_font(22, weight=QFont.Weight.DemiBold)
    assert f.family() == "Newsreader"
    assert f.pixelSize() == 22
    assert f.featureValue(QFont.Tag("lnum")) == 1
    assert f.featureValue(QFont.Tag("onum")) == 0


def test_section_font_is_tracked_caps_at_caption_size(qapp):
    from PySide6.QtGui import QFont
    f = fonts.section_font()
    assert f.capitalization() == QFont.Capitalization.AllUppercase
    assert f.letterSpacing() > 100
    assert f.pixelSize() == 11


def test_type_role_sizes_are_in_the_stylesheet():
    """A widget's setFont size loses to the blanket QWidget font-size rule, so the
    role sizes must be stated in the QSS."""
    from m110.ui.theme import tokens
    from m110.ui.theme.qss import build_qss
    qss = build_qss(tokens.DARK)
    for role, px in (("display", 30), ("title", 22), ("heading", 17)):
        assert f'*[type="{role}"] {{ font-size: {px}px; }}' in qss


def test_object_title_sets_designation_and_italic_name(qapp):
    from m110.ui.widgets import object_title
    lbl = object_title("M81", "Bode's Galaxy")
    assert lbl.property("type") == "title"
    assert "M81" in lbl.text() and "<i>Bode&#x27;s Galaxy</i>" in lbl.text()
    assert lbl.font().family() in ("Newsreader", "")
