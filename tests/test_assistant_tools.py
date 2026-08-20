"""Behaviour of the individual read tools.

test_assistant_registry.py proves the *contract* (schema legality, JSON safety,
read-only). This file proves the tools return the right answers, against a store
with a real capture in it.
"""
from pathlib import Path

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


# ── planning tools (real astropy) ────────────────────────────────────────────

_PLAN_DAY = "2026-07-13"        # the real July night the planning tests use


@pytest.fixture
def planned(captured):
    """A store that also has cached ranking contexts, so plan_night can run."""
    root, slug, target = captured
    prioritize.write_contexts([
        prioritize.TargetContext("m13", "globular cluster", 0.0, True,
                                 {"observable": True, "transit_alt": 80.0,
                                  "hours_clear": 5.0, "nights_to_close": 90}, 5.8, None),
        prioritize.TargetContext("m31", "galaxy", 30.0, True,
                                 {"observable": True, "transit_alt": 65.0,
                                  "hours_clear": 3.0, "nights_to_close": 120}, 3.4, None),
    ])
    return root, slug, target


def test_object_observability_returns_a_real_track(captured):
    out = call("object_observability", slugs=["m13"], date=_PLAN_DAY)
    row = out["objects"][0]
    assert row["resolved"] is True and row["up_tonight"] is True
    assert row["transit_alt"] > 80            # M13 is near-overhead from lat 40
    # Datetimes came back as offset-carrying ISO strings, not raw objects.
    assert row["transit_time"].endswith(("-06:00", "-07:00"))
    # The chart array is dropped.
    assert "samples" not in row


def test_object_observability_distinguishes_unresolvable_from_not_up(captured):
    out = call("object_observability", slugs=["not-a-real-object"], date=_PLAN_DAY)
    row = out["objects"][0]
    assert row["resolved"] is False
    assert "no coordinates" in row["note"]
    # Crucially it does NOT claim the object isn't up — a different fact.
    assert "up_tonight" not in row


def test_object_observability_caps_the_slug_count(captured):
    with pytest.raises(registry.ToolError) as e:
        call("object_observability", slugs=["m13"] * 6)
    assert "plan_night" in str(e.value)       # points at the right tool instead


def test_object_observability_rejects_a_bad_date(captured):
    with pytest.raises(registry.ToolError) as e:
        call("object_observability", slugs=["m13"], date="July 13")
    assert "YYYY-MM-DD" in str(e.value)


def test_plan_night_refuses_without_contexts(captured):
    with pytest.raises(registry.ToolError) as e:
        call("plan_night", date=_PLAN_DAY)
    assert "read-only" in str(e.value).lower()


def test_plan_night_produces_a_schedule_and_field_guide(planned):
    out = call("plan_night", date=_PLAN_DAY, count=2)
    assert out["entries"], "expected targets up on this night"
    assert out["schedule"], "expected a non-overlapping schedule"

    # The dark window is named, not a bare two-element array.
    assert set(out["window"]) == {"dusk", "dawn"}
    assert out["window"]["dusk"].endswith(("-06:00", "-07:00"))

    slot = out["schedule"][0]
    assert {"slug", "start", "end", "duration_min"} <= set(slot)
    assert slot["start"] < slot["end"]        # ISO strings sort chronologically here

    assert "# " in out["field_guide_markdown"]
    assert out["legend"] and out["elapsed_s"] >= 0


def test_plan_night_schedule_slots_do_not_overlap(planned):
    slots = call("plan_night", date=_PLAN_DAY, count=3)["schedule"]
    for a, b in zip(slots, slots[1:]):
        assert a["end"] <= b["start"], f"{a['slug']} overlaps {b['slug']}"


def test_plan_night_can_omit_the_field_guide(planned):
    out = call("plan_night", date=_PLAN_DAY, include_field_guide=False)
    assert "field_guide_markdown" not in out


def test_plan_night_reports_targets_it_could_not_use(planned):
    out = call("plan_night", date=_PLAN_DAY, targets=["m13", "not-a-real-object"])
    assert out["unavailable_targets"] == ["not-a-real-object"]
    assert out["candidates_considered"] == 1


