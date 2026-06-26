"""Local horizon / obstruction mask plus a light-pollution **glow** layer.

Loads measured ``(azimuth, altitude)`` pairs and tests whether a sky position is
blocked by the local skyline — and, layered on top, by an azimuth-dependent
light-pollution *glow floor* (the Boulder/Denver dome over the southern horizon).
The effective floor at any azimuth is ``max(physical_obstruction, glow_floor)``.

Two interchangeable input formats (auto-detected — the parser is delimiter-
agnostic, so the extension is just convention):

* **CSV** (``.csv``): ``azimuth,altitude`` per row, ``#`` comments, optional
  ``az,alt`` header.
* **Stellarium/NINA horizon files** (``.hrz``): whitespace-separated
  ``azimuth altitude`` per line, azimuths ascending from 0 (often with a closing
  360 point — treated as the wrap of 0). This is what **theo.rocks** (the mobile
  web app that builds a horizon profile by panning the phone around the skyline,
  the recommended way for M110 users to capture a mask) exports. Negative
  altitudes are kept as-is (an open horizon below 0° is never an obstruction).

Azimuth = true north, clockwise; altitude = top of the obstruction. Points need
not be evenly spaced; the altitude at an arbitrary azimuth is linearly
interpolated, with 0/360 wraparound. Duplicate azimuths (vertical obstruction
edges) keep the higher altitude.

Ported from the sibling Astronomy project's ``scripts/horizon.py`` (the glow
layer + ``effective_floor`` are new for M110).
"""
from __future__ import annotations

import bisect

Mask = list[tuple[float, float]]


def load_mask(path) -> Mask:
    """Parse a horizon/glow mask file into sorted ``(azimuth, altitude)`` pairs."""
    pts: list[tuple[float, float]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "#;":
                continue
            if line.lower().replace(" ", "").startswith("az,"):
                continue
            parts = line.replace(",", " ").split()
            if len(parts) < 2:
                continue
            try:
                az, alt = float(parts[0]), float(parts[1])
            except ValueError:
                continue  # tolerate stray metadata lines in exported files
            pts.append((az % 360.0, alt))
    # Duplicate azimuths: a closing 360 row wraps onto 0; vertical obstruction
    # edges use repeated azimuths. Keep the HIGHER altitude (conservative).
    dedup: dict[float, float] = {}
    for az, alt in pts:
        dedup[az] = max(alt, dedup.get(az, alt))
    out = sorted(dedup.items())
    if not out:
        raise ValueError(f"no horizon points in {path}")
    return out


def horizon_alt(az: float, pts: Mask) -> float:
    """Interpolated obstruction altitude (deg) at azimuth ``az``, with 0/360 wrap."""
    az %= 360.0
    azs = [p[0] for p in pts]
    i = bisect.bisect_left(azs, az)
    if 0 < i < len(pts):
        a0, h0 = pts[i - 1]
        a1, h1 = pts[i]
        if a1 == a0:
            return max(h0, h1)
        return h0 + (h1 - h0) * ((az - a0) / (a1 - a0))
    # wrap segment: between the last point and the first point (+360)
    a0, h0 = pts[-1]
    a1, h1 = pts[0]
    span = (a1 + 360.0) - a0
    if span == 0:
        return h0
    return h0 + (h1 - h0) * (((az - a0) % 360.0) / span)


def is_obstructed(az: float, alt: float, pts: Mask) -> bool:
    """True if a target at ``(az, alt)`` is below the local physical horizon. An
    empty mask is treated as an open horizon (never obstructed)."""
    return bool(pts) and alt < horizon_alt(az, pts)


def effective_floor(az: float, *masks: Mask) -> float:
    """The combined altitude floor at ``az`` across one or more masks — the
    physical horizon layered with the light-pollution glow floor, etc. Returns
    ``max`` over the non-empty masks, or a wide-open ``-90.0`` if none apply."""
    vals = [horizon_alt(az, m) for m in masks if m]
    return max(vals) if vals else -90.0


def is_below_floor(az: float, alt: float, *masks: Mask) -> bool:
    """True if ``(az, alt)`` is below the combined floor of the given masks
    (physical horizon + glow). Empty masks are ignored (open in that arc)."""
    return alt < effective_floor(az, *masks)
