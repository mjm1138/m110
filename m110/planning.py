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
from functools import lru_cache
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

# A window-truncated slot on a *descending* target this short (minutes) is flagged
# marginal ("last chance"): at low, sinking altitude the S50 rejects well above the
# ~30% baseline on FWHM/roundness, so a 20–30 min token slot may yield ≤10 usable
# minutes (2026-07-14 harness review, GAP 2). Longer last-grabs still pay.
MARGINAL_SLOT_MIN = 30

# Shortest slot the sequencer will schedule (minutes). Below this, a slot isn't
# worth the slew + autofocus overhead (a 10-min stub after setup yields almost
# nothing usable), so the target is dropped for tonight rather than tokened in
# (2026-07-17 tuning call). Also the floor for the night÷count base duration.
MIN_SLOT_MIN = 30


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


def _utc_times(naive_locals, site: Site):
    """The batched partner to `to_utc`: naive local wall times → **one** astropy
    ``Time`` array. Same conversion, one object instead of N.

    Worth its own function because `Time.__init__` is not cheap and this sits on
    the twilight hot path — building one `Time` per 5-minute step ran to ~204k
    constructions (≈10 s) in a single prioritizer pass over the Messier list."""
    from astropy.time import Time
    return Time([site.localize(t).astimezone(_UTC).replace(tzinfo=None)
                 for t in naive_locals])


# Twilight is a pure function of (site geometry, timezone, date) — the answer for a
# given night never changes — so it memoizes safely for the life of the process.
# It matters because it sits under `observability`, which the prioritizer calls per
# target across a ~22-date forward grid: one uncached run over the Messier list made
# 535 twilight calls for 22 distinct dates (24× redundant, and 91% of the runtime).
# Caching turns that cost from O(targets × dates) into O(dates).
#
# The key is the four Site fields the computation actually reads, and the cached
# function takes only those — reconstructing a minimal Site — so it *cannot* quietly
# start depending on a field that isn't in the key. Editing a site profile changes
# the key, so a stale hit isn't possible.
@lru_cache(maxsize=512)
def _twilight_cached(lat: float, lon: float, elev: float, tz: str,
                     year: int, month: int, day: int, step_min: int):
    from astropy.coordinates import AltAz, get_sun
    site = planning_config.Site(latitude_deg=lat, longitude_deg=lon,
                                elevation_m=elev, timezone=tz)
    loc = _location(site)
    base = datetime(year, month, day, 15, 0)
    times = [base + timedelta(minutes=step_min * i)
             for i in range(int(18 * 60 / step_min))]
    T = _utc_times(times, site)
    alt = get_sun(T).transform_to(AltAz(obstime=T, location=loc)).alt.deg

    dusk = dawn = None
    for i in range(len(alt) - 1):
        if alt[i] >= -18 > alt[i + 1]:
            dusk = times[i + 1]
            break
    if dusk is not None:
        # The post-dusk samples are a *slice* of the ones already transformed — the
        # sun's altitude at a given instant doesn't depend on which array it was
        # computed in — so the dawn crossing is read out of `alt`, not out of a
        # second `get_sun` transform over the tail (which is what this used to do).
        for i in range(times.index(dusk) + 1, len(alt) - 1):
            if alt[i] < -18 <= alt[i + 1]:
                dawn = times[i + 1]
                break
    return dusk, dawn


def twilight(year: int, month: int, day: int, site: Site, step_min: int = 5):
    """``(astro_dusk, astro_dawn)`` as naive local datetimes for the night of the
    given evening date — the astronomical-darkness window (sun below −18°). Either
    may be ``None`` at high latitude in summer (no astro dark). Memoized per
    (site, date) — see `_twilight_cached`."""
    return _twilight_cached(site.latitude_deg, site.longitude_deg,
                            site.elevation_m, site.timezone,
                            year, month, day, step_min)


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

    # Moon separation, evaluated at the proposed START (the slot the plan proposes),
    # in a COMMON topocentric AltAz frame. Never `icrs.separation(gcrs_moon)`: that
    # re-expresses the moon's direction from the barycenter and returned 101° where
    # the true separation was 45° (2026-07-17 M3 case — the 2026-07-14 test-harness
    # review, PLANNING_BUGS BUG 1).
    si = times.index(start_time) if start_time in times else ti
    moon = get_body("moon", T[si], location=_location(site))
    fr_si = AltAz(obstime=T[si], location=_location(site))
    moon_sep = float(moon.transform_to(fr_si).separation(aa[si]).deg)

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
    ceiling = device.start_alt_ceiling_deg
    if ceiling is not None:
        ceiling -= START_CEILING_MARGIN_DEG
    return {"window": (dusk, dawn), "moon": moon, "entries": entries,
            # Effective (margin-applied) start ceiling — the sequencer needs the
            # per-tick startability test, not just night_track's single pick.
            "start_ceiling_deg": ceiling, "ceiling_is_hard": device.ceiling_is_hard}


