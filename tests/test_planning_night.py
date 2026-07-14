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


# ── night sequencer (Phase 4 / BUGS #40–42) ──────────────────────────────────

def _entry(slug, up_start, up_end, alt=50.0, sep=90.0, step=10):
    """Synthetic night_track entry: clear at `alt` across [up_start, up_end]."""
    n = int((up_end - up_start).total_seconds() / 60 / step) + 1
    samples = [(up_start + timedelta(minutes=step * i), alt, True) for i in range(n)]
    return {"slug": slug, "up_start": up_start, "up_end": up_end,
            "moon_sep_deg": sep, "samples": samples,
            "transit_time": up_start, "transit_alt": alt, "best_alt": alt,
            "start_time": up_start, "start_alt": alt, "over_ceiling": False}


from datetime import timedelta


def _synthetic_plan(entries, dusk=None, dawn=None, ceiling=75.0, hard=True,
                    moon_track=None, illum=0.3):
    dusk = dusk or datetime(2026, 7, 18, 22, 25)
    dawn = dawn or datetime(2026, 7, 19, 3, 55)
    return {"window": (dusk, dawn), "entries": entries,
            "start_ceiling_deg": ceiling, "ceiling_is_hard": hard,
            "moon": {"illum": illum, "alt": 5.0, "set_time": None,
                     "rise_time": None, "track": moon_track or []}}


def test_sequence_non_overlapping_ticked_and_chained():
    """#40/#41 core: default 4 slots, 10-min aligned, object N+1 starts at N's end."""
    d0 = datetime(2026, 7, 18, 22, 25)
    d1 = datetime(2026, 7, 19, 3, 55)
    entries = [_entry(f"t{i}", d0, d1) for i in range(6)]
    plan = _synthetic_plan(entries)
    slots = planning.sequence_plan(plan, scores={f"t{i}": 10 - i for i in range(6)})
    assert len(slots) == 4                              # default count
    assert slots[0]["start"] == datetime(2026, 7, 18, 22, 30)   # dusk 22:25 → 22:30
    for s in slots:
        assert s["start"].minute % 10 == 0 and s["duration_min"] % 10 == 0
    for a, b in zip(slots, slots[1:]):
        assert b["start"] == a["end"]                   # contiguous, non-overlapping
    assert [s["slug"] for s in slots] == ["t0", "t1", "t2", "t3"]   # priority order
    assert slots[-1]["end"] <= datetime(2026, 7, 19, 3, 50)


def test_sequence_tie_goes_to_the_setter():
    """#40.4: equal priority in a window → the one closer to setting goes first."""
    d0 = datetime(2026, 7, 18, 22, 25)
    early = _entry("sets-early", d0, datetime(2026, 7, 19, 0, 30))
    late = _entry("sets-late", d0, datetime(2026, 7, 19, 3, 55))
    plan = _synthetic_plan([late, early])
    slots = planning.sequence_plan(plan, count=2,
                                   scores={"sets-early": 5.0, "sets-late": 5.0})
    assert [s["slug"] for s in slots] == ["sets-early", "sets-late"]


def test_sequence_deep_remaining_caps_duration():
    """#40.1: a target that reaches deep-stack sooner gets a shorter slot; the next
    object starts at its (earlier) end."""
    d0 = datetime(2026, 7, 18, 22, 25)
    d1 = datetime(2026, 7, 19, 3, 55)
    plan = _synthetic_plan([_entry("nearly-deep", d0, d1), _entry("new", d0, d1)])
    slots = planning.sequence_plan(plan, count=2,
                                   scores={"nearly-deep": 9, "new": 1},
                                   deep_remaining={"nearly-deep": 35.0, "new": 240.0})
    assert slots[0]["slug"] == "nearly-deep"
    assert slots[0]["duration_min"] == 40               # 35 min → next 10-min tick
    assert slots[1]["start"] == slots[0]["end"]


def test_sequence_waits_for_a_startable_target():
    """Nothing startable right at dark → the schedule starts when something rises."""
    dusk = datetime(2026, 7, 18, 22, 25)
    dawn = datetime(2026, 7, 19, 3, 55)
    rises = _entry("later", datetime(2026, 7, 19, 0, 5), dawn)
    plan = _synthetic_plan([rises])
    slots = planning.sequence_plan(plan, count=1, scores={"later": 5.0})
    assert slots and slots[0]["start"] >= datetime(2026, 7, 19, 0, 0)


def test_sequence_hard_ceiling_skips_over_ceiling_ticks():
    """A target above a hard ceiling at dark isn't chosen until it descends; a soft
    ceiling allows it flagged ^."""
    dusk = datetime(2026, 7, 18, 22, 25)
    dawn = datetime(2026, 7, 19, 3, 55)
    n = int((dawn - dusk).total_seconds() / 60 / 10) + 1
    # high early (80°), descends below the 75° ceiling from 00:05 on
    samples = [(dusk + timedelta(minutes=10 * i),
                80.0 if (dusk + timedelta(minutes=10 * i)) < datetime(2026, 7, 19, 0, 5)
                else 70.0, True) for i in range(n)]
    high = {"slug": "high", "up_start": dusk, "up_end": dawn, "moon_sep_deg": 90.0,
            "samples": samples, "transit_time": dusk, "transit_alt": 80.0,
            "best_alt": 80.0, "start_time": dusk, "start_alt": 70.0,
            "over_ceiling": False}
    hard_slots = planning.sequence_plan(_synthetic_plan([high], hard=True),
                                        count=1, scores={"high": 5.0})
    assert hard_slots[0]["start"] >= datetime(2026, 7, 19, 0, 0)
    assert hard_slots[0]["alt_start"] <= 75.0 and not hard_slots[0]["over_ceiling"]
    soft_slots = planning.sequence_plan(_synthetic_plan([high], hard=False),
                                        count=1, scores={"high": 5.0})
    assert soft_slots[0]["start"] == datetime(2026, 7, 18, 22, 30)
    assert soft_slots[0]["over_ceiling"] is True


def test_sequence_forced_order_and_moon_at_slot():
    """forced_order (the UI's manual reorder) wins over scores; moon impact is
    evaluated at each slot's start from the track."""
    d0 = datetime(2026, 7, 18, 22, 25)
    d1 = datetime(2026, 7, 19, 3, 55)
    entries = [_entry("a", d0, d1, sep=30.0), _entry("b", d0, d1, sep=30.0)]
    # moon up until 23:05, then down
    track = [(d0 + timedelta(minutes=10 * i),
              5.0 if (d0 + timedelta(minutes=10 * i)) < datetime(2026, 7, 18, 23, 5)
              else -10.0) for i in range(34)]
    plan = _synthetic_plan(entries, moon_track=track, illum=0.9)
    slots = planning.sequence_plan(plan, count=2, scores={"a": 1.0, "b": 9.0},
                                   forced_order=["a", "b"])
    assert [s["slug"] for s in slots] == ["a", "b"]     # forced, not score order
    assert slots[0]["moon_impact"] in ("low", "medium", "high")   # moon up at 22:30
    assert slots[1]["moon_impact"] is None              # moon set before slot 2
