"""Light-dome **glow floor** — an azimuth-dependent sky-quality floor built from
nearby towns, layered over the physical horizon as ``max(physical, glow)``.

The season/observability gate already reads the ``.hrz`` horizon mask; this adds a
parallel **light-pollution** layer so a target low *toward* a city is demoted while
one equally low *away* from the city is not — a distinction a flat altitude floor
can't make (see ROADMAP item 1 / the Astronomy-prototype finding).

**v1 (bundled, fully offline).** Find populated places within a radius of the site,
compute each town's **bearing** and a **skyglow intensity** via Walker's Law
(``skyglow ∝ population × distance⁻²·⁵``), map each to a **light dome** (a peak floor
altitude + an angular half-width; brighter/closer ⇒ taller and wider), and take the
**upper envelope** across all towns as ``glow_floor(az)``. An optional observed
**Bortle** anchor nudges the whole envelope. The result is emitted as an az/alt
table in the same format ``horizon.load_mask`` consumes, so it composes through the
existing ``horizon.effective_floor`` and is **hand-editable** afterward.

**Filter-aware.** Narrowband/LP filters punch through light pollution, so a softer
narrowband floor is produced alongside the broadband one (same idea as the moon
decision).

Data: a bundled GeoNames populated-places subset (CC-BY 4.0 — see ``NOTICE``),
produced build-time by ``tools/gen_geonames.py`` and **global** (both hemispheres).
The Walker-Law/bearing math is coordinate-sign agnostic, so southern sites work
identically. VIIRS Day/Night-Band radiance is the deferred **v2** precision upgrade.

The scaling constants below are **calibration defaults** — tunable against known
sites (the same "tune with the user" posture as the prioritizer weights).
"""
from __future__ import annotations

import gzip
import math
from dataclasses import dataclass
from pathlib import Path

from . import config

# ── geometry ───────────────────────────────────────────────────────────────────
_EARTH_R_KM = 6371.0088
MI_TO_KM = 1.609344

# ── Walker's-Law dome model (calibration defaults) ─────────────────────────────
DEFAULT_RADIUS_MI = 50.0
WALKER_EXP = 2.5                 # skyglow ∝ population × distance_km^-WALKER_EXP
MAX_PEAK_ALT = 40.0              # deg — cap on the brightest nearby city's dome
# Michaelis–Menten peak mapping: peak = MAX_PEAK_ALT · I/(I + HALF_SAT). A town whose
# intensity equals HALF_SAT gets half the cap. Default ≈ a mid-size metro at ~40 km;
# tune so a known nearby city lands at the observed floor.
HALF_SAT_INTENSITY = 120.0
HALF_WIDTH_BASE = 30.0           # deg of azimuth — a dim dome's half-width
HALF_WIDTH_GAIN = 22.0           # widening added at full brightness
NARROWBAND_FACTOR = 0.6          # softer floor for narrowband/LP filters
STEP_DEG = 5                     # az sampling of the emitted mask
_MIN_POP = 1                     # ignore populationless entries
# A town you're essentially standing in has no meaningful *bearing* (the direction
# between near-coincident points is numerically unstable) and washes the *whole* sky,
# not one azimuth — that all-sky component is the Bortle anchor's job, not a
# directional dome. So towns within this radius don't contribute a directional dome.
MIN_DOME_DIST_KM = 3.0


@dataclass
class Town:
    name: str
    lat: float
    lon: float
    population: int


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (sign-agnostic → works in either hemisphere)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * _EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial true bearing (° clockwise from N) from the observer to a town."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360.0


def _az_delta(a: float, b: float) -> float:
    """Smallest absolute azimuth difference (deg), 0..180, with wraparound."""
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def _intensity(population: int, dist_km: float) -> float:
    """Walker's-Law relative skyglow: ``population × distance_km^-2.5``. A tiny
    floor on distance avoids a singularity for an in-town observer."""
    return population * max(dist_km, 0.5) ** (-WALKER_EXP)


def _peak_alt(intensity: float) -> float:
    """Map a town's intensity to its dome's peak floor altitude (deg), saturating
    toward ``MAX_PEAK_ALT`` so one giant city can't push the floor past the cap."""
    if intensity <= 0:
        return 0.0
    return MAX_PEAK_ALT * intensity / (intensity + HALF_SAT_INTENSITY)


def _half_width(peak: float) -> float:
    """Angular half-width (deg) of a dome — brighter domes spread wider."""
    return HALF_WIDTH_BASE + HALF_WIDTH_GAIN * (peak / MAX_PEAK_ALT)


def _bortle_scale(bortle: int) -> float:
    """Optional observed-Bortle calibration nudge on the whole envelope. Unset
    (``0``) → 1.0 (no change). Bortle 4 (typical suburb) is the neutral point;
    brighter skies scale the floor up, darker down. Clamped so it only nudges."""
    if not bortle:
        return 1.0
    return max(0.5, min(1.7, (bortle / 4.0) ** 0.5))


Mask = list[tuple[float, float]]


