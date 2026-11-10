"""Integration goals per object and telescope model (#184): storage, defaults, state."""
import pytest

from m110 import config, devices, integration_goals as ig
from m110.build_derived import deep_threshold
from m110.planning_config import DEVICE_PRESETS
from tests._helpers import seed_root


@pytest.fixture
def store(tmp_path, monkeypatch):
    return seed_root(tmp_path, monkeypatch)


def test_empty_when_absent_and_lazily_created(store):
    assert ig.load() == {}
    assert not config.INTEGRATION_GOALS_TOML.exists()


def test_round_trip_keeps_reasons_and_other_goals(store):
    ig.set_goal("m77", "seestar_s50", 420, "outer disk SNR ~5–7 per 12″")
    ig.set_goal("m77", "dwarf_3", 300)
    ig.set_goal('odd "slug"', "seestar_s30", 90.5)
    assert ig.load() == {
        "m77": {"seestar_s50": {"min": 420.0, "reason": "outer disk SNR ~5–7 per 12″"},
                "dwarf_3": {"min": 300.0}},
        'odd "slug"': {"seestar_s30": {"min": 90.5}},
    }
    ig.clear_goal("m77", "dwarf_3")
    ig.clear_goal("m77", "dwarf_3")                     # idempotent
    assert set(ig.load()["m77"]) == {"seestar_s50"}
    ig.set_goal('odd "slug"', "seestar_s30", 0)        # non-positive clears
    assert 'odd "slug"' not in ig.load()


def test_a_malformed_file_reads_as_empty(store):
    config.INTEGRATION_GOALS_TOML.write_text("[goals\nnot toml", encoding="utf-8")
    assert ig.load() == {}
    config.INTEGRATION_GOALS_TOML.write_text(
        '[goals."m1"]\nseestar_s50 = { min = -5 }\ndwarf_3 = { min = "x" }\n'
        'dwarf_mini = { min = true }\nseestar_s30 = { min = 60 }\n', encoding="utf-8")
    assert ig.load() == {"m1": {"seestar_s30": {"min": 60.0}}}


def test_every_preset_has_an_f_ratio():
    for key, dev in DEVICE_PRESETS.items():
        assert dev.f_ratio, key
    assert DEVICE_PRESETS["seestar_s50"].f_ratio == pytest.approx(5.0)


def test_speed_factor_scales_by_f_ratio_squared(store):
    assert ig.speed_factor("seestar_s50") == (1.0, True)
    factor, calibrated = ig.speed_factor("dwarf_3")              # f/4.29
    assert calibrated and factor == pytest.approx((150 / 35 / 5) ** 2)
    factor, _ = ig.speed_factor("seestar_s30_pro")               # f/5.33 — slower
    assert factor > 1.0


def test_a_telescope_without_optics_is_uncalibrated_until_the_user_enters_them(store):
    assert ig.speed_factor("MyScope") == (1.0, False)
    assert ig.speed_factor("unknown") == (1.0, False)
    devices.save_device("MyScope", optics={"aperture_mm": 61.0, "focal_length_mm": 274.5})
    factor, calibrated = ig.speed_factor("MyScope")
    assert calibrated and factor == pytest.approx((274.5 / 61 / 5) ** 2)


def test_default_goal_rounds_to_five_minutes(store):
    assert ig.default_goal("galaxy", "seestar_s50") == deep_threshold("galaxy") == 240
    dwarf = ig.default_goal("galaxy", "dwarf_3")
    assert dwarf % ig.DEFAULT_ROUND_MIN == 0
    assert dwarf == pytest.approx(240 * (150 / 35 / 5) ** 2, abs=2.5)
    assert ig.default_goal("galaxy", "MyScope") == 240            # uncalibrated → 1.0


def test_resolve_prefers_the_users_goal(store):
    assert ig.resolve("m77", "galaxy", "seestar_s50") == (240.0, ig.SOURCE_DEFAULT)
    ig.set_goal("m77", "seestar_s50", 420)
    assert ig.resolve("m77", "galaxy", "seestar_s50") == (420.0, ig.SOURCE_USER)
    # another model of the same object keeps its own default
    assert ig.resolve("m77", "galaxy", "seestar_s30")[1] == ig.SOURCE_DEFAULT


@pytest.mark.parametrize("minutes,expected", [
    (0, ig.INITIAL), (24.9, ig.INITIAL), (25, ig.IN_PROGRESS),
    (99.9, ig.IN_PROGRESS), (100, ig.DEEP), (150, ig.DEEP),
])
def test_state_thresholds(minutes, expected):
    assert ig.state(minutes, 100) == expected


def test_rollup_picks_the_most_advanced_model():
    assert ig.rollup({}) is None
    by_model = {
        "seestar_s30": {"status": ig.IN_PROGRESS, "fraction": 0.4},
        "seestar_s50": {"status": ig.IN_PROGRESS, "fraction": 0.6},
        "dwarf_3": {"status": ig.INITIAL, "fraction": 0.2},
    }
    assert ig.rollup(by_model)[0] == "seestar_s50"             # higher fraction wins a tie
    by_model["dwarf_3"] = {"status": ig.DEEP, "fraction": 1.0}
    assert ig.rollup(by_model)[0] == "dwarf_3"                 # state outranks fraction


