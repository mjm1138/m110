"""Observing-site & device profiles for the session-planning engine.

A **site profile** is one shooting location — home backyard, a dark-site trip —
authored as ``<name>.toml`` under ``.m110_internal_data/profiles/``. It carries
the observer location (lat/lon/elevation/timezone), an optional physical
**horizon mask** (``.hrz``), and a light-pollution **glow** layer: a Bortle/SQM
scalar plus an azimuth-dependent glow floor (broadband + a softer narrowband
variant), which the planning module layers over the physical horizon as
``max(physical_obstruction, glow_floor)``. The glow fields default empty; the
*next* (light-dome) phase fills them in by looking up the location online.

A **device profile** carries the capture constraints (altitude ceiling/floor,
exposure bounds). Both fall back to in-code defaults so a fresh store plans
sensibly before any profile is authored.

UTC offsets are derived per-date from the site's IANA timezone (``zoneinfo``);
never hardcode an offset (MST vs MDT is handled automatically).

Ported/adapted from the sibling Astronomy project's ``scripts/planning_config.py``
(M110 stores one site per profile file under ``PROFILES_DIR`` and adds the glow
layer; the Astronomy ``[positions]`` multi-mask-per-file scheme is replaced by
one profile per location).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

DEFAULT_PROFILE = "default"


@dataclass
class Site:
    name: str = "Home"
    latitude_deg: float = 40.015
    longitude_deg: float = -105.270
    elevation_m: float = 1655.0
    timezone: str = "America/Denver"
    # Physical horizon mask — filename (resolved against the profiles dir) or an
    # absolute path. Empty → an open horizon (no obstruction).
    horizon_mask: str = ""
    # Light-pollution glow layer (populated by the light-dome phase; empty = unset).
    bortle: int = 0
    sqm_zenith: float = 0.0
    glow_mask: str = ""             # broadband glow floor
    glow_mask_narrowband: str = ""  # softer floor for ON/LP (narrowband) filters
    # Directory the mask filenames resolve against (set by load_site).
    profiles_dir: Path | None = field(default=None, repr=False)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def localize(self, naive: datetime) -> datetime:
        """Attach the site timezone to a naive local datetime."""
        return naive.replace(tzinfo=self.tz)

    def _resolve(self, name: str) -> str | None:
        if not name:
            return None
        if os.path.isabs(name):
            return name
        base = self.profiles_dir or config.PROFILES_DIR
        return str(Path(base) / name)

    def mask_path(self) -> str | None:
        """Absolute path to the physical horizon mask, or ``None`` if unset."""
        return self._resolve(self.horizon_mask)

    def glow_path(self, narrowband: bool = False) -> str | None:
        """Absolute path to the glow mask (broadband, or narrowband if asked and
        a narrowband variant is configured), or ``None`` if unset."""
        if narrowband and self.glow_mask_narrowband:
            return self._resolve(self.glow_mask_narrowband)
        return self._resolve(self.glow_mask)


@dataclass
class Device:
    name: str = "ZWO Seestar S50"
    start_alt_ceiling_deg: float = 78.0  # device rejects a start above this
    low_alt_floor_deg: float = 10.0      # atmosphere/seeing limit
    max_exposure_s: int = 30
    default_exposure_s: int = 20
    one_exposure_per_plan: bool = True
    gain: int = 80
    retry_wait_s: int = 300


def _load_toml(path) -> dict:
    p = Path(path)
    if not p.is_file():
        return {}
    with p.open("rb") as f:
        return tomllib.load(f)


def profile_path(name: str = DEFAULT_PROFILE) -> Path:
    """The ``<name>.toml`` path under the store's profiles dir."""
    return Path(config.PROFILES_DIR) / f"{name}.toml"


def list_profiles() -> list[str]:
    """Profile names (``<name>.toml`` stems) present in the store, sorted with
    ``default`` first."""
    d = Path(config.PROFILES_DIR)
    if not d.is_dir():
        return []
    names = sorted(p.stem for p in d.glob("*.toml"))
    if DEFAULT_PROFILE in names:
        names.remove(DEFAULT_PROFILE)
        names.insert(0, DEFAULT_PROFILE)
    return names


def load_site(name: str = DEFAULT_PROFILE, path=None) -> Site:
    """Load a site profile by name (or an explicit path), falling back to in-code
    defaults when the file is missing."""
    p = Path(path) if path else profile_path(name)
    raw = _load_toml(p)
    site = Site(profiles_dir=p.parent)
    for k, v in raw.get("site", {}).items():
        if hasattr(site, k) and k != "profiles_dir":
            setattr(site, k, v)
    horizon = raw.get("horizon", {})
    if "mask" in horizon:
        site.horizon_mask = horizon["mask"]
    glow = raw.get("glow", {})
    for src, dst in (("bortle", "bortle"), ("sqm_zenith", "sqm_zenith"),
                     ("mask", "glow_mask"), ("mask_narrowband", "glow_mask_narrowband")):
        if src in glow:
            setattr(site, dst, glow[src])
    return site


def load_device(name: str = "device", path=None) -> Device:
    """Load a device profile (optional ``device.toml`` under the profiles dir),
    falling back to in-code Seestar S50 defaults."""
    p = Path(path) if path else profile_path(name)
    raw = _load_toml(p)
    dev = Device()
    for k, v in raw.get("device", {}).items():
        if hasattr(dev, k):
            setattr(dev, k, v)
    return dev
