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

# Planning margin under the device's start-refusal ceiling: the Seestar app's
# threshold reads tighter than nominal (M94 was rejected at ~78° against the
# advertised 80°), so proposed starts stay a few degrees below the profile value —
# the Astronomy "plan with ~75° practical" rule.
START_CEILING_MARGIN_DEG = 3.0


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


def pick_start(samples, ceiling, hard: bool):
    """The best **startable** moment from a night track (Phase 3 / BUGS #37):
    ``(start_time, start_alt, over_ceiling)``.

    ``samples`` = ``[(time, alt, clear), …]``. The Seestar app rejects a capture
    whose target is above the ceiling at the slot's **start** (start-only — it may
    ride through zenith once running), so the pick is the highest *clear* sample at
    or below the ceiling — i.e. a rising- or setting-side slot for a high-transit
    target, never the over-ceiling transit itself.

    A **hard** ceiling with no startable sample → ``(None, None, True)`` (the
    device would refuse every start). A **soft** ceiling (Dwarf alt-az: quality
    guideline, not a firmware refusal) falls back to the best clear sample with
    ``over_ceiling=True`` so the consumer can annotate. Pure — no astropy."""
    clear = [(t, a) for t, a, c in samples if c]
    if not clear:
        return None, None, False
    startable = ([(t, a) for t, a in clear if a <= ceiling]
                 if ceiling is not None else clear)
    if startable:
        t, a = max(startable, key=lambda x: x[1])
        return t, a, False
    if hard:
        return None, None, True
    t, a = max(clear, key=lambda x: x[1])
    return t, a, True


def moon_impact(illum, moon_alt, sep_deg, filter: str | None = None) -> str | None:
    """Plain-language moon impact on one target's slot — ``None`` when the moon is
    **below the horizon** (separation is physically meaningless then; BUGS #36), else
    ``"none"/"low"/"medium"/"high"``.

    Impact = illumination × proximity, discounted for narrowband: broadband (IRCUT)
    suffers within ~40–50° of a bright moon, LP/dual-band tolerates much closer (the
    Astronomy moon rule). Pure + deterministic so the field guide can *explain* it."""
    if moon_alt is None or moon_alt <= 0:
        return None
    if illum is None:
        return "low"                                    # moon up, phase unknown → mild
    score = float(illum) * max(0.0, 1.0 - float(sep_deg) / 120.0)
    if (filter or "").upper() in _NARROWBAND_FILTERS:
        score *= 0.25                                   # narrowband ≈ near-immune
    if score >= 0.35:
        return "high"
    if score >= 0.15:
        return "medium"
    if score >= 0.05:
        return "low"
    return "none"


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
    import warnings
    with warnings.catch_warnings():          # sun–moon elongation frame transform is
        warnings.simplefilter("ignore")      # ~1° precise; plenty for an illum fraction
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


# ── tonight's plan: per-target time windows + ordering (Checkpoint B) ──────────

def _contiguous_up(samples, min_alt, physical, glow):
    """Given ``[(local_time, alt, az)]`` across the dark window, return the
    ``(start, end)`` of the **longest** run that's above ``min_alt`` AND above the
    horizon+glow floor — the target's usable window tonight — or ``(None, None)``."""
    best = (None, None, 0.0)
    run_start = None
    for t, alt, az in list(samples) + [(None, -90.0, 0.0)]:
        clear = (t is not None and alt > min_alt
                 and not horizon.is_below_floor(float(az), float(alt), physical, glow))
        if clear and run_start is None:
            run_start = t
        elif not clear and run_start is not None:
            span = (prev_t - run_start).total_seconds()
            if span > best[2]:
                best = (run_start, prev_t, span)
            run_start = None
        prev_t = t
    return best[0], best[1]