def test_plan_night_all_targets_unknown_is_an_error(planned):
    with pytest.raises(registry.ToolError) as e:
        call("plan_night", date=_PLAN_DAY, targets=["nope", "also-nope"])
    assert "rank_targets" in str(e.value)


def test_plan_night_rejects_an_unknown_site_profile(planned):
    with pytest.raises(registry.ToolError) as e:
        call("plan_night", date=_PLAN_DAY, site_profile="no-such-site")
    assert "default" in str(e.value)          # lists what does exist


def test_plan_night_writes_nothing(planned):
    """The read-only proof for the expensive path specifically — the parametrized
    version in test_assistant_registry only reaches plan_night's early refusal."""
    import hashlib

    def manifest():
        return {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in sorted(config.DATA_ROOT.rglob("*")) if p.is_file()}

    before = manifest()
    call("plan_night", date=_PLAN_DAY, count=2)
    assert manifest() == before


# ── get_image (vision) ───────────────────────────────────────────────────────

def _decode(b64):
    import base64
    import io
    from PIL import Image
    return Image.open(io.BytesIO(base64.b64decode(b64)))


@pytest.fixture
def with_image(captured):
    """The captured object, plus a real rendered image on disk."""
    from m110 import build_images, catalog, config, derived
    root, slug, target = captured
    stacks = config.seestar_stacks_dir(target)
    stacks.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.new("RGB", (2400, 1600), (30, 40, 70)).save(
        stacks / f"Stacked_10_{target}_30s_LP_20260529-010101.jpg")
    build_images.render_images(catalog.load_library(), derived.load_totals())
    return root, slug, target


def test_get_image_returns_metadata_and_an_image_block(with_image):
    from m110.assistant import registry as reg
    _, slug, _ = with_image
    meta, images = reg.call_with_media("get_image", {"slug": slug})

    assert len(images) == 1 and images[0].mime_type == "image/jpeg"
    img = _decode(images[0].base64)
    assert max(img.size) <= 1568                 # default long edge

    # The grounding a critique needs, alongside the pixels.
    assert meta["capture"]["deep_threshold_min"] > 0
    assert meta["render"]["source_width"] >= img.width
    assert meta["identifiers"]


def test_get_image_keeps_base64_out_of_the_json_payload(with_image):
    """base64 belongs in an image block, not stuffed into a text field."""
    import json
    from m110.assistant import registry as reg
    _, slug, _ = with_image
    meta, images = reg.call_with_media("get_image", {"slug": slug})
    body = json.dumps(meta)
    assert images[0].base64 not in body
    assert len(body) < 4000, "metadata payload should stay small"


def test_get_image_honours_max_long_edge(with_image):
    from m110.assistant import registry as reg
    _, slug, _ = with_image
    _, images = reg.call_with_media("get_image", {"slug": slug, "max_long_edge": 512})
    assert max(_decode(images[0].base64).size) <= 512


def test_get_image_reports_downscaling_as_a_caveat(with_image):
    _, slug, _ = with_image
    meta = call("get_image", slug=slug, max_long_edge=512)
    assert meta["render"]["downscaled"] is True
    assert any("Downscaled" in c for c in meta["caveats"])


def test_get_image_refuses_an_oversized_request(with_image):
    _, slug, _ = with_image
    with pytest.raises(registry.ToolInputError):     # schema maximum
        call("get_image", slug=slug, max_long_edge=99_999)


def test_get_image_unknown_object_and_missing_images(captured, tmp_path, monkeypatch):
    _, slug, _ = captured
    with pytest.raises(registry.ToolError) as e:
        call("get_image", slug="not-a-real-object")
    assert "list_objects" in str(e.value)
    # The captured object has a light frame but no rendered gallery image.
    with pytest.raises(registry.ToolError):
        call("get_image", slug=slug, which="finished")


