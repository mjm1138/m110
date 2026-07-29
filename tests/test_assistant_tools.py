"""Behaviour of the individual read tools.

test_assistant_registry.py proves the *contract* (schema legality, JSON safety,
read-only). This file proves the tools return the right answers, against a store
with a real capture in it.
"""
import pytest

from m110 import config, pins, prioritize
from m110.assistant import registry, tools  # noqa: F401  (import populates registry)
from tests._helpers import seed_capture, seed_root


@pytest.fixture
def captured(tmp_path, monkeypatch):
    """A store with one captured Messier object and derived data built."""
    root = seed_root(tmp_path, monkeypatch)
    slug, target = seed_capture(root)
    return root, slug, target


def call(_tool, **args):
    # `_tool` is underscore-prefixed so it can't collide with a tool's own
    # parameter names (saved_plans takes `name`).
    return registry.call(_tool, args)


# ── get_store_overview ───────────────────────────────────────────────────────

def test_overview_reports_counts_and_staleness(captured):
    _, slug, _ = captured
    out = call("get_store_overview")
    assert out["derived_available"] is True
    assert out["object_count"] >= 1
    # No contexts were ever computed, so the ranking must self-report as stale.
    assert out["ranking"]["context_stale"] is True
    assert out["ranking"]["note"]


