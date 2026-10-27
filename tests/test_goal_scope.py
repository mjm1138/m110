"""Goal-list telescope scope and per-model ranking (#184, PR 2)."""
import json
from datetime import date

import pytest

from m110 import config, goals, integration_goals as ig, prioritize
from m110.build_derived import build_goals
from m110.prioritize import GOAL_BASE, TargetContext, Weights
from tests._helpers import seed_root

S50, S30 = "seestar_s50", "seestar_s30"


@pytest.fixture
def store(tmp_path, monkeypatch):
    return seed_root(tmp_path, monkeypatch)


# ── goals.toml ───────────────────────────────────────────────────────────────

def test_scope_round_trips_and_survives_other_writes(store):
    assert goals.goal_scope("messier") is None                 # default: any telescope
    goals.set_goal_scope("messier", S30)
    gid = goals.create_custom_goal("Draco Messier", ["m1", "m13"])
    goals.set_goal_scope(gid, "draco")
    goals.set_active_goals(["messier", gid])                   # a rewrite keeps [scope]
    goals.edit_custom_goal(gid, name="New scope Messier")
    assert goals.scopes() == {"messier": S30, gid: "draco"}
    by_id = {g["id"]: g for g in goals.list_goals()}
    assert by_id["messier"]["scope"] == S30 and by_id["caldwell"]["scope"] is None
    goals.delete_custom_goal(gid)                              # its scope goes with it
    goals.set_goal_scope("messier", None)
    assert goals.scopes() == {}


def test_a_malformed_scope_table_reads_as_any(store):
    config.GOALS_TOML.write_text('active = ["messier"]\nscope = "oops"\n', encoding="utf-8")
    assert goals.scopes() == {} and goals.goal_scope("messier") is None


# ── progress as a scoped goal sees it ────────────────────────────────────────

def _entry(by_model):
    status, progress, model = "initial", 0.0, None
    best = ig.rollup(by_model)
    if best:
        model, e = best
        status, progress = e["status"], e["fraction"]
    return {"integration_min": sum(e["integration_min"] for e in by_model.values()),
            "status": status, "progress": progress, "progress_model": model,
            "by_model": by_model}


def _m(minutes, goal=240):
    return {"integration_min": minutes, "goal_min": goal, "goal_source": "default",
            "fraction": ig.fraction(minutes, goal), "status": ig.state(minutes, goal)}


BY_SLUG = {
    "m31": _entry({S50: _m(300)}),                 # deep on the S50 only
    "m51": _entry({S50: _m(30), S30: _m(250)}),    # deep on the S30
    "m13": _entry({S30: _m(100, goal=90)}),        # deep on the S30
}


def test_scoped_totals_keeps_only_that_models_captures():
    assert goals.scoped_totals(BY_SLUG, None) is BY_SLUG
    s30 = goals.scoped_totals(BY_SLUG, S30)
    assert set(s30) == {"m51", "m13"}
    assert s30["m51"]["integration_min"] == 250 and s30["m51"]["status"] == "deep_stack"
    s50 = goals.scoped_totals(BY_SLUG, S50)
    assert s50["m51"]["status"] == "initial"        # 30/240 on the S50


def test_build_goals_counts_only_the_scoped_telescope(store):
    gid = goals.create_custom_goal("Trio", ["m31", "m51", "m13"])
    any_scope = build_goals({"by_slug": BY_SLUG}, [gid])[0]
    assert (any_scope["scope"], any_scope["captured"], any_scope["deep"]) == (None, 3, 3)
    goals.set_goal_scope(gid, S50)
    s50 = build_goals({"by_slug": BY_SLUG}, [gid])[0]
    assert (s50["scope"], s50["captured"], s50["deep"]) == (S50, 2, 1)
    assert [i["slug"] for i in s50["in_progress"]] == ["m51"]


# ── ranking per telescope model ──────────────────────────────────────────────

OBS = {"observable": True, "transit_alt": 60.0, "hours_clear": 4.0,
       "nights_to_close": 10}


def _ctx(scopes=(), by_model=None, in_goal=False):
    return TargetContext("m31", "galaxy", sum((by_model or {}).values()), in_goal, OBS,
                         None, None, by_model, tuple(scopes))


