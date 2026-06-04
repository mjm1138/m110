"""Standardized display-name generation for image files.

Used by build_site.py (gallery + hero + lightbox) and build_derived.py
(processing-page "latest stack" column) to ensure the same source file is
shown under the same name everywhere.

Display-name format:
    [ObjectName]_stacked_[YYYYMMDD].fit    (FITS files)
    [ObjectName]_processed_[YYYYMMDD].ext  (jpg / png / tif / tiff)

ObjectName rules:
  - apostrophes stripped:        "Markarian's" → "Markarians"
  - parenthetical qualifiers folded in as words:
                                 "Veil Nebula (E)" → "Veil Nebula E"
  - "mosaic" keyword pulled off as "_mosaic" suffix
  - multi-object folders (≥2 slugs): remaining tokens joined with "_"
                                 "M81 M82" → "M81_M82"
  - single-object folders: tokens concatenated, no separator
                                 "NGC 2903" → "NGC2903"

Date source:
  - Embedded YYYYMMDD-HHMMSS pattern in the source filename (Seestar native)
  - File mtime otherwise
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

_FILENAME_DATE_RE = re.compile(r"(\d{8})-\d{6}")


def _filename_object_name(folder: str, n_slugs: int) -> str:
    """Convert a folder name into the standardized object-name component."""
    name = folder.replace("'", "")
    # Fold parentheticals into the name as words
    name = re.sub(r"\s*\(([^)]+)\)\s*", r" \1 ", name).strip()
    # Tokenize on whitespace and underscores
    tokens = [t for t in re.split(r"[\s_]+", name) if t]
    # Pull off trailing "mosaic" keyword
    has_mosaic = False
    if tokens and tokens[-1].lower() == "mosaic":
        has_mosaic = True
        tokens.pop()
    if n_slugs >= 2:
        body = "_".join(tokens)
    else:
        body = "".join(tokens)
    return body + ("_mosaic" if has_mosaic else "")


def _filename_date_from_path(path: Path) -> str:
    """Extract YYYYMMDD from filename, otherwise file mtime."""
    m = _FILENAME_DATE_RE.search(path.name)
    if m:
        return m.group(1)
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d")


def _filename_date_from_name_and_mtime(name: str, mtime: float) -> str:
    """Extract YYYYMMDD from a filename + mtime pair (no Path needed)."""
    m = _FILENAME_DATE_RE.search(name)
    if m:
        return m.group(1)
    return datetime.fromtimestamp(mtime).strftime("%Y%m%d")


def _status_for_ext(ext: str) -> str:
    """FITS files are 'stacked'; viewable formats are 'processed'."""
    return "stacked" if ext.lower() in (".fit", ".fits") else "processed"


def display_name_for_image(path: Path, folder: str, n_slugs: int) -> str:
    """Return the standardized display name for an image file (Path input)."""
    obj = _filename_object_name(folder, n_slugs)
    date = _filename_date_from_path(path)
    ext = path.suffix.lower()
    return f"{obj}_{_status_for_ext(ext)}_{date}{ext}"


def display_name_for_name(name: str, mtime: float,
                          folder: str, n_slugs: int) -> str:
    """Same as display_name_for_image, but takes name + mtime instead of Path.

    Useful when only filename/mtime metadata is available (e.g., from a
    pre-built listing in build_derived.py).
    """
    obj = _filename_object_name(folder, n_slugs)
    date = _filename_date_from_name_and_mtime(name, mtime)
    ext = Path(name).suffix.lower()
    return f"{obj}_{_status_for_ext(ext)}_{date}{ext}"
