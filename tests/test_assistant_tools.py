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
