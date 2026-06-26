"""Session-planning engine — twilight, moon, transit altitude, and a seasonal /
tonight **observability gate** layered with the light-pollution glow floor.

Qt-free. The auto-prioritizer (ROADMAP item 1 / BUGS #21) is the real consumer:
``observability()`` answers *"does this object clear a usable quality floor for
long enough during astronomical darkness — tonight, and for how many more nights
this season?"*, which the scorer turns into a ranking. Coordinates come from the
existing offline reference (:func:`m110.catalog.load_coords`) and the season
window from :func:`m110.catalog.season_from_ra` — no network, no new coord cache.

Astropy (already a core dependency) is imported lazily so the pure helpers and
the horizon/config tests don't pull it in. Ported from the sibling Astronomy
project's ``scripts/sky.py`` + the observability gate of ``scripts/prioritize.py``
(M110 adds the glow layer and returns continuous ``hours_clear`` so the scorer can
*grade* short-window targets rather than hard-drop them).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import catalog
from . import horizon
from . import planning_config

# Re-exports so callers use one module.
Site = planning_config.Site
Device = planning_config.Device
load_site = planning_config.load_site
load_device = planning_config.load_device
list_profiles = planning_config.list_profiles

_UTC = ZoneInfo("UTC")

# Default seasonal-observability gate: an object is "in season" when it clears
# this quality floor (degrees) for at least this many hours of astro dark.
SEASON_MIN_ALT = 30.0
SEASON_MIN_HOURS = 1.5
SEASON_HORIZON_DAYS = 150
SEASON_GRID_DAYS = 7
PREDAWN_EXCLUDE_H = 1.0
SAMPLES = 13

# Filters that punch through light pollution → use the softer narrowband glow floor.
_NARROWBAND_FILTERS = {"ON", "LP"}


# ── coordinate / season helpers ──────────────────────────────────────────────

def _radec(target) -> tuple[float, float] | None:
    """Resolve a target to ``(ra_deg, dec_deg)``. ``target`` is either a slug
    (looked up in the offline reference + library) or an explicit ``(ra, dec)``."""
    if isinstance(target, (tuple, list)) and len(target) == 2:
        return float(target[0]), float(target[1])
    coords = catalog.load_coords()
    key = str(target)
    return coords.get(key) or coords.get(key.lower())


def transit_altitude(dec_deg: float, site: Site) -> float:
    """Upper-culmination (transit) altitude of a target at the site — the highest
    it gets. ``90 − |latitude − declination|``."""
    return round(90.0 - abs(site.latitude_deg - float(dec_deg)), 1)


# ── astropy-backed night math (lazy import) ──────────────────────────────────

def _location(site: Site):
    from astropy.coordinates import EarthLocation
    import astropy.units as u
    return EarthLocation(lat=site.latitude_deg * u.deg,
                         lon=site.longitude_deg * u.deg,
                         height=site.elevation_m * u.m)


def to_utc(naive_local: datetime, site: Site):
    """Naive local wall time → astropy ``Time`` (UTC), via the site's IANA
    timezone. The offset is derived per-date, so MST/MDT is handled automatically."""
    from astropy.time import Time
    aware = site.localize(naive_local)
    return Time(aware.astimezone(_UTC).replace(tzinfo=None))


def twilight(year: int, month: int, day: int, site: Site, step_min: int = 5):
    """``(astro_dusk, astro_dawn)`` as naive local datetimes for the night of the
    given evening date — the astronomical-darkness window (sun below −18°). Either
    may be ``None`` at high latitude in summer (no astro dark)."""
    from astropy.coordinates import AltAz, get_sun
    from astropy.time import Time
    loc = _location(site)
    base = datetime(year, month, day, 15, 0)
    times = [base + timedelta(minutes=step_min * i)
             for i in range(int(18 * 60 / step_min))]
    T = Time([to_utc(t, site) for t in times])
    alt = get_sun(T).transform_to(AltAz(obstime=T, location=loc)).alt.deg

    def cross(thr, rising):
        for i in range(len(alt) - 1):
            if (rising and alt[i] < thr <= alt[i + 1]) or \
               (not rising and alt[i] >= thr > alt[i + 1]):
                return times[i + 1]
        return None

    dusk = cross(-18, False)
    dawn = None
    if dusk:
        after = [t for t in times if t > dusk]
        T2 = Time([to_utc(t, site) for t in after])
        alt2 = get_sun(T2).transform_to(AltAz(obstime=T2, location=loc)).alt.deg
        for i in range(len(alt2) - 1):
            if alt2[i] < -18 <= alt2[i + 1]:
                dawn = after[i + 1]
                break
    return dusk, dawn


def moon_summary(times_local, site: Site):
    """``(altitudes, illuminated_fraction)`` — the moon's altitude at each local
    time plus its illuminated fraction at the window's midpoint."""
    import numpy as np
    from astropy.coordinates import AltAz, get_body, get_sun
    loc = _location(site)
    frames = [AltAz(obstime=to_utc(t, site), location=loc) for t in times_local]
    alts = [float(get_body("moon", fr.obstime, location=loc).transform_to(fr).alt.deg)
            for fr in frames]
    mid = frames[len(frames) // 2]
    elong = get_sun(mid.obstime).separation(
        get_body("moon", mid.obstime, location=loc)).deg
    illum = (1 - np.cos(np.radians(elong))) / 2.0
    return alts, illum


# ── observability gate ───────────────────────────────────────────────────────

def _load_mask(path):
    if not path:
        return []
    try:
        return horizon.load_mask(path)
    except (OSError, ValueError):
        return []  # unconfigured / empty → open in that layer


def _clear_hours(ra_deg, dec_deg, day: date, site, physical, glow,
                 min_alt, samples, predawn_exclude_h):
    """Hours the target spends above ``min_alt`` AND above the combined horizon +
    glow floor during astro dark, ignoring the final ``predawn_exclude_h``. Returns
    ``(hours_clear, window_h)`` — ``window_h`` is ``None`` when there's no astro dark."""
    from astropy.coordinates import AltAz, SkyCoord
    from astropy.time import Time
    import astropy.units as u

    dusk, dawn = twilight(day.year, day.month, day.day, site)
    if not dusk or not dawn:
        return None, None
    window_h = (dawn - dusk).total_seconds() / 3600.0
    times = [dusk + (dawn - dusk) * (i / (samples - 1)) for i in range(samples)]
    fr = AltAz(obstime=Time([to_utc(t, site) for t in times]), location=_location(site))
    aa = SkyCoord(ra_deg * u.deg, dec_deg * u.deg).transform_to(fr)
    alts, azs = aa.alt.deg, aa.az.deg
    clear = 0
    for t, az, alt in zip(times, azs, alts):
        if predawn_exclude_h and (dawn - t).total_seconds() < predawn_exclude_h * 3600:
            continue
        if alt > min_alt and not horizon.is_below_floor(float(az), float(alt),
                                                        physical, glow):
            clear += 1
    return (clear / samples) * window_h, window_h


def observability(target, day: date, site: Site, *,
                  min_alt: float = SEASON_MIN_ALT, min_hours: float = SEASON_MIN_HOURS,
                  filter: str | None = None, samples: int = SAMPLES,
                  predawn_exclude_h: float = PREDAWN_EXCLUDE_H,
                  horizon_days: int = SEASON_HORIZON_DAYS,
                  grid_days: int = SEASON_GRID_DAYS) -> dict:
    """Seasonal/tonight observability for a target from a site on ``day``.

    Returns ``{observable, hours_clear, transit_alt, nights_to_close, season}``:

    * ``observable`` — clears ``min_alt`` + the glow/horizon floor for ≥
      ``min_hours`` of astro dark (ignoring the final pre-dawn hour).
    * ``hours_clear`` — the continuous clear-time figure (so the scorer can *grade*
      a short window rather than treat the gate as binary); ``None`` if there's no
      astronomical darkness.
    * ``transit_alt`` — upper-culmination altitude at the site.
    * ``nights_to_close`` — nights until the target stops being observable (forward
      grid scan); ``None`` if it isn't observable now or never closes within the
      look-ahead horizon.
    * ``season`` — the derived observing window (``catalog.season_from_ra``).

    The glow floor is filter-aware: narrowband/LP filters use the softer
    ``glow_mask_narrowband`` layer when configured.
    """
    rd = _radec(target)
    if rd is None:
        return {"observable": None, "hours_clear": None, "transit_alt": None,
                "nights_to_close": None, "season": ""}
    ra_deg, dec_deg = rd
    narrowband = (filter or "").upper() in _NARROWBAND_FILTERS
    physical = _load_mask(site.mask_path())
    glow = _load_mask(site.glow_path(narrowband=narrowband))
    season = catalog.season_from_ra(ra_deg)
    transit = transit_altitude(dec_deg, site)

    hours, window_h = _clear_hours(ra_deg, dec_deg, day, site, physical, glow,
                                   min_alt, samples, predawn_exclude_h)
    if window_h is None:  # no astro dark → don't gate
        return {"observable": True, "hours_clear": None, "transit_alt": transit,
                "nights_to_close": None, "season": season}
    observable = hours >= min_hours
    nights_to_close = None
    if observable:
        nights_to_close = horizon_days
        for off in range(grid_days, horizon_days + 1, grid_days):
            h, w = _clear_hours(ra_deg, dec_deg, day + timedelta(days=off), site,
                                physical, glow, min_alt, samples, predawn_exclude_h)
            if w is not None and h < min_hours:
                nights_to_close = off
                break
    return {"observable": observable, "hours_clear": round(hours, 2),
            "transit_alt": transit, "nights_to_close": nights_to_close,
            "season": season}
