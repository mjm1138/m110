"""Tests for processing-prep (siril.py) — temp fixtures, never live data."""
import json
import os

import pytest

from m110 import config, siril


def _make_target(tmp_path, monkeypatch, ircut=120, lp=0):
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    target = "M101"
    lights = config.lights_dir(target)
    lights.mkdir(parents=True)
    for i in range(ircut):
        (lights / f"Light_M101_20s_IRCUT_20260101-{i:06d}.fit").write_text("x")
    for i in range(lp):
        (lights / f"Light_M101_20s_LP_20260102-{i:06d}.fit").write_text("y")
    return target


# ── preset / drizzle tree ────────────────────────────────────────────────────

@pytest.mark.parametrize("frames,drizzle,amount,pf", [
    (50, False, 1.0, 1.0),
    (99, False, 1.0, 1.0),
    (100, True, 1.5, 1.0),
    (299, True, 1.5, 1.0),
    (300, True, 1.5, 0.7),
    (499, True, 1.5, 0.7),
    (500, True, 2.0, 0.5),
    (3000, True, 2.0, 0.5),
])
def test_drizzle_tree(frames, drizzle, amount, pf):
    assert siril.drizzle_for(frames) == (drizzle, amount, pf)
    p = siril.default_preset(frames)
    assert (p["drizzle"], p["drizzle_amount"], p["pixel_fraction"]) == (drizzle, amount, pf)


def test_default_preset_constants():
    p = siril.default_preset(200)
    assert p["telescope"] == "ZWO Seestar S50"
    assert p["filter"] == "No Filter (Broadband)"
    assert p["darks"] is False and p["flats"] is False and p["biases"] is False
    assert p["batch_size"] == 25000 and p["bg_extract"] is True
    assert p["roundness"] == 95.0 and p["fwhm"] == 95.0
    assert p["star_count_filter"] == 100.0 and p["bg_filter"] == 95.0
    assert p["weighting_method"] == "Weighted FWHM"
    assert p["spcc"] is False and p["compression"] is False
    assert len(p) == 22


def test_filter_of():
    assert siril.filter_of("Light_M101_20s_IRCUT_20260101-000000.fit") == "IRCUT"
    assert siril.filter_of("Light_M101_20s_LP_20260101-000000.fit") == "LP"
    assert siril.filter_of("random.fit") == siril.OTHER_FILTER


# ── plan (read-only) ─────────────────────────────────────────────────────────

def test_plan_groups_per_filter(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=350, lp=5)
    plan = siril.plan_prep(target)
    assert plan.total_lights == 355
    assert set(plan.filters) == {"IRCUT", "LP"}
    assert len(plan.groups["IRCUT"]) == 350 and len(plan.groups["LP"]) == 5
    # raw count drives drizzle (355 → 1.5/0.7)
    assert plan.frame_basis == "raw" and plan.usable_frames == 355
    assert plan.preset["drizzle_amount"] == 1.5 and plan.preset["pixel_fraction"] == 0.7
    # dest paths go under process/lights_<FILTER>/
    src, dst = plan.groups["LP"][0]
    assert dst.endswith("/process/lights_LP/" + os.path.basename(dst))
    # LP present → LP-blend guidance included
    assert "siril_lp_narrowband_galaxy_blend" in plan.guidance


def test_plan_usable_frames_override(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=600)
    plan = siril.plan_prep(target, usable_frames=80)  # post-rejection count
    assert plan.frame_basis == "stack" and plan.usable_frames == 80
    assert plan.preset["drizzle"] is False     # <100 usable → no drizzle


def test_plan_no_lights(tmp_path, monkeypatch):
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    plan = siril.plan_prep("Nope")
    assert plan.total_lights == 0 and plan.groups == {}


# ── apply (the only writer) ──────────────────────────────────────────────────

def test_apply_hardlinks_preset_and_idempotent(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=120, lp=3)
    plan = siril.plan_prep(target)
    res = siril.apply_prep(plan)
    assert res == {"linked": 123, "skipped": 0, "cancelled": False}

    proc = config.process_dir(target)
    sample = next((proc / "lights_IRCUT").glob("*.fit"))
    assert sample.stat().st_nlink > 1            # hardlink, not a copy
    assert len(list((proc / "lights_IRCUT").glob("*.fit"))) == 120
    assert len(list((proc / "lights_LP").glob("*.fit"))) == 3

    preset_file = proc / "presets" / siril.PRESET_NAME
    assert preset_file.is_file()
    d = json.loads(preset_file.read_text())
    assert d["drizzle_amount"] == 1.5 and d["pixel_fraction"] == 1.0   # 123 frames
    assert (proc / "next-steps.md").is_file()

    # re-run is a no-op (skip-if-present)
    res2 = siril.apply_prep(plan)
    assert res2["linked"] == 0 and res2["skipped"] == 123


def test_apply_copy_fallback_when_link_unsupported(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=5)
    plan = siril.plan_prep(target)

    def _boom(src, dst):
        raise OSError("cross-device link not permitted")
    monkeypatch.setattr(siril.os, "link", _boom)

    res = siril.apply_prep(plan)
    assert res["linked"] == 5
    proc = config.process_dir(target)
    f = next((proc / "lights_IRCUT").glob("*.fit"))
    assert f.is_file() and f.read_text() == "x"   # copied bytes
    assert f.stat().st_nlink == 1                 # a copy, not a link


def test_apply_cancel_stops_before_writing_preset(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=10)
    plan = siril.plan_prep(target)
    res = siril.apply_prep(plan, should_cancel=lambda: True)
    assert res["cancelled"] is True and res["linked"] == 0
    # preset/next-steps are not written on cancel
    assert not (config.process_dir(target) / "presets" / siril.PRESET_NAME).exists()


# ── guidance ─────────────────────────────────────────────────────────────────

def test_guidance_bundled_and_selected():
    ids = siril.guidance_ids()
    assert "siril_processing_workflow" in ids and "siril_drizzle_guide" in ids
    assert siril.guidance_path("siril_drizzle_guide").is_file()
    # title comes from the first heading
    assert siril.guidance_title("siril_drizzle_guide")
    core = siril.guidance_for(set(), star_removal=False)
    assert "siril_lp_narrowband_galaxy_blend" not in core
    with_lp = siril.guidance_for({"LP"}, star_removal=False)
    assert "siril_lp_narrowband_galaxy_blend" in with_lp