def test_overview_degrades_before_a_refresh(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    out = call("get_store_overview")
    assert out["derived_available"] is False
    assert "refresh" in out["note"].lower()


# ── list_objects ─────────────────────────────────────────────────────────────

def test_list_objects_finds_by_designation(captured):
    _, slug, _ = captured
    out = call("list_objects", query=slug)
    assert out["total_matched"] >= 1
    assert any(r["slug"] == slug for r in out["objects"])


def test_list_objects_captured_only_and_limit(captured):
    _, slug, _ = captured
    assert all(r["integration_min"] > 0
               for r in call("list_objects", captured_only=True)["objects"])
    out = call("list_objects", limit=1)
    assert out["returned"] == 1 and out["total_matched"] >= 1


def test_list_objects_reports_total_beyond_the_limit(captured):
    out = call("list_objects", limit=1)
    assert out["total_matched"] >= out["returned"]


# ── get_object ───────────────────────────────────────────────────────────────

def test_get_object_returns_capture_and_threshold(captured):
    _, slug, _ = captured
    out = call("get_object", slug=slug)
    assert out["slug"] == slug
    assert out["identifiers"]
    assert out["capture"]["integration_min"] > 0
    assert out["capture"]["frames"] >= 1
    # Type-aware deep threshold, plus how far along this object is.
    assert out["capture"]["deep_threshold_min"] > 0
    assert 0.0 <= out["capture"]["fraction_of_deep"] <= 1.0
    assert out["sessions"], "the seeded light frame should produce a session"


def test_get_object_is_case_insensitive(captured):
    _, slug, _ = captured
    assert call("get_object", slug=slug.upper())["slug"] == slug


def test_get_object_unknown_slug_is_a_tool_error_not_a_crash(captured):
    with pytest.raises(registry.ToolError) as e:
        call("get_object", slug="not-a-real-object")
    assert "list_objects" in str(e.value)      # tells the model how to recover


def test_get_object_can_omit_the_heavy_sections(captured):
    _, slug, _ = captured
    out = call("get_object", slug=slug, include_journal=False, include_images=False)
    assert "journal" not in out and "images" not in out


def test_get_object_reflects_pin_state(captured):
    _, slug, _ = captured
    assert call("get_object", slug=slug)["pin_state"] is None
    pins.set_state(slug, "pin")                 # a WRITE, done by the test not the tool
    assert call("get_object", slug=slug)["pin_state"] == "pin"


# ── rank_targets ─────────────────────────────────────────────────────────────

def test_rank_targets_without_contexts_explains_itself(captured):
    out = call("rank_targets")
    assert out["rows"] == []
    assert out["context_stale"] is True
    # The server can't fix this itself — it must say so rather than appear broken.
    assert "read-only" in out["note"].lower()


def test_rank_targets_ranks_cached_contexts(captured):
    _, slug, _ = captured
    prioritize.write_contexts([                 # a WRITE, done by the test
        prioritize.TargetContext(slug, "galaxy", 30.0, True,
                                 {"observable": True, "transit_alt": 70.0,
                                  "hours_clear": 4.0, "nights_to_close": 40,
                                  "season": "spring"}, 7.9, "28x27"),
        prioritize.TargetContext("m13", "globular cluster", 0.0, True,
                                 {"observable": True, "transit_alt": 80.0,
                                  "hours_clear": 5.0, "nights_to_close": 90,
                                  "season": "summer"}, 5.8, "20x20"),
    ])
    out = call("rank_targets")
    assert out["total_ranked"] == 2
    assert [r["rank"] for r in out["rows"]] == [1, 2]
    # The factor breakdown is what "explain the numbers" cites.
    assert set(out["rows"][0]["factors"]) >= {"goal", "urgency", "completion", "tonight"}
    assert out["scoring_note"]


def test_rank_targets_honours_pins_and_visibility(captured):
    _, slug, _ = captured
    prioritize.write_contexts([
        prioritize.TargetContext(slug, "galaxy", 300.0, True,
                                 {"observable": True, "transit_alt": 20.0,
                                  "hours_clear": 1.0, "nights_to_close": 200}, None, None),
        prioritize.TargetContext("m13", "globular cluster", 0.0, True,
                                 {"observable": False, "transit_alt": 80.0,
                                  "hours_clear": 5.0, "nights_to_close": 5}, None, None),
    ])
    pins.set_state(slug, "pin")
    assert call("rank_targets")["rows"][0]["slug"] == slug   # pinned floats to the top

    # m13 is explicitly not observable, so the tonight view drops it.
    assert all(r["slug"] != "m13"
               for r in call("rank_targets", visible_tonight_only=True)["rows"])


def test_rank_targets_strategy_override_changes_scores(captured):
    _, slug, _ = captured
    # Half of the galaxy deep threshold (240 min), where the two strategies are
    # furthest apart: capture-many gives 1-p = 0.5, go-deep peaks at 4p(1-p) = 1.0.
    # (Avoid p = 0.25 — the curves cross there and the scores are identical.)
    prioritize.write_contexts([
        prioritize.TargetContext(slug, "galaxy", 120.0, True,
                                 {"observable": True, "transit_alt": 60.0,
                                  "hours_clear": 3.0, "nights_to_close": 50}, None, None),
    ])
    capture = call("rank_targets", strategy="capture")["rows"][0]
    deep = call("rank_targets", strategy="deep")["rows"][0]
    assert deep["factors"]["completion"] > capture["factors"]["completion"]
    assert deep["score"] > capture["score"]


# ── get_processing_state ─────────────────────────────────────────────────────

def test_processing_state_lists_folders(captured):
    _, _, target = captured
    out = call("get_processing_state")
    assert any(f["folder"] == target for f in out["folders"])
    assert "counts" in out


def test_processing_state_for_one_target(captured):
    _, _, target = captured
    out = call("get_processing_state", target=target)
    assert out["folder"]["folder"] == target
    assert out["folder"]["status"]


def test_processing_state_unknown_target_lists_the_real_ones(captured):
    _, _, target = captured
    with pytest.raises(registry.ToolError) as e:
        call("get_processing_state", target="Nonexistent")
    assert target in str(e.value)


def test_processing_state_filters_by_status(captured):
    out = call("get_processing_state", status="not_processed")
    assert all(f["status"] == "not_processed" for f in out["folders"])


# ── saved_plans ──────────────────────────────────────────────────────────────

def _write_plan(name, text):
    config.PLANS_DIR.mkdir(parents=True, exist_ok=True)
    (config.PLANS_DIR / name).write_text(text, encoding="utf-8")


def test_saved_plans_lists_then_reads(captured):
    _write_plan("2026-07-13_summer.md", "# Summer galaxies\n\nBody text.\n")
    listed = call("saved_plans")
    assert listed["count"] == 1
    assert listed["guides"][0]["name"] == "2026-07-13_summer.md"
    # Listing must not leak an absolute path (serialize collapses it).
    assert "/Users" not in str(listed)

    got = call("saved_plans", name="2026-07-13_summer.md")
    assert "Body text." in got["markdown"]
    assert got["date"] == "2026-07-13"


def test_saved_plans_unknown_name_is_a_tool_error(captured):
    _write_plan("2026-07-13_summer.md", "# x\n")
    with pytest.raises(registry.ToolError):
        call("saved_plans", name="nope.md")


def test_saved_plans_refuses_a_path_traversal(captured):
    _write_plan("2026-07-13_summer.md", "# x\n")
    secret = config.DATA_ROOT / "secret.md"
    secret.write_text("should not be readable", encoding="utf-8")
    with pytest.raises(registry.ToolError):
        call("saved_plans", name="../secret.md")