def _score(ctx, model, goals_=None):
    return prioritize.score_target(ctx, Weights(), prioritize.STRATEGY_CAPTURE,
                                   model, goals_ or {})


def test_each_telescope_is_its_own_campaign_outside_any_goal(store):
    ctx = _ctx(by_model={S50: 300.0})                # deep on the S50
    on_s30 = _score(ctx, S30)
    assert on_s30["integration_min"] == 0 and on_s30["progress_model"] == S30
    assert on_s30["factors"]["urgency"] > 0          # still work to do on the S30
    on_s50 = _score(ctx, S50)
    assert on_s50["factors"]["urgency"] == 0         # done on the S50


def test_an_any_telescope_goal_is_satisfied_by_any_telescope(store):
    ctx = _ctx(scopes=["any"], by_model={S50: 300.0, S30: 10.0})
    on_s30 = _score(ctx, S30)
    assert on_s30["progress_model"] == S50 and on_s30["factors"]["urgency"] == 0
    assert on_s30["factors"]["goal"] == 1.0


def test_a_goal_scoped_to_the_telescope_wins(store):
    ctx = _ctx(scopes=["any", S30], by_model={S50: 300.0, S30: 10.0})
    on_s30 = _score(ctx, S30)
    assert on_s30["progress_model"] == S30 and on_s30["integration_min"] == 10
    assert on_s30["factors"]["urgency"] > 0


def test_the_goal_boost_applies_only_to_goals_for_that_telescope(store):
    ctx = _ctx(scopes=[S30], by_model={})
    assert _score(ctx, S30)["factors"]["goal"] == 1.0
    assert _score(ctx, S50)["factors"]["goal"] == GOAL_BASE


def test_a_users_goal_moves_the_ranking(store):
    ctx = _ctx(by_model={S50: 240.0})
    assert _score(ctx, S50)["factors"]["urgency"] == 0           # 240 = default goal
    row = _score(ctx, S50, {"m31": {S50: {"min": 480.0}}})
    assert row["goal_min"] == 480 and row["factors"]["urgency"] > 0


def test_a_legacy_context_still_ranks_sensibly(store):
    """Cached before scopes/by_model existed: in a goal = any telescope, and its
    total minutes are read as the active telescope's."""
    legacy = TargetContext("m31", "galaxy", 300.0, True, OBS)
    row = _score(legacy, S30)
    assert row["factors"]["goal"] == 1.0 and row["integration_min"] == 300
    # no model → the old whole-library basis, unchanged
    assert prioritize.score_target(legacy, Weights(), "capture")["progress_model"] is None


def test_rank_for_active_ranks_for_the_planning_telescope(store, monkeypatch):
    done_s50 = TargetContext("m31", "galaxy", 300.0, False, OBS, None, None, {S50: 300.0})
    new = TargetContext("m33", "galaxy", 0.0, False, OBS, None, None, {})
    monkeypatch.setattr("m110.planning_config.active_device_key", lambda: "S50_aaaa0001")
    rows = prioritize.rank_for_active([done_s50, new], Weights(), "capture", {})
    assert [r["slug"] for r in rows] == ["m33", "m31"]
    monkeypatch.setattr("m110.planning_config.active_device_key", lambda: "S30_bbbb0002")
    rows = prioritize.rank_for_active([done_s50, new], Weights(), "capture", {})
    assert {r["slug"]: r["progress_model"] for r in rows} == {"m31": S30, "m33": S30}
    assert rows[0]["score"] == rows[1]["score"]       # both brand new for the S30


# ── the context cache ────────────────────────────────────────────────────────

def test_contexts_round_trip_and_an_old_cache_is_stale(store):
    ctx = _ctx(scopes=["any", S30], by_model={S50: 12.0})
    prioritize.write_contexts([ctx])
    assert not prioritize.is_stale()
    back = prioritize.load_contexts()[0]
    assert back.integration_by_model == {S50: 12.0} and back.goal_scopes == ("any", S30)
    path = config.DERIVED_DIR / "prioritized.json"
    data = json.loads(path.read_text())
    data.pop("v")                                       # written before #184
    path.write_text(json.dumps(data))
    assert prioritize.is_stale(date.today())
