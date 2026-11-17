"""Typography — system font for chrome, a bundled serif for voice, a mono for data.

Three bundled/selected faces, each with one job (UI_ROADMAP → 1.0 redesign):

* **Newsreader** (OFL, bundled variable TTFs): object names, page and inspector
  titles, notes — the "astronomer's notebook" voice. Designations are set with
  **lining numerals** forced (`lnum`): Newsreader defaults to old-style figures,
  which make "M1" read as "Mı".
* **System UI font** for chrome, with **tabular numerals** (`tnum`) wherever numbers
  stack in a column, so columns line up without a monospace.
* **JetBrains Mono** (OFL, bundled) only for genuinely technical strings —
  filenames, FITS cards, logs, the journal editor.

Sizes follow the token scale (`tokens.TYPE_SCALE`, px).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

from .tokens import FONT_SIZE

_FONT_DIR = Path(__file__).resolve().parent / "fonts"
_MONO_FILE = _FONT_DIR / "JetBrainsMono-Regular.ttf"
SERIF_FILES = (_FONT_DIR / "Newsreader.ttf", _FONT_DIR / "Newsreader-Italic.ttf")
_mono_family: str | None = None
_serif_family: str | None = None


def _register(path: Path) -> str | None:
    if not path.is_file():
        return None
    fid = QFontDatabase.addApplicationFont(str(path))
    if fid < 0:
        return None
    fams = QFontDatabase.applicationFontFamilies(fid)
    return fams[0] if fams else None


def load_fonts() -> str | None:
    """Register the bundled faces with Qt. Idempotent; returns the mono family name
    (or None if the file is missing / registration failed). Requires a QApplication."""
    global _mono_family, _serif_family
    if _serif_family is None:
        fams = [f for f in (_register(p) for p in SERIF_FILES) if f]
        _serif_family = fams[0] if fams else ""
    if _mono_family is None:
        _mono_family = _register(_MONO_FILE)
    return _mono_family


def serif_family() -> str | None:
    """The bundled serif's family name, or None when it isn't available."""
    if _serif_family is None:
        load_fonts()
    return _serif_family or None


def _feature(font: QFont, tag: str, on: bool = True) -> None:
    """Set an OpenType feature where Qt supports it (≥ 6.7); a no-op otherwise."""
    try:
        font.setFeature(QFont.Tag(tag), 1 if on else 0)
    except (AttributeError, TypeError):
        pass


def mono_font(size: int | None = None) -> QFont:
    """A QFont for the bundled monospace (falls back to the system fixed font if the
    bundle is unavailable). For technical strings only — not for numbers."""
    fam = _mono_family or load_fonts()
    f = QFont(fam) if fam else QFontDatabase.systemFont(QFontDatabase.FixedFont)
    if size:
        f.setPointSize(size)
    return f


def serif_font(size: int = FONT_SIZE["section"], *, weight: QFont.Weight =
               QFont.Weight.Normal, italic: bool = False) -> QFont:
    """The display serif at a pixel `size` from the type scale, lining numerals on.
    Falls back to the system font (still lining/tabular) if the bundle is missing."""
    fam = serif_family()
    f = QFont(fam) if fam else QFont()
    f.setPixelSize(size)
    f.setWeight(weight)
    f.setItalic(italic)
    _feature(f, "lnum")
    _feature(f, "onum", False)
    return f


def tabular(font: QFont | None = None) -> QFont:
    """`font` (default: the application font) with tabular, lining figures — for
    every cell that stacks numbers in a column."""
    f = QFont(font) if font is not None else QFont()
    _feature(f, "tnum")
    _feature(f, "lnum")
    return f


def section_font() -> QFont:
    """Tracked small capitals for panel section labels (Lightroom's "DETAILS")."""
    f = QFont()
    f.setPixelSize(FONT_SIZE["caption"])
    f.setWeight(QFont.Weight.DemiBold)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
    return f
