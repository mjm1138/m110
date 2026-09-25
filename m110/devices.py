"""Telescope identity, from the one header card every device writes: ``TELESCOP``.

Two questions, deliberately tiny:

* `folder_name` — the store-visible name a device's data files under
  (``Calibration/<device>/``): the ``TELESCOP`` string verbatim, trimmed. Real
  names, not normalized ones (a standing preference), and the same string a user
  sees in any FITS viewer. Callers that build paths from it must still pass it
  through `ingest._safe_segment` — the header is attacker-controlled exactly like
  ``OBJECT``.
* `preset_key` — which `planning_config.DEVICE_PRESETS` entry describes it, or
  None. Lookup is by loose substring so firmware spelling drift (``DWARF 3``,
  ``Dwarf3``, ``DWARF III``?) doesn't need a release to fix.

Known ``TELESCOP`` values: ``'DWARF 3'`` (Dwarf 3), ``'Draco'`` (Draco, 2026
pre-release), Seestar: a **per-unit** string like ``'S50_15e7e390'`` (BUGS.md),
so a Seestar folder name is per unit today — a device registry (ROADMAP 6d) is
the place to fold that.
"""
from __future__ import annotations

import re

UNKNOWN = "unknown"


def folder_name(telescop: str | None) -> str:
    """The device's store-visible name: trimmed ``TELESCOP``, or ``"unknown"``."""
    s = (telescop or "").strip()
    return s or UNKNOWN


# (regex over the lower-cased TELESCOP, preset key) — first match wins, so the
# more specific patterns come first.
_PRESET_RULES = (
    (r"draco", "draco"),
    (r"dwarf\s*mini", "dwarf_mini"),
    (r"dwarf\s*(3|iii)\b", "dwarf_3"),
    (r"\bs30\s*pro\b|s30_?pro", "seestar_s30_pro"),
    (r"\bs30\b|s30_", "seestar_s30"),
    (r"\bs50\b|s50_", "seestar_s50"),
)


def preset_key(telescop: str | None) -> str | None:
    """The `planning_config.DEVICE_PRESETS` key for a ``TELESCOP`` value, or None
    when the device is unknown to the presets."""
    low = (telescop or "").strip().lower()
    if not low:
        return None
    for pat, key in _PRESET_RULES:
        if re.search(pat, low):
            return key
    return None