def test_get_image_named_requires_and_validates_a_name(with_image):
    _, slug, _ = with_image
    with pytest.raises(registry.ToolError) as e:
        call("get_image", slug=slug, which="named")
    assert "requires a name" in str(e.value)

    with pytest.raises(registry.ToolError) as e:
        call("get_image", slug=slug, which="named", name="nope.jpg")
    assert "Available" in str(e.value)          # lists what it could have used


def test_get_image_flags_a_linear_fits_as_preview_stretched(captured):
    """The caveat that stops a model critiquing M110's own preview rendering."""
    from m110 import build_images, catalog, config, derived
    import numpy as np
    from astropy.io import fits
    _, slug, target = captured
    stack = config.stacks_dir(target)
    stack.mkdir(parents=True, exist_ok=True)
    data = np.random.default_rng(0).normal(1000, 50, (400, 600)).astype("float32")
    fits.PrimaryHDU(data).writeto(stack / "result.fit", overwrite=True)
    # get_image resolves named files through the gallery, so it has to be rendered.
    build_images.render_images(catalog.load_library(), derived.load_totals())

    meta = call("get_image", slug=slug, which="named", name="result.fit")
    assert meta["source"]["was_linear_fits"] is True
    assert any("LINEAR FITS" in c for c in meta["caveats"])
    assert any("not of the user's processing" in c for c in meta["caveats"])


def test_get_image_writes_nothing(with_image):
    """Vision is where an accidental disk write would most plausibly creep in."""
    import hashlib
    _, slug, _ = with_image

    def manifest():
        return {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in sorted(config.DATA_ROOT.rglob("*")) if p.is_file()}

    before = manifest()
    call("get_image", slug=slug)
    assert manifest() == before


def test_get_image_size_ladder_drops_quality_then_scale(with_image, monkeypatch):
    """The byte budget exists because the client re-emits our bytes as an API
    image block, which is hard-capped. Force a tiny budget and check we actually
    step down instead of returning something oversized."""
    from m110.assistant import registry as reg, vision
    _, slug, _ = with_image

    monkeypatch.setattr(vision, "MAX_ENCODED_BYTES", 3000)
    meta, images = reg.call_with_media("get_image", {"slug": slug})

    assert meta["render"]["encoded_bytes"] <= 3000, "budget not enforced"
    # It got there by lowering quality and/or scale, not by giving up.
    assert meta["render"]["jpeg_quality"] in vision.QUALITY_LADDER
    assert _decode(images[0].base64).size[0] > 0


def test_get_image_serves_a_large_source_within_budget(captured):
    """A realistic full-size frame, not the tiny synthetic corpus images."""
    from m110 import build_images, catalog, config, derived, webexport
    from PIL import Image
    import numpy as np
    _, slug, target = captured
    finished = config.finished_dir(target)
    finished.mkdir(parents=True, exist_ok=True)
    # Noise, so it doesn't compress to nothing and actually stresses the encoder.
    arr = np.random.default_rng(1).integers(0, 255, (2000, 3000, 3), dtype="uint8")
    Image.fromarray(arr, "RGB").save(finished / "processed.png")
    build_images.render_images(catalog.load_library(), derived.load_totals())

    meta = call("get_image", slug=slug, which="named", name="processed.png")
    assert meta["render"]["source_width"] == 3000
    assert max(meta["render"]["width"], meta["render"]["height"]) <= 1568
    assert meta["render"]["downscaled"] is True
    assert meta["render"]["encoded_bytes"] <= 3_500_000


# ── proposals ────────────────────────────────────────────────────────────────

def _envelope_is_wellformed(env, action):
    from m110.assistant import proposals as pr
    assert env["schema"] == pr.SCHEMA
    assert env["action"] == action
    assert env["id"] and env["created"]
    assert env["rationale"] and env["summary"]
    assert env["apply"]["requires_confirmation"] is True
    assert env["apply"]["safe_write"] is True          # all three are allowlisted
    assert env["apply"]["handler"] == pr.SAFE_WRITE_ACTIONS[action]
    # The fingerprint a later apply path checks for drift.
    assert set(env["basis"]["store_state"]) >= {
        "contexts_generated", "contexts_stale", "totals_mtime", "journal_sha256"}
    assert env["basis"]["functions"]