def night_track(target, day: date, site: Site, *, filter: str | None = None,
                min_alt: float = SEASON_MIN_ALT, step_min: int = 10,
                window=None, device=None) -> dict | None:
    """A target's track across tonight's astro-dark window (for the planner + the
    timeline chart). Returns ``None`` when the target can't be resolved or there's no
    astronomical darkness; otherwise::

        {slug, transit_time, transit_alt, best_alt, start_time, start_alt,
         over_ceiling, up_start, up_end, moon_sep_deg,
         samples: [(local_time, alt, clear_bool)]}

    ``up_start``/``up_end`` is the longest contiguous stretch above ``min_alt`` and
    the (filter-aware) horizon+glow floor; ``transit_time`` is the arg-max altitude
    (astronomy truth), while ``start_time``/``start_alt`` is the recommended
    **startable** slot under the device's start-altitude ceiling (:func:`pick_start`
    — Phase 3 / BUGS #37; ``device`` defaults to the store's device profile);
    ``moon_sep_deg`` is the angular separation from the moon at transit."""
    from astropy.coordinates import AltAz, SkyCoord, get_body
    from astropy.time import Time
    import astropy.units as u

    rd = _radec(target)
    if rd is None:
        return None
    # `window` lets plan_night compute twilight ONCE (the 18h sun scan) and reuse it
    # across all targets on a night, instead of paying it per target.
    dusk, dawn = window if window is not None else twilight(day.year, day.month, day.day, site)
    if not dusk or not dawn:
        return None
    ra_deg, dec_deg = rd
    narrowband = (filter or "").upper() in _NARROWBAND_FILTERS
    physical = _load_mask(site.mask_path())
    glow = _load_mask(site.glow_path(narrowband=narrowband))

    n = max(2, int((dawn - dusk).total_seconds() / 60 / step_min) + 1)
    times = [dusk + (dawn - dusk) * (i / (n - 1)) for i in range(n)]
    T = Time([to_utc(t, site) for t in times])
    fr = AltAz(obstime=T, location=_location(site))
    coord = SkyCoord(ra_deg * u.deg, dec_deg * u.deg)
    aa = coord.transform_to(fr)
    alts, azs = [float(a) for a in aa.alt.deg], [float(a) for a in aa.az.deg]

    samples = list(zip(times, alts, azs))
    up_start, up_end = _contiguous_up(samples, min_alt, physical, glow)
    ti = max(range(n), key=lambda i: alts[i])          # transit (arg-max altitude)
    transit_time = times[ti]
    import warnings
    with warnings.catch_warnings():                    # moon-sep frame transform is
        warnings.simplefilter("ignore")                # ~1° precise; that's plenty here
        moon = get_body("moon", T[ti], location=_location(site))
        moon_sep = float(coord.separation(moon).deg)

    def clear(alt, az):
        return alt > min_alt and not horizon.is_below_floor(az, alt, physical, glow)

    if device is None:
        device = planning_config.load_device()
    out_samples = [(t, round(a, 1), clear(a, z)) for t, a, z in samples]
    ceiling = device.start_alt_ceiling_deg
    if ceiling is not None:
        ceiling -= START_CEILING_MARGIN_DEG     # plan under the refusal threshold
    start_time, start_alt, over_ceiling = pick_start(
        out_samples, ceiling, device.ceiling_is_hard)

    return {
        "slug": str(target) if not isinstance(target, (tuple, list)) else "",
        "transit_time": transit_time,
        "transit_alt": round(alts[ti], 1),
        "best_alt": round(max(alts), 1),
        "start_time": start_time,
        "start_alt": start_alt,
        "over_ceiling": over_ceiling,
        "up_start": up_start,
        "up_end": up_end,
        "moon_sep_deg": round(moon_sep, 1),
        "samples": out_samples,
    }


def plan_night(site: Site, day: date, targets, *, order: str = "auto",
               scores: dict | None = None, filters: dict | None = None,
               step_min: int = 10, device=None) -> dict:
    """Build tonight's plan for ``targets`` (slugs). Returns
    ``{window: (dusk, dawn), moon: {…}, entries: [night_track, …]}``.

    The moon is sampled **across the whole dark window** (BUGS #36 — a 5-hour night
    can't be described by one dusk snapshot)::

        moon = {illum,                  # fraction at the window midpoint
                alt,                    # at dusk
                set_time, rise_time,    # crossings inside the window (else None)
                track: [(local_time, alt), …]}

    and every entry is annotated with ``moon_alt_at_best`` (the moon's altitude at
    that target's proposed slot) + ``moon_impact`` (via :func:`moon_impact`, using
    the target's filter) — so consumers can gate the separation column on moon-up.
    ``device`` (default: the store's device profile) supplies the start-altitude
    ceiling; each entry carries ``start_time``/``start_alt``/``over_ceiling`` from
    :func:`pick_start`.

    Only targets that are actually **up** tonight (a real ``up_start``) are kept.
    ``order="auto"`` sorts by ``up_end`` ascending — **the target setting soonest
    goes first** — tie-broken by prioritizer ``score`` (higher first); ``"manual"``
    preserves the input order. ``filters`` optionally maps slug → capture filter (so
    the glow floor is filter-aware per target)."""
    scores = scores or {}
    filters = filters or {}
    if device is None:
        device = planning_config.load_device()
    dusk, dawn = twilight(day.year, day.month, day.day, site)
    moon = {"illum": None, "alt": None, "set_time": None, "rise_time": None,
            "track": []}
    times, malts, illum = [], [], None
    if dusk and dawn:
        n = max(2, int((dawn - dusk).total_seconds() / 60 / step_min) + 1)
        times = [dusk + (dawn - dusk) * (i / (n - 1)) for i in range(n)]
        malts, illum = moon_summary(times, site)
        set_time = rise_time = None
        for i in range(len(malts) - 1):
            if malts[i] > 0 >= malts[i + 1] and set_time is None:
                set_time = times[i + 1]
            if malts[i] <= 0 < malts[i + 1] and rise_time is None:
                rise_time = times[i + 1]
        moon = {"illum": round(float(illum), 2), "alt": round(malts[0], 1),
                "set_time": set_time, "rise_time": rise_time,
                "track": [(t, round(a, 1)) for t, a in zip(times, malts)]}

    entries = []
    if dusk and dawn:
        for slug in targets:
            tr = night_track(slug, day, site, filter=filters.get(slug),
                             step_min=step_min, window=(dusk, dawn), device=device)
            if tr and tr["up_start"] is not None:
                # Moon state at this target's proposed slot (its startable start
                # when the ceiling picked one, else transit) — nearest grid sample.
                anchor = tr["start_time"] or tr["transit_time"]
                bi = min(range(len(times)),
                         key=lambda i: abs((times[i] - anchor).total_seconds()))
                tr["moon_alt_at_best"] = round(malts[bi], 1)
                tr["moon_impact"] = moon_impact(moon["illum"], malts[bi],
                                                tr["moon_sep_deg"], filters.get(slug))
                entries.append(tr)

    if order == "auto":
        entries.sort(key=lambda e: (e["up_end"], -scores.get(e["slug"], 0.0)))
    return {"window": (dusk, dawn), "moon": moon, "entries": entries}
