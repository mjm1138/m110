"""Light-dome glow-floor engine (m110/glow.py) — pure math over fixture towns."""
import math

import pytest

from m110 import glow, horizon


def _floor_at(mask, az):
    """Nearest-sample floor altitude at azimuth `az` (masks are sampled every 5°)."""
    return min(mask, key=lambda p: glow._az_delta(p[0], az))[1]


# ── geometry sanity (both hemispheres) ─────────────────────────────────────────

def test_bearing_cardinal_directions():
    # A point due north / east of the observer.
    assert glow.bearing_deg(0, 0, 1, 0) == pytest.approx(0, abs=1)      # north
    assert glow.bearing_deg(0, 0, 0, 1) == pytest.approx(90, abs=1)     # east


def test_haversine_southern_hemisphere():
    # ~1° of latitude ≈ 111 km, near Sydney (works with negative coords).
    d = glow.haversine_km(-33.87, 151.21, -34.87, 151.21)
    assert d == pytest.approx(111, abs=2)


def test_southern_site_builds_a_dome():
    # A town due north of a southern-hemisphere observer produces a northern dome.
    obs = (-33.0, 18.0)  # ~Cape Town-ish
    towns = [glow.Town("City", -32.7, 18.0, 500_000)]
    mask = glow.build_glow_floor(*obs, towns)
    assert _floor_at(mask, 0) > _floor_at(mask, 180)   # glow toward the city (north)


# ── Walker's-Law monotonicity ──────────────────────────────────────────────────

def test_peak_grows_with_population():
    near = glow._peak_alt(glow._intensity(1_000_000, 30))
    far = glow._peak_alt(glow._intensity(10_000, 30))
    assert near > far > 0


def test_peak_grows_as_town_gets_closer():
    close = glow._peak_alt(glow._intensity(100_000, 10))
    distant = glow._peak_alt(glow._intensity(100_000, 60))
    assert close > distant > 0


def test_peak_saturates_below_cap():
    huge = glow._peak_alt(glow._intensity(50_000_000, 5))
    assert huge < glow.MAX_PEAK_ALT           # one megacity can't blow past the cap
    assert huge > glow.MAX_PEAK_ALT * 0.8     # …but it's near it


# ── dome shape + upper envelope ────────────────────────────────────────────────

def test_dome_peaks_toward_city_and_fades_away():
    obs = (40.0, -105.0)
    towns = [glow.Town("Metro", 39.7, -105.0, 1_000_000)]   # due south, ~33 km
    mask = glow.build_glow_floor(*obs, towns)
    assert _floor_at(mask, 180) > 15          # solid floor toward the city
    assert _floor_at(mask, 0) < 2             # open sky away from it (north)


def test_upper_envelope_of_two_cities():
    obs = (40.0, -105.0)
    towns = [glow.Town("South", 39.6, -105.0, 800_000),    # ~S
             glow.Town("East", 40.0, -104.5, 800_000)]     # ~E
    mask = glow.build_glow_floor(*obs, towns)
    assert _floor_at(mask, 180) > 10          # both directions raised
    assert _floor_at(mask, 90) > 10
    assert _floor_at(mask, 315) < 5           # the gap between them stays open


def test_out_of_range_town_contributes_nothing():
    obs = (40.0, -105.0)
    far = [glow.Town("Faraway", 20.0, -105.0, 5_000_000)]  # ~2200 km away
    mask = glow.build_glow_floor(*obs, far, radius_mi=50)
    assert all(alt == 0 for _, alt in mask)


def test_empty_towns_is_open_sky():
    mask = glow.build_glow_floor(40.0, -105.0, [])
    assert all(alt == 0 for _, alt in mask)


# ── narrowband softening + Bortle nudge ────────────────────────────────────────

def test_narrowband_floor_is_softer():
    obs = (40.0, -105.0)
    towns = [glow.Town("Metro", 39.7, -105.0, 1_000_000)]
    bb = glow.build_glow_floor(*obs, towns)
    nb = glow.build_glow_floor(*obs, towns, narrowband=True)
    assert _floor_at(nb, 180) == pytest.approx(
        _floor_at(bb, 180) * glow.NARROWBAND_FACTOR, rel=0.01)


def test_bortle_scale_monotonic_and_neutral_when_unset():
    assert glow._bortle_scale(0) == 1.0
    assert glow._bortle_scale(7) > glow._bortle_scale(4) > glow._bortle_scale(2)


# ── composition with the physical horizon (the whole point) ────────────────────

def test_glow_composes_with_horizon_to_demote_toward_city():
    obs = (40.0, -105.0)
    towns = [glow.Town("Metro", 39.6, -105.0, 1_500_000)]   # due south
    glow_mask = glow.build_glow_floor(*obs, towns)
    physical: horizon.Mask = []                              # open physical horizon
    # A target at 15° altitude: obstructed toward the city (S), fine away (N).
    assert horizon.is_below_floor(180, 15, physical, glow_mask) is True
    assert horizon.is_below_floor(0, 15, physical, glow_mask) is False


# ── data loading degrades gracefully ───────────────────────────────────────────

def test_load_towns_absent_file_returns_empty(tmp_path):
    assert glow.load_towns(tmp_path / "nope.tsv.gz") == []


def test_glow_mask_text_roundtrips_through_horizon(tmp_path):
    mask = glow.build_glow_floor(40.0, -105.0,
                                 [glow.Town("Metro", 39.7, -105.0, 900_000)])
    p = tmp_path / "g.hrz"
    p.write_text(glow.glow_mask_text(mask), encoding="utf-8")
    reloaded = horizon.load_mask(p)
    # same floor toward the city after a write/parse round-trip
    assert _floor_at(reloaded, 180) == pytest.approx(_floor_at(mask, 180), abs=0.5)


# ── persistence round-trip through planning_config ─────────────────────────────

def test_compute_site_glow_and_write(tmp_path, monkeypatch):
    from m110 import config, planning_config as pc
    d = tmp_path / "profiles"
    d.mkdir()
    monkeypatch.setattr(config, "PROFILES_DIR", d)
    towns = [glow.Town("Metro", 39.6, -105.0, 1_500_000)]      # due south of the site
    bb, nb, n = glow.compute_site_glow(40.0, -105.0, radius_mi=50, bortle=5, towns=towns)
    assert n == 1
    assert _floor_at(nb, 180) < _floor_at(bb, 180)             # narrowband softer
    fbb, fnb = glow.write_glow_masks("home", bb, nb)
    assert (d / fbb).is_file() and (d / fnb).is_file()
    assert fbb == "home.glow.hrz"

    # a Site pointed at those masks resolves + composes through horizon
    site = pc.Site(name="Home", glow_mask=fbb, glow_mask_narrowband=fnb, profiles_dir=d)
    m = horizon.load_mask(site.glow_path())
    assert horizon.horizon_alt(180, m) > 15                    # glow toward the city
    assert horizon.horizon_alt(0, m) < 2                       # open away from it


def test_local_town_does_not_make_a_spurious_dome():
    """A town at (essentially) the observer's own location has no meaningful bearing
    and washes the whole sky, not one azimuth — it must not create a directional
    dome (that all-sky glow is the Bortle anchor's job)."""
    obs = (40.015, -105.27)
    towns = [glow.Town("HomeTown", 40.015, -105.27, 108_000)]   # right on top of us
    mask = glow.build_glow_floor(*obs, towns)
    assert all(alt == 0 for _, alt in mask)                     # no spurious dome