def test_propose_weights_returns_an_engine_computed_preview(planned):
    env = call("propose_weights", rationale="galaxy season is closing",
               type_groups={"galaxy": 2.0})
    _envelope_is_wellformed(env, "set_weights")
    assert env["payload"]["weights"]["type_weights"]["galaxy"] == 2.0

    # The preview must come from the scorer, not from prose: re-run the pure
    # ranking with the proposed weights and demand the same answer.
    proposed = prioritize.Weights(**{k: v for k, v in
                                     env["payload"]["weights"].items()
                                     if k != "type_weights"},
                                  type_weights=env["payload"]["weights"]["type_weights"])
    expected = prioritize.rank(prioritize.load_contexts(), proposed,
                               env["payload"]["strategy"], pins.load())
    assert [r["slug"] for r in env["preview"]["after"]] == \
           [r["slug"] for r in expected[:len(env["preview"]["after"])]]


def test_propose_weights_boosting_galaxies_moves_a_galaxy_up(planned):
    """m31 (galaxy) sits below m13 by default; a big galaxy boost should flip it."""
    baseline = call("rank_targets")["rows"]
    assert baseline[0]["slug"] == "m13"

    env = call("propose_weights", rationale="favour galaxies",
               type_groups={"galaxy": 5.0})
    assert env["preview"]["after"][0]["slug"] == "m31"
    assert not env["preview"]["unchanged"]
    assert any(m["slug"] == "m31" and m["change"] > 0 for m in env["preview"]["moved"])


def test_propose_weights_reports_no_change_honestly(planned):
    env = call("propose_weights", rationale="tiny nudge",
               factors={"goal": 1.0000001})
    assert env["preview"]["unchanged"] is True
    assert "would not change" in env["summary"]


def test_propose_weights_requires_something_to_change(planned):
    with pytest.raises(registry.ToolError):
        call("propose_weights", rationale="nothing")


def test_propose_weights_writes_nothing(planned):
    """The saved tuning must be untouched — this is a proposal, not a change."""
    before_w, before_s = prioritize.load_weights(), prioritize.load_strategy()
    call("propose_weights", rationale="x", strategy="deep",
         factors={"urgency": 4.0}, type_groups={"galaxy": 3.0})
    assert prioritize.load_weights() == before_w
    assert prioritize.load_strategy() == before_s


def test_propose_pins_previews_and_writes_nothing(planned):
    env = call("propose_pins", rationale="user asked for m31 first", pin=["m31"])
    _envelope_is_wellformed(env, "set_pins")
    assert env["preview"]["after"][0]["slug"] == "m31"
    assert env["payload"]["pin"] == ["m31"]
    assert pins.load() == {}, "propose_pins must not actually pin anything"


def test_propose_pins_rejects_contradictory_input(planned):
    with pytest.raises(registry.ToolError) as e:
        call("propose_pins", rationale="x", pin=["m13"], deprioritize=["m13"])
    assert "m13" in str(e.value)


def test_propose_pins_deprioritize_removes_from_the_ranking(planned):
    env = call("propose_pins", rationale="skip it", deprioritize=["m13"])
    assert all(r["slug"] != "m13" for r in env["preview"]["after"])


def test_propose_journal_entry_returns_paste_ready_markdown(captured):
    _, slug, _ = captured
    env = call("propose_journal_entry", slug=slug, rationale="record the critique",
               markdown="## 2026-07-13 critique\n\nStars are slightly bloated.",
               section="Processing notes")
    _envelope_is_wellformed(env, "append_journal")
    assert env["target"] == {"slug": slug}
    assert "Processing notes" in env["payload"]["markdown"]
    assert "bloated" in env["summary"]
    # Fingerprinted so a later apply can't clobber edits made in the meantime.
    assert env["basis"]["store_state"]["journal_sha256"]


