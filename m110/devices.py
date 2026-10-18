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

Known ``TELESCOP`` values: ``'DWARF 3'`` (Dwarf 3), Seestar: a **per-unit** string like ``'S50_15e7e390'`` (BUGS.md),
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
    (r"dwarf\s*mini", "dwarf_mini"),
    (r"dwarf\s*(3|iii)\b", "dwarf_3"),
    (r"\bs30\s*pro\b|s30_?pro", "seestar_s30_pro"),
    (r"\bs30\b|s30_", "seestar_s30"),
    (r"\bs50\b|s50_", "seestar_s50"),
)


# Devices whose saved subs are ALREADY dark-subtracted on the device. Measured on
# a Seestar S50 (2026-10-18): the hot pixels of its own master darks are absent
# from every raw `_sub` frame, before and after the firmware began keeping a dark
# library. The S30s run the same ZWO pipeline and are assumed to match. Applying
# a library dark to these subs again would double-subtract (DONE.md).
_DARKS_APPLIED_ON_DEVICE = frozenset({"seestar_s50", "seestar_s30", "seestar_s30_pro"})


def darks_applied_on_device(telescop: str | None) -> bool:
    """True when this telescope's subs come off the device already dark-subtracted,
    so a library dark is reference data, never something to apply again."""
    return preset_key(telescop) in _DARKS_APPLIED_ON_DEVICE


def display_name(telescop: str | None) -> str:
    """What a person calls the device: the preset's model name, plus the unit
    serial when ``TELESCOP`` carries one (``S50_15e7e390`` → ``ZWO Seestar S50 ·
    15e7e390``); the raw string when the device is unknown."""
    key = preset_key(telescop)
    if key is None:
        return folder_name(telescop)
    from .planning_config import DEVICE_PRESETS      # local: keeps this module tiny
    name = DEVICE_PRESETS[key].name
    head, sep, serial = (telescop or "").strip().partition("_")
    return f"{name} · {serial}" if sep and serial else name


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
