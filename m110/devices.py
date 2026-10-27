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
import tomllib

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


# ── the registry: what the user has said about each telescope ──────────────────
# Devices are DISCOVERED (every TELESCOP a session names, every Calibration/<dev>/
# folder); `.m110_internal_data/devices.toml` holds only the user's edits, keyed
# by the device key (`folder_name`):
#
#   [devices."S50_15e7e390"]
#   nickname = "Backyard S50"
#   retired = false
#   preset = "seestar_s50"      # only when TELESCOP is not recognised
#
#   [devices."MyScope".optics]  # only for a telescope with no preset
#   aperture_mm = 61.0
#   focal_length_mm = 275.0
#   pixel_um = 3.76
#
# Additive and lazily created (absence = no edits) → no .store_version bump.
# A malformed file reads as empty rather than failing a refresh.

REGISTRY_FIELDS = ("nickname", "retired", "preset")
# Nested tables of numbers: the planning-limit overrides, and the optics of a
# telescope no preset describes.
_SUBTABLES = ("planning", "optics")
OPTICS_FIELDS = ("aperture_mm", "focal_length_mm", "pixel_um")


def load_registry() -> dict[str, dict]:
    """``{device key: {nickname?, retired?, preset?, planning?, optics?}}`` — the
    user's edits."""
    from . import config
    path = config.DEVICES_TOML
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    devs = data.get("devices", {})
    if not isinstance(devs, dict):
        return {}
    out: dict[str, dict] = {}
    for key, entry in devs.items():
        if not isinstance(entry, dict):
            continue
        clean = {}
        if isinstance(entry.get("nickname"), str) and entry["nickname"].strip():
            clean["nickname"] = entry["nickname"].strip()
        if isinstance(entry.get("retired"), bool):
            clean["retired"] = entry["retired"]
        if isinstance(entry.get("preset"), str) and entry["preset"].strip():
            clean["preset"] = entry["preset"].strip()
        if isinstance(entry.get("planning"), dict):
            clean["planning"] = {k: v for k, v in entry["planning"].items()
                                 if isinstance(v, (int, float, bool))}
        if isinstance(entry.get("optics"), dict):
            optics = {k: float(v) for k, v in entry["optics"].items()
                      if k in OPTICS_FIELDS and isinstance(v, (int, float))
                      and not isinstance(v, bool) and v > 0}
            if optics:
                clean["optics"] = optics
        out[str(key)] = clean
    return out


def save_device(key: str, **fields) -> dict:
    """Merge `fields` into `key`'s entry (a value of None or "" clears that field)
    and rewrite the file, keeping every other device. Returns the new entry."""
    reg = load_registry()
    entry = dict(reg.get(key, {}))
    for name, value in fields.items():
        if name not in REGISTRY_FIELDS + _SUBTABLES:
            raise ValueError(f"unknown device field {name!r}")
        if value is None or value == "" or value == {} or value is False and name == "retired":
            entry.pop(name, None)
        else:
            entry[name] = value
    if entry:
        reg[key] = entry
    else:
        reg.pop(key, None)
    _write_registry(reg)
    return entry


def effective_preset(key: str | None, registry: dict | None = None) -> str | None:
    """The preset that describes `key`: the user's choice, else the TELESCOP rule."""
    reg = load_registry() if registry is None else registry
    return (reg.get(key or "", {}).get("preset")) or preset_key(key)


def model_name(key: str | None, registry: dict | None = None) -> str | None:
    """The preset's model name ("ZWO Seestar S50"), or None for an unknown device."""
    preset = effective_preset(key, registry)
    if not preset:
        return None
    from .planning_config import DEVICE_PRESETS
    dev = DEVICE_PRESETS.get(preset)
    return dev.name if dev else None


def serial(key: str | None) -> str | None:
    """The unit serial a per-unit TELESCOP carries (``S50_15e7e390`` → ``15e7e390``)."""
    head, sep, tail = (key or "").strip().partition("_")
    return tail if sep and tail else None


def label(key: str | None, registry: dict | None = None) -> str:
    """What the UI calls the device: the user's nickname, else `display_name`."""
    if not key or key == UNKNOWN:
        return "Unknown telescope"
    reg = load_registry() if registry is None else registry
    nick = reg.get(key, {}).get("nickname")
    if nick:
        return nick
    model = model_name(key, reg)
    if model and preset_key(key) is None:          # user-chosen preset, raw TELESCOP
        return f"{model} · {key}"
    return display_name(key)


def _q(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return _q(v)


def _write_registry(reg: dict[str, dict]) -> None:
    from . import config
    lines = ["# What you've told M110 about each telescope (Devices page).",
             "# Keyed by the FITS TELESCOP value; devices themselves are discovered.", ""]
    for key in sorted(reg):
        entry = reg[key]
        lines.append(f"[devices.{_q(key)}]")
        for name in REGISTRY_FIELDS:
            if name in entry:
                lines.append(f"{name} = {_toml_value(entry[name])}")
        for sub in _SUBTABLES:
            if entry.get(sub):
                lines += ["", f"[devices.{_q(key)}.{sub}]"]
                for k in sorted(entry[sub]):
                    lines.append(f"{k} = {_toml_value(entry[sub][k])}")
        lines.append("")
    config.DEVICES_TOML.parent.mkdir(parents=True, exist_ok=True)
    config.DEVICES_TOML.write_text("\n".join(lines), encoding="utf-8")