# ── night sequencer (Phase 4 / BUGS #40–42) ──────────────────────────────────

def _ceil_tick(t: datetime, tick_min: int) -> datetime:
    """Round up to the next wall-clock multiple of ``tick_min`` (Seestar plan
    slots must sit on 10-minute increments)."""
    t = t.replace(second=0, microsecond=0)
    over = t.minute % tick_min
    return t if not over else t + timedelta(minutes=tick_min - over)


def _floor_tick(t: datetime, tick_min: int) -> datetime:
    t = t.replace(second=0, microsecond=0)
    return t - timedelta(minutes=t.minute % tick_min)


def _sample_at(entry: dict, t: datetime, tick_min: int = 10):
    """The track sample nearest ``t``: ``(alt, clear)``. Samples are on a 10-min
    grid anchored at dusk and ticks on wall-clock 10s, so a real match is ≤5 min
    away — anything farther means the track has **no data at t** (e.g. the target
    hasn't risen yet) and must not read as startable."""
    samples = entry.get("samples") or []
    if not samples:
        return None, False
    s = min(samples, key=lambda s: abs((s[0] - t).total_seconds()))
    if abs((s[0] - t).total_seconds()) > tick_min * 60 * 0.6:
        return None, False
    return s[1], s[2]


def sequence_plan(plan: dict, *, count: int = 4, scores: dict | None = None,
                  filters: dict | None = None, min_slot_min: int = MIN_SLOT_MIN,
                  tick_min: int = 10, forced_order: list | None = None,
                  fill: bool = True) -> list[dict]:
    """Turn ``plan_night`` output into a **non-overlapping schedule** (Phase 4 /
    BUGS #40–42): ``[{slug, start, end, duration_min, alt_start, filter,
    moon_sep_deg, moon_impact, over_ceiling, marginal}, …]``.

    The BUGS #40 v1 logic, deterministic and pure (no astropy — testable with
    synthetic plan dicts):

    1. Object 1 = the highest-priority target **startable right at astronomical
       dark** (clear at that tick, under the start ceiling, and with at least one
       tick of window left). Base duration = dark span ÷ ``count`` (floored to a
       ``min_slot_min`` minimum), shortened **only** when the target's own
       up-window (or dawn) ends. A primary is left to **overshoot** its deep-stack
       target rather than be trimmed to free time for another slot — max
       integration on the ``count`` chosen objects (2026-07-17 tuning call).
    2. Object N+1 = the highest-priority target startable at object N's end — no
       overlap, no slew/focus modelling.
    3. Near-equal priority (scores quantized to 2 dp) → the one **closer to
       setting** (earlier ``up_end``) goes first.

    ``count`` sizes the slots (the night ÷ count split, at least ``min_slot_min``);
    with ``fill`` on (the default) the sequencer **keeps scheduling past count**
    when early-setting targets leave dark unused, until dawn or candidates run out
    — the 2026-07-14 harness review caught a plan ending at 01:00 with ~3 h of dark
    left (GAP 1). A slot that would come out **shorter than ``min_slot_min``** is
    **dropped, not scheduled** — no 10-minute stubs that a slew + autofocus would
    eat whole.

    A slot cut short by its **own closing window** while the target is
    *descending* is flagged ``marginal`` ("last chance" — heavy frame rejection
    at low, sinking altitude; GAP 2) so the human can drop it knowingly.

    Every start/end sits on a wall-clock ``tick_min`` boundary. A **hard** ceiling
    excludes over-ceiling ticks outright; a **soft** one allows them flagged
    ``over_ceiling`` (rendered ``^``). Moon impact is re-evaluated **at each
    slot's start** from the plan's moon track. ``forced_order`` (slugs) replaces
    the priority selection — the UI's manual reorder/exclude reflow."""
    dusk, dawn = plan.get("window") or (None, None)
    entries = [e for e in (plan.get("entries") or []) if e.get("up_start")]
    if not dusk or not dawn or not entries:
        return []
    scores = scores or {}
    filters = filters or {}
    ceiling = plan.get("start_ceiling_deg")
    hard = plan.get("ceiling_is_hard", True)
    moon = plan.get("moon") or {}
    track = moon.get("track") or []
    illum = moon.get("illum")

    def moon_alt_at(t):
        if not track:
            return None
        return min(track, key=lambda s: abs((s[0] - t).total_seconds()))[1]

    t0, t_end = _ceil_tick(dusk, tick_min), _floor_tick(dawn, tick_min)
    span = (t_end - t0).total_seconds() / 60.0
    if span < tick_min:
        return []
    n = max(1, int(count))
    floor_min = max(tick_min, int(min_slot_min))
    base = max(floor_min, int(span / n // tick_min) * tick_min)

    by_slug = {e["slug"]: e for e in entries}
    if forced_order is not None:
        queue = [s for s in forced_order if s in by_slug]
    else:
        # priority order, ties (2-dp quantum) to the target setting soonest (#40.4)
        queue = [e["slug"] for e in sorted(
            entries, key=lambda e: (-round(scores.get(e["slug"], 0.0), 2),
                                    e["up_end"], e["slug"]))]

    def startable(e, t):
        if (e["up_end"] - t).total_seconds() / 60.0 < tick_min:
            return None                              # window over (or nearly)
        alt, clear = _sample_at(e, t, tick_min)
        if alt is None or not clear:
            return None
        over = ceiling is not None and alt > ceiling
        if over and hard:
            return None
        return alt, over

    slots, used, t = [], set(), t0
    while (t_end - t).total_seconds() / 60.0 >= tick_min:
        if len(slots) >= n and not fill:
            break
        pick = None
        for slug in queue:
            if slug in used:
                continue
            st = startable(by_slug[slug], t)
            if st is not None:
                pick = (slug, *st)
                break
        if pick is None:
            if used >= set(queue):
                break                                 # every candidate is spent
            t += timedelta(minutes=tick_min)          # gap — nothing startable yet
            continue
        slug, alt, over = pick
        e = by_slug[slug]
        # Primaries run the full base slot, capped only by the target's own closing
        # up-window and by dawn — no deep-stack trim (overshoot beats seeding a
        # marginal slot; 2026-07-17). A slot that comes out under the min is dropped
        # (mark the target spent, try the next) rather than scheduled as a stub.
        window_cap = int((e["up_end"] - t).total_seconds() / 60.0 // tick_min) * tick_min
        dawn_cap = int((t_end - t).total_seconds() / 60.0 // tick_min) * tick_min
        dur = min(base, window_cap, dawn_cap)
        if dur < floor_min:
            used.add(slug)
            continue
        # Last-chance guard (GAP 2): a SHORT slot truncated by the target's own
        # closing window while it descends — expect heavy frame rejection at low,
        # sinking altitude. Kept (a deliberate last grab) but flagged.
        end_alt, _ = _sample_at(e, t + timedelta(minutes=dur), tick_min)
        marginal = (dur == window_cap and dur < base and dur <= MARGINAL_SLOT_MIN
                    and end_alt is not None and end_alt < alt)
        malt = moon_alt_at(t)
        slots.append({
            "slug": slug,
            "start": t,
            "end": t + timedelta(minutes=dur),
            "duration_min": dur,
            "alt_start": alt,
            "filter": filters.get(slug),
            "moon_sep_deg": e.get("moon_sep_deg"),
            "moon_alt_at_best": malt,                 # at THIS slot's start
            "moon_impact": moon_impact(illum, malt, e.get("moon_sep_deg", 0.0),
                                       filters.get(slug)),
            "over_ceiling": over,
            "marginal": marginal,
        })
        used.add(slug)
        t += timedelta(minutes=dur)
    return slots
