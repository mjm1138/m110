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


# ── per-slot moon model (Phase 2 / BUGS #36) ─────────────────────────────────

def test_moon_impact_gates_on_moon_up():
    # Moon below the horizon → no impact, whatever the separation.
    assert planning.moon_impact(0.99, -5.0, 20.0) is None
    assert planning.moon_impact(0.99, 0.0, 20.0) is None
    # Bright moon close by: broadband suffers, narrowband is largely immune.
    assert planning.moon_impact(0.95, 40.0, 40.0, "IRCUT") == "high"
    assert planning.moon_impact(0.95, 40.0, 40.0, "LP") in ("low", "medium")
    # Thin crescent far away → negligible.
    assert planning.moon_impact(0.05, 30.0, 110.0) == "none"


def test_plan_night_moon_track_new_moon_night():
    """Jul 13 2026 (night before the Jul 14 new moon): the moon is down essentially
    all night — near-0% illum, and every entry's impact must be gated to None."""
    plan = planning.plan_night(_SITE, _DAY, ["m13"])
    moon = plan["moon"]
    assert moon["illum"] <= 0.05                         # ~new moon
    assert moon["track"], "per-slot track present"
    assert all(a <= 5 for _t, a in moon["track"])        # at/under the horizon all night
    for e in plan["entries"]:
        assert "moon_alt_at_best" in e
        if e["moon_alt_at_best"] <= 0:
            assert e["moon_impact"] is None


def test_plan_night_moon_sets_during_window():
    """Jul 18 2026 from Boulder — the review's ground-truth night: ~24–28% waxing
    crescent, up at dusk (~+5°), setting ~23:00 (prioritizer-review §5a). The old
    header claimed '0% lit, down at dusk (−17°)'."""
    day = date(2026, 7, 18)
    plan = planning.plan_night(_SITE, day, ["m107"])
    moon = plan["moon"]
    assert 0.20 <= moon["illum"] <= 0.32                 # crescent, not 0%
    assert 2.0 <= moon["alt"] <= 10.0                    # up at dusk, ~+5°
    assert moon["set_time"] is not None                  # sets inside the window…
    assert moon["set_time"].hour in (22, 23)             # …around 23:00 local
    assert moon["rise_time"] is None
    # M107 (transit 36°, under the ceiling) starts right at dusk → moon still up,
    # and the impact annotation follows the proposed START slot (Phase 3).
    e = plan["entries"][0]
    assert e["start_time"] == plan["window"][0]
    assert e["moon_alt_at_best"] > 0
    assert e["moon_impact"] in ("none", "low", "medium", "high")


# ── start-altitude ceiling (Phase 3 / BUGS #37) ──────────────────────────────

def _mk(hh, mm, alt, clear=True):
    return (datetime(2026, 7, 18, hh, mm), alt, clear)


def test_pick_start_prefers_highest_startable():
    samples = [_mk(22, 0, 60), _mk(23, 0, 75), _mk(0, 0, 85), _mk(1, 0, 74)]
    t, a, over = planning.pick_start(samples, 78.0, True)
    assert (a, over) == (75, False) and t.hour == 23    # rising-side slot, not the 85° peak


def test_pick_start_hard_ceiling_refuses_when_nothing_startable():
    samples = [_mk(23, 0, 82), _mk(0, 0, 88)]
    assert planning.pick_start(samples, 78.0, True) == (None, None, True)


def test_pick_start_soft_ceiling_falls_back_with_flag():
    samples = [_mk(23, 0, 82), _mk(0, 0, 88)]
    t, a, over = planning.pick_start(samples, 80.0, False)
    assert (a, over) == (88, True)                       # annotated, not refused


def test_pick_start_ignores_unclear_and_no_ceiling():
    samples = [_mk(22, 0, 76, clear=False), _mk(23, 0, 70)]
    t, a, over = planning.pick_start(samples, 78.0, True)
    assert a == 70                                       # obstructed 76° sample skipped
    t, a, over = planning.pick_start(samples, None, True)
    assert a == 70 and over is False                     # no ceiling → best clear


def test_device_presets_ceiling_kinds():
    from m110.planning_config import DEVICE_PRESETS
    for k in ("seestar_s50", "seestar_s30", "seestar_s30_pro"):
        d = DEVICE_PRESETS[k]
        assert d.start_alt_ceiling_deg == 78.0 and d.ceiling_is_hard
    for k in ("dwarf_3", "dwarf_mini"):
        d = DEVICE_PRESETS[k]
        assert d.start_alt_ceiling_deg == 80.0 and not d.ceiling_is_hard


def test_high_transit_target_gets_startable_slot():
    """The review's 5c case: M29 transits ~88° from lat 40 on Jul 18 — the Seestar
    app would reject a start there. The proposed start must be ≤ the ceiling, inside
    the dark window, and distinct from transit."""
    day = date(2026, 7, 18)
    tr = planning.night_track("m29", day, _SITE)         # default device = S50, hard 78°
    assert tr["transit_alt"] > 80                        # the trap the old plan fell into
    assert tr["start_time"] is not None
    # profile ceiling 78° minus the planning margin → practical ~75°
    assert tr["start_alt"] <= 78.0 - planning.START_CEILING_MARGIN_DEG
    assert tr["over_ceiling"] is False
    assert tr["start_time"] != tr["transit_time"]
    # plan_night surfaces the same slot + anchors the moon annotation to it
    plan = planning.plan_night(_SITE, day, ["m29"])
    e = plan["entries"][0]
    assert e["start_alt"] <= 75.0 and e["start_time"] is not None
