"""Tests for the session-planning engine (m110/planning.py).

Pure helpers run without astropy; the night-math tests exercise the real astropy
path (a core dependency). Twilight goldens match the sibling Astronomy project's
hand-derived 2026-06 Boulder plans (the default site profile is Boulder)."""
from datetime import date, datetime

import pytest

from m110 import planning


# ── pure helpers ─────────────────────────────────────────────────────────────

def test_transit_altitude():
    site = planning.Site()  # Boulder default, lat 40.015
    assert planning.transit_altitude(40.015, site) == pytest.approx(90.0)   # at the zenith
    assert planning.transit_altitude(47.20, site) == pytest.approx(82.8, abs=0.1)  # M51
    assert planning.transit_altitude(-34.84, site) == pytest.approx(15.1, abs=0.2)  # M7, low


def test_radec_resolves_slug_and_tuple():
    assert planning._radec((10.0, 20.0)) == (10.0, 20.0)
    ra, dec = planning._radec("m51")
    assert ra == pytest.approx(202.47, abs=0.01) and dec == pytest.approx(47.20, abs=0.01)


def test_radec_unknown_is_none():
    assert planning._radec("not-a-real-slug") is None


def test_observability_unresolved_target():
    out = planning.observability("not-a-real-slug", date(2026, 6, 10), planning.Site())
    assert out["observable"] is None and out["season"] == ""


# ── astropy night math ───────────────────────────────────────────────────────

def test_to_utc_handles_dst_automatically():
    site = planning.Site()
    assert planning.to_utc(datetime(2026, 6, 10, 22, 0), site).iso.startswith("2026-06-11 04:00")
    assert planning.to_utc(datetime(2026, 12, 10, 22, 0), site).iso.startswith("2026-12-11 05:00")


def test_twilight_golden_june():
    dusk, dawn = planning.twilight(2026, 6, 10, planning.Site())
    assert dusk.strftime("%H:%M") == "22:35"
    assert dawn.strftime("%H:%M") == "03:30"
    assert (dawn - dusk).total_seconds() / 3600 == pytest.approx(4.92, abs=0.1)


def test_twilight_winter_is_long():
    dusk, dawn = planning.twilight(2026, 12, 10, planning.Site())
    assert dusk.strftime("%H:%M") == "18:15"
    assert dawn.strftime("%H:%M") == "05:40"


def test_observability_well_placed_target():
    # M51 (dec +47°) is high and well placed from Boulder in June.
    out = planning.observability("m51", date(2026, 6, 10), planning.Site(),
                                 horizon_days=14, grid_days=7)
    assert out["observable"] is True
    assert out["hours_clear"] > 1.5
    assert out["transit_alt"] == pytest.approx(82.8, abs=0.2)
    assert out["nights_to_close"] is not None
    assert out["season"]  # derived window, non-empty


def test_observability_far_south_target_out():
    # M7 (dec −35°) never clears the 30° quality floor from Boulder.
    out = planning.observability("m7", date(2026, 6, 10), planning.Site(),
                                 horizon_days=14, grid_days=7)
    assert out["observable"] is False
    assert out["nights_to_close"] is None


def test_glow_floor_gates_observability(tmp_path):
    # A glow floor near the zenith blots out even an overhead target — proves the
    # gate consults the glow layer (azimuth-specificity is covered in test_horizon).
    glow = tmp_path / "glow.hrz"
    glow.write_text("0 89\n180 89\n")
    site_glow = planning.Site(glow_mask="glow.hrz", profiles_dir=tmp_path)
    site_open = planning.Site()  # no glow
    day = date(2026, 6, 10)
    assert planning.observability("m51", day, site_open,
                                  horizon_days=7, grid_days=7)["observable"] is True
    assert planning.observability("m51", day, site_glow,
                                  horizon_days=7, grid_days=7)["observable"] is False


def test_zoneinfo_resolves_without_a_system_tzdb():
    """Regression guard for issue #56 (Windows launch crash). Windows ships no system
    tz database, so `zoneinfo` must fall back to the bundled `tzdata` package — which
    means `tzdata` has to be a declared dependency (and bundled by the PyInstaller
    specs). Simulate a system with no tz db by clearing the search path; both the UTC
    anchor (`planning._UTC`, resolved at import) and a real site zone must still load."""
    import zoneinfo
    from zoneinfo import ZoneInfo
    saved = list(zoneinfo.TZPATH)
    try:
        zoneinfo.reset_tzpath([])                 # emulate Windows: no /usr/share/zoneinfo
        assert ZoneInfo("UTC") is not None        # the crash site (planning.py import)
        assert ZoneInfo("America/Denver") is not None   # site-profile localization
    finally:
        zoneinfo.reset_tzpath(saved)              # restore for the rest of the session
