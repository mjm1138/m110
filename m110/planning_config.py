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
import shutil
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

DEFAULT_PROFILE = "default"
# Which site profile the planner/prioritizer reads. Persisted in settings.json
# (not in a profile file) so it's a per-user choice, not per-store data.
ACTIVE_PROFILE_SETTING = "active_site_profile"


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


# ── writers (author profiles from the Planning UI) ─────────────────────────────

def _toml_str(v) -> str:
    """Quote a string as a TOML basic string."""
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _num(v) -> str:
    """Render a number: integers stay integers, floats keep a decimal point."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    f = float(v)
    return str(int(f)) + ".0" if f == int(f) else repr(f)


def format_site_toml(site: Site) -> str:
    """Serialize a :class:`Site` to the ``[site]``/``[horizon]``/``[glow]`` TOML
    shape (matching ``config.DEFAULT_PROFILE_TOML``). Hand-written rather than via
    a TOML lib (no writer dependency; mirrors ``pins._write``/``_write_library``)."""
    return (
        "# M110 observing-site profile. Session planning derives twilight, transit\n"
        "# altitude, and observability from it. See m110/planning_config.py.\n\n"
        "[site]\n"
        f"name = {_toml_str(site.name)}\n"
        f"latitude_deg = {_num(site.latitude_deg)}        # decimal degrees, +N\n"
        f"longitude_deg = {_num(site.longitude_deg)}       # decimal degrees, +E\n"
        f"elevation_m = {_num(site.elevation_m)}           # metres above sea level\n"
        f"timezone = {_toml_str(site.timezone)}  # IANA timezone (DST automatic)\n\n"
        "[horizon]\n"
        "# Physical skyline obstruction (.hrz/CSV, e.g. from theo.rocks). Empty = open.\n"
        f"mask = {_toml_str(site.horizon_mask)}\n\n"
        "[glow]\n"
        "# Light-pollution layer (the city light-dome). Filled by the light-dome lookup.\n"
        f"bortle = {_num(int(site.bortle))}\n"
        f"sqm_zenith = {_num(site.sqm_zenith)}\n"
        f"mask = {_toml_str(site.glow_mask)}\n"
        f"mask_narrowband = {_toml_str(site.glow_mask_narrowband)}\n"
    )


def save_site(site: Site, name: str = DEFAULT_PROFILE) -> Path:
    """Write ``<name>.toml`` under the store's profiles dir; returns its path."""
    p = profile_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(format_site_toml(site), encoding="utf-8")
    return p


def delete_profile(name: str) -> None:
    """Delete a site profile. The ``default`` profile is protected (there must
    always be a fallback). If the deleted profile was active, reset to default."""
    if name == DEFAULT_PROFILE:
        raise ValueError("The default profile can't be deleted.")
    p = profile_path(name)
    if p.is_file():
        p.unlink()
    if config.get_setting(ACTIVE_PROFILE_SETTING) == name:
        config.save_setting(ACTIVE_PROFILE_SETTING, DEFAULT_PROFILE)


def import_horizon_mask(src_path, profile: str = DEFAULT_PROFILE,
                        *, narrowband: bool = False, glow: bool = False) -> str:
    """Copy a user-picked ``.hrz``/CSV mask into the profiles dir under a stable
    per-profile filename and return that filename (to store on the Site's
    ``horizon_mask``/``glow_mask``/``glow_mask_narrowband`` field).

    Validates the file parses first (``horizon.load_mask`` raises on an unusable
    file). ``glow``/``narrowband`` pick the destination name so a profile's
    physical + glow masks don't collide."""
    from . import horizon
    src = Path(src_path)
    horizon.load_mask(str(src))     # raises ValueError on an unparseable/empty file
    suffix = ("glow-nb" if narrowband else "glow") if glow else "horizon"
    dest_dir = Path(config.PROFILES_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{profile}.{suffix}.hrz"
    shutil.copyfile(src, dest)      # bytes only (mask files are plain text)
    return dest.name


# ── active-profile selection (which site the planner reads) ────────────────────

def active_profile() -> str:
    """The selected active site profile name. Falls back to the first available
    profile (``default`` sorts first), then to :data:`DEFAULT_PROFILE`."""
    name = config.get_setting(ACTIVE_PROFILE_SETTING, "") or ""
    profiles = list_profiles()
    if name and name in profiles:
        return name
    return profiles[0] if profiles else DEFAULT_PROFILE


def set_active_profile(name: str) -> None:
    config.save_setting(ACTIVE_PROFILE_SETTING, name)


def load_active_site() -> Site:
    """Load the site profile the planner/prioritizer should use."""
    return load_site(active_profile())


# ── optional online geocode (place name → coordinates) ─────────────────────────

def geocode(query: str, *, timeout: int = 6, fetch=None):
    """Best-effort place-name → ``(lat, lon, display_name)`` via OpenStreetMap
    Nominatim. Returns ``None`` on any failure (offline, no match, parse error).

    Opt-in — a user clicks "Look up" — and sends only the typed query. Manual
    lat/lon entry is the baseline, so this never blocks profile authoring."""
    import json
    import urllib.parse
    import urllib.request

    q = (query or "").strip()
    if not q:
        return None
    if fetch is None:
        from . import updates

        def fetch(url):
            req = urllib.request.Request(url, headers={
                "User-Agent": f"M110/{updates.current_version()} (observing-site geocode)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                return json.loads(r.read().decode("utf-8"))

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1})
    try:
        data = fetch(url)
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None
    top = data[0]
    try:
        return (float(top["lat"]), float(top["lon"]), top.get("display_name") or q)
    except (KeyError, TypeError, ValueError):
        return None
