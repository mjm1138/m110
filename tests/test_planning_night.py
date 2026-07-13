"""Tonight-plan engine (planning.night_track / plan_night) — astropy, fixture site."""
from datetime import date, datetime

import pytest

from m110 import planning
from m110.planning_config import Site

_SITE = Site(name="Home", latitude_deg=40.015, longitude_deg=-105.27,
             elevation_m=1655, timezone="America/Denver")
_DAY = date(2026, 7, 13)          # a real July night from Boulder


def test_night_track_transit_and_window():
    tr = planning.night_track("m13", _DAY, _SITE)      # M13 globular, high in summer
    assert tr is not None
    assert isinstance(tr["transit_time"], datetime)
    assert tr["transit_alt"] > 80                       # near-overhead from lat 40
    # up-window is within the dark window and non-empty
    assert tr["up_start"] is not None and tr["up_end"] > tr["up_start"]
    assert 0 <= tr["moon_sep_deg"] <= 180
    assert tr["samples"] and all(len(s) == 3 for s in tr["samples"])   # (time, alt, clear)


def test_night_track_none_for_unresolvable_target():
    assert planning.night_track("not-a-real-object", _DAY, _SITE) is None


def test_plan_night_orders_by_setting_soonest():
    plan = planning.plan_night(_SITE, _DAY, ["m13", "m81", "m31"],
                               scores={"m13": 5.0})
    dusk, dawn = plan["window"]
    assert dusk and dawn and dusk < dawn
    assert plan["moon"]["illum"] is not None
    ends = [e["up_end"] for e in plan["entries"]]
    assert ends == sorted(ends)                          # auto = sets-soonest first
    # M81 (a spring galaxy, setting in the west in July) should be early in the order
    slugs = [e["slug"] for e in plan["entries"]]
    assert slugs.index("m81") < slugs.index("m13")


def test_plan_night_drops_targets_not_up():
    # A far-southern target (dec very negative) never clears the floor from lat 40.
    plan = planning.plan_night(_SITE, _DAY, [(0.0, -80.0), "m13"])
    slugs = [e["slug"] for e in plan["entries"]]
    assert "m13" in slugs
    assert len(plan["entries"]) == 1                     # the southern one is dropped


def test_plan_night_manual_preserves_order():
    plan = planning.plan_night(_SITE, _DAY, ["m13", "m81"], order="manual")
    assert [e["slug"] for e in plan["entries"]] == ["m13", "m81"]
