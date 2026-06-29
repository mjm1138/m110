"""Typography — keep the system UI font for chrome, bundle one monospace for data.

The bundled mono (JetBrains Mono, OFL) gives aligned, legible technical values
(RA/Dec, integration, filenames, FITS metadata) consistently across platforms.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

_FONT_DIR = Path(__file__).resolve().parent / "fonts"
_MONO_FILE = _FONT_DIR / "JetBrainsMono-Regular.ttf"
_mono_family: str | None = None


def load_fonts() -> str | None:
    """Register the bundled monospace with Qt. Idempotent; returns the family name
    (or None if the file is missing / registration failed). Requires a QApplication."""
    global _mono_family
    if _mono_family is not None:
        return _mono_family
    if not _MONO_FILE.is_file():
        return None
    fid = QFontDatabase.addApplicationFont(str(_MONO_FILE))
    if fid < 0:
        return None
    fams = QFontDatabase.applicationFontFamilies(fid)
    _mono_family = fams[0] if fams else None
    return _mono_family


def mono_font(size: int | None = None) -> QFont:
    """A QFont for the bundled monospace (falls back to the system fixed font if the
    bundle is unavailable). Used for technical/data cells + the journal editor."""
    fam = _mono_family or load_fonts()
    f = QFont(fam) if fam else QFontDatabase.systemFont(QFontDatabase.FixedFont)
    if size:
        f.setPointSize(size)
    return f