def test_propose_journal_entry_does_not_touch_the_journal(captured):
    from m110 import objects as journals
    _, slug, _ = captured
    before = journals.read_journal_text(slug)
    call("propose_journal_entry", slug=slug, markdown="new note", rationale="x")
    assert journals.read_journal_text(slug) == before


def test_propose_journal_entry_validates_its_input(captured):
    _, slug, _ = captured
    with pytest.raises(registry.ToolError):
        call("propose_journal_entry", slug="not-a-real-object",
             markdown="x", rationale="y")
    with pytest.raises(registry.ToolError):
        call("propose_journal_entry", slug=slug, markdown="   ", rationale="y")


def test_proposals_refuse_without_contexts(captured):
    """A proposal whose preview can't be computed would be guesswork."""
    with pytest.raises(registry.ToolError) as e:
        call("propose_weights", rationale="x", strategy="deep")
    assert "Recompute" in str(e.value)


def test_proposal_preview_surfaces_top_of_list_moves_first(planned):
    """A 176 -> 80 shuffle is a bigger number than 4 -> 1, but nobody cares
    about it. Ordering by proximity to the top is what makes the preview useful."""
    from m110.assistant.proposals import rank_delta
    before = [{"rank": i, "slug": f"o{i}", "score": 0.0} for i in range(1, 200)]
    after = [dict(r) for r in before]
    # o100 jumps 100 -> 60 (big); o4 moves 4 -> 2 (small, but at the top).
    for r in after:
        if r["slug"] == "o100":
            r["rank"] = 60
        if r["slug"] == "o4":
            r["rank"] = 2
    out = rank_delta(before, after)
    assert out["moved"][0]["slug"] == "o4"
    assert out["total_moved"] == 2


# ── plan_stack ───────────────────────────────────────────────────────────────

def test_plan_stack_proposes_settings_and_leaks_no_absolute_path(captured):
    """The whole payload is checked, not just the fields carrying a Path.

    `serialize` relativizes `Path` objects but passes strings through verbatim, so
    a path formatted into a message or a command string sails past it — which is
    exactly how a home directory ends up in a model's context. Assert on the
    serialized blob so any future field is covered by the same test.
    """
    import json

    _root, _slug, target = captured
    out = call("plan_stack", target=target)

    assert out["survey"]["n_frames"] >= 1
    assert "rejection" in out["settings"]
    assert out["working_dir"].startswith("Images/")          # store-relative
    assert target in out["how_to_run"] and "--run" in out["how_to_run"]
    assert isinstance(out["siril"]["found"], bool)

    blob = json.dumps(out)
    assert str(config.DATA_ROOT) not in blob
    assert str(Path.home()) not in blob


def test_plan_stack_summarises_per_frame_arrays_instead_of_shipping_them(captured):
    """`temps` carries one float per frame — ~900 numbers on a mosaic, the largest
    thing in the payload and pure noise beside the range it collapses to."""
    _root, _slug, target = captured
    out = call("plan_stack", target=target)

    assert "temps" not in out["survey"]
    temps = out["survey"].get("sensor_temp_c")
    if temps is not None:                    # the fixture frames may carry no CCD-TEMP
        assert set(temps) == {"min", "max"} and temps["min"] <= temps["max"]


def test_plan_stack_names_both_script_phases(captured):
    """A single `script` key was a half-truth — registration is one of two Siril
    runs, and the stack phase carries the settings a reader most wants to check."""
    _root, _slug, target = captured
    out = call("plan_stack", target=target)
    assert "seqapplyreg" in out["register_script"]
    assert "stack " in out["stack_script"]
    assert "script" not in out


def test_plan_stack_names_the_known_folders_when_the_target_is_wrong(captured):
    _root, _slug, target = captured
    with pytest.raises(registry.ToolError, match="Known capture folders"):
        call("plan_stack", target="not-a-real-folder")
    # And the message actually helps: it lists the one that does exist.
    try:
        call("plan_stack", target="not-a-real-folder")
    except registry.ToolError as e:
        assert target in str(e)