def build_glow_floor(lat: float, lon: float, towns, *, radius_mi: float = DEFAULT_RADIUS_MI,
                     bortle: int = 0, narrowband: bool = False,
                     step_deg: int = STEP_DEG) -> Mask:
    """Compute the glow floor as an az/alt table sampled every ``step_deg``.

    ``towns`` is any iterable of :class:`Town` (or ``(name, lat, lon, pop)``). Only
    towns within ``radius_mi`` contribute. Returns ``[(az, alt), …]`` — the upper
    envelope of every town's dome, scaled by the optional Bortle anchor and the
    narrowband softening. An empty/too-far town set yields a flat ``0°`` floor
    (open sky), which composes harmlessly through ``max(physical, glow)``."""
    radius_km = radius_mi * MI_TO_KM
    scale = _bortle_scale(bortle) * (NARROWBAND_FACTOR if narrowband else 1.0)

    # Pre-compute each in-range town's (bearing, peak, half_width).
    domes: list[tuple[float, float, float]] = []
    for t in towns:
        name, tlat, tlon, pop = (t.name, t.lat, t.lon, t.population) \
            if isinstance(t, Town) else t
        if pop < _MIN_POP:
            continue
        d = haversine_km(lat, lon, tlat, tlon)
        if d > radius_km or d < MIN_DOME_DIST_KM:
            continue                     # too far, or the local town (→ Bortle anchor)
        peak = _peak_alt(_intensity(pop, d)) * scale
        if peak <= 0.05:
            continue
        domes.append((bearing_deg(lat, lon, tlat, tlon), peak, _half_width(peak)))

    floor: Mask = []
    for az in range(0, 360, step_deg):
        best = 0.0
        for bearing, peak, hw in domes:
            delta = _az_delta(az, bearing)
            if delta >= hw:
                continue
            # Raised-cosine falloff: peak at the bearing, smoothly → 0 at the edge.
            contrib = peak * math.cos((delta / hw) * (math.pi / 2))
            if contrib > best:
                best = contrib
        floor.append((float(az), round(min(best, MAX_PEAK_ALT), 2)))
    return floor


# ── bundled town data ──────────────────────────────────────────────────────────

# Trimmed GeoNames subset: gzip TSV of `asciiname \t lat \t lon \t population \t cc`,
# produced by tools/gen_geonames.py. cities1000 (pop ≥ 1000) is the chosen extract —
# NOT cities15000: skyglow domes are dominated by nearby towns of a few thousand, and
# using a 15k floor would drop those (biasing rural/southern-hemisphere users). See
# ROADMAP item 1.
GEONAMES_DIR = "geonames"
GEONAMES_FILE = "cities1000.tsv.gz"


def _seed_geonames_path() -> Path:
    return Path(__file__).parent / "seed" / GEONAMES_DIR / GEONAMES_FILE


def load_towns(path=None) -> list[Town]:
    """Load the bundled populated-places table. Returns ``[]`` (not an error) when
    the data isn't present, so the feature degrades to "no auto-map" rather than
    failing — the caller then relies on the Bortle anchor / manual editing."""
    p = Path(path) if path else _seed_geonames_path()
    if not p.is_file():
        return []
    out: list[Town] = []
    with gzip.open(p, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            try:
                out.append(Town(parts[0], float(parts[1]), float(parts[2]),
                                int(parts[3])))
            except ValueError:
                continue
    return out


# ── emit / persist ─────────────────────────────────────────────────────────────

def glow_mask_text(mask: Mask) -> str:
    """Render a glow floor as an ``.hrz``-style ``azimuth altitude`` table (the
    format ``horizon.load_mask`` reads), with a header noting it's generated."""
    lines = ["# M110 light-dome glow floor (generated; azimuth altitude, degrees).",
             "# Hand-editable — see m110/glow.py."]
    lines += [f"{az:g} {alt:g}" for az, alt in mask]
    return "\n".join(lines) + "\n"


def write_glow_masks(profile: str, broadband: Mask, narrowband: Mask) -> tuple[str, str]:
    """Write the broadband + narrowband glow floors beside the profile as
    ``<profile>.glow.hrz`` / ``<profile>.glow-nb.hrz`` and return their filenames
    (to store on the Site's ``glow_mask`` / ``glow_mask_narrowband``). Mirrors
    ``planning_config.import_horizon_mask``'s per-profile naming."""
    d = Path(config.PROFILES_DIR)
    d.mkdir(parents=True, exist_ok=True)
    bb = f"{profile}.glow.hrz"
    nb = f"{profile}.glow-nb.hrz"
    (d / bb).write_text(glow_mask_text(broadband), encoding="utf-8")
    (d / nb).write_text(glow_mask_text(narrowband), encoding="utf-8")
    return bb, nb


def compute_site_glow(lat: float, lon: float, *, radius_mi: float = DEFAULT_RADIUS_MI,
                      bortle: int = 0, towns=None) -> tuple[Mask, Mask, int]:
    """Convenience: load the bundled towns (unless injected), build both the
    broadband and narrowband floors, and report how many towns contributed within
    the radius. Pure compute — the caller persists via :func:`write_glow_masks`."""
    towns = load_towns() if towns is None else towns
    radius_km = radius_mi * MI_TO_KM
    n = sum(1 for t in towns
            if MIN_DOME_DIST_KM <= haversine_km(lat, lon, t.lat, t.lon) <= radius_km
            and t.population >= _MIN_POP)
    bb = build_glow_floor(lat, lon, towns, radius_mi=radius_mi, bortle=bortle)
    nb = build_glow_floor(lat, lon, towns, radius_mi=radius_mi, bortle=bortle,
                          narrowband=True)
    return bb, nb, n