def test_model_key_pools_units_of_one_model(store):
    assert ig.model_key("S50_aaaa0001") == ig.model_key("S50_bbbb0002") == "seestar_s50"
    assert ig.model_key("MyScope") == "MyScope"
    assert ig.model_key(None) == "unknown"
    devices.save_device("MyScope", preset="dwarf_3")
    assert ig.model_key("MyScope") == "dwarf_3"
    assert ig.model_label("dwarf_3") == "DwarfLab Dwarf 3"


# ── build_totals: graded per model ───────────────────────────────────────────

def _session(folder, slugs, minutes, device, date="2026-03-13"):
    return {"date": date, "object_dir": folder, "slugs": slugs, "frames": 10,
            "exposure_s": 30, "filter": "LP", "integration_min": minutes,
            "device": device}


def test_status_is_graded_per_model_and_rolled_up_to_the_most_advanced(store):
    from m110.build_derived import build_totals
    catalog = {"m77": {"id": "M77", "type": "galaxy"}}
    sessions = [
        _session("M77", ["m77"], 150, "S50_aaaa0001"),
        _session("M77", ["m77"], 60, "S50_bbbb0002", "2026-03-14"),   # same model: pooled
        _session("M77", ["m77"], 30, "S30_cccc0003"),
    ]
    totals = build_totals(catalog, sessions)
    m77 = totals["by_slug"]["m77"]
    s50 = m77["by_model"]["seestar_s50"]
    assert s50["integration_min"] == 210 and s50["devices"] == ["S50_aaaa0001",
                                                                 "S50_bbbb0002"]
    assert (s50["goal_min"], s50["goal_source"]) == (240, "default")
    assert s50["status"] == "in_progress" and s50["fraction"] == pytest.approx(0.875)
    assert m77["by_model"]["seestar_s30"]["status"] == "initial"     # 30 / 240
    # 240 min summed across both models would have read "deep"; per model it isn't
    assert m77["integration_min"] == 240
    assert (m77["status"], m77["progress_model"]) == ("in_progress", "seestar_s50")
    assert m77["progress"] == pytest.approx(0.875)
    # the by_device split is unchanged
    assert set(m77["by_device"]) == {"S50_aaaa0001", "S50_bbbb0002", "S30_cccc0003"}

    ig.set_goal("m77", "seestar_s50", 420)
    m77 = build_totals(catalog, sessions)["by_slug"]["m77"]
    assert m77["by_model"]["seestar_s50"]["goal_source"] == "user"
    assert m77["progress"] == pytest.approx(0.5)
    ig.set_goal("m77", "seestar_s30", 30)
    m77 = build_totals(catalog, sessions)["by_slug"]["m77"]
    assert (m77["status"], m77["progress_model"]) == ("deep_stack", "seestar_s30")


def test_a_folder_uses_its_most_demanding_member_per_model(store):
    from m110.build_derived import build_totals
    catalog = {"m81": {"id": "M81", "type": "galaxy"},
               "m82": {"id": "M82", "type": "galaxy"}}
    sessions = [_session("M81 M82", ["m81", "m82"], 250, "S50_aaaa0001")]
    folder = build_totals(catalog, sessions)["by_folder"]["M81 M82"]
    assert folder["status"] == "deep_stack"                          # 250 ≥ 240
    ig.set_goal("m82", "seestar_s50", 300)
    folder = build_totals(catalog, sessions)["by_folder"]["M81 M82"]
    s50 = folder["by_model"]["seestar_s50"]
    assert (s50["goal_min"], s50["goal_source"], s50["status"]) == (300, "user",
                                                                    "in_progress")


def test_a_capture_with_no_sessions_reads_initial(store):
    from m110.build_derived import _status_fields
    assert _status_fields({}) == {"status": "initial", "progress": 0.0,
                                  "progress_model": None}


def test_progress_lines_and_the_assistant_report(store, monkeypatch):
    by_model = {
        "seestar_s30": {"integration_min": 30, "goal_min": 240, "goal_source": "default",
                        "fraction": 0.125, "status": "initial"},
        "seestar_s50": {"integration_min": 210, "goal_min": 420, "goal_source": "user",
                        "fraction": 0.5, "status": "in_progress"},
    }
    assert ig.progress_lines(by_model) == [
        "ZWO Seestar S50: 210 of 420 min (50%, your goal)",
        "ZWO Seestar S30: 30 of 240 min (12%, default goal)",
    ]
    ig.set_goal("m77", "seestar_s30", 120)
    monkeypatch.setattr("m110.planning_config.active_device_key", lambda: "S30_cccc0003")
    report = ig.capture_report("m77", "galaxy", {"by_model": by_model})
    assert report["active_model"] == "seestar_s30"
    assert (report["deep_threshold_min"], report["goal_source"]) == (120.0, "user")
    assert report["fraction_of_deep"] == 0.25
    assert [g["model"] for g in report["goals"]] == ["seestar_s30", "seestar_s50"]
    # no telescope yet → the reference S50, no progress
    monkeypatch.setattr("m110.planning_config.active_device_key", lambda: None)
    report = ig.capture_report("m31", "galaxy", {})
    assert (report["active_model"], report["fraction_of_deep"]) == ("seestar_s50", 0.0)


def test_publish_badge_matches_the_pill():
    from m110.publish.site import _status_label
    assert _status_label("in_progress", 0.62) == "62% of goal"
    assert _status_label("deep_stack") == "Deep Stack"
    assert _status_label(None) == "—"
