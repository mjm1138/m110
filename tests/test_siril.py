"""Tests for the Siril processing round-trip (siril.py) — temp fixtures only."""
import json
import os

import pytest

from m110 import config, objects, siril


def _make_target(tmp_path, monkeypatch, ircut=120, lp=0, name="M101"):
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    lights = config.lights_dir(name)
    lights.mkdir(parents=True)
    for i in range(ircut):
        (lights / f"Light_{name}_20s_IRCUT_20260101-{i:06d}.fit").write_text("x")
    for i in range(lp):
        (lights / f"Light_{name}_20s_LP_20260102-{i:06d}.fit").write_text("y")
    return name


# ── preset / drizzle tree ────────────────────────────────────────────────────

@pytest.mark.parametrize("frames,drizzle,amount,pf", [
    (99, False, 1.0, 1.0), (100, True, 1.5, 1.0), (300, True, 1.5, 0.7),
    (500, True, 2.0, 0.5),
])
def test_drizzle_tree(frames, drizzle, amount, pf):
    assert siril.drizzle_for(frames) == (drizzle, amount, pf)


def test_default_preset_shape():
    p = siril.default_preset(200)
    assert p["telescope"] == "ZWO Seestar S50" and p["spcc"] is False
    assert len(p) == 22


def test_filter_of():
    assert siril.filter_of("Light_M101_20s_IRCUT_20260101-000000.fit") == "IRCUT"
    assert siril.filter_of("Light_M101_20s_LP_20260101-000000.fit") == "LP"
    assert siril.filter_of("random.fit") == siril.OTHER_FILTER


# ── prepare: single-filter sandbox ───────────────────────────────────────────

def test_prepare_single_filter_literal_lights(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=350)
    plan = siril.plan_prep(target)
    assert plan.total_lights == 350 and plan.multi_filter is False
    assert len(plan.jobs) == 1 and plan.jobs[0].filt == ""

    res = siril.apply_prep(plan)
    assert res == {"linked": 350, "skipped": 0, "cancelled": False}
    sb = config.siril_dir(target)
    lights = sb / "lights"                      # LITERAL 'lights' (Siril needs it)
    assert lights.is_dir() and len(list(lights.glob("*.fit"))) == 350
    assert next(lights.glob("*.fit")).stat().st_nlink > 1   # hardlink
    preset = sb / "presets" / siril.PRESET_NAME
    d = json.loads(preset.read_text())
    assert d["drizzle_amount"] == 1.5 and d["pixel_fraction"] == 0.7   # 350 frames
    assert (sb / "next-steps.md").is_file()
    # idempotent
    assert siril.apply_prep(plan)["linked"] == 0


def test_prepare_multi_filter_per_job(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=120, lp=40)
    plan = siril.plan_prep(target)
    assert plan.multi_filter is True and {j.filt for j in plan.jobs} == {"IRCUT", "LP"}
    siril.apply_prep(plan)
    sb = config.siril_dir(target)
    assert (sb / "IRCUT" / "lights").is_dir() and (sb / "LP" / "lights").is_dir()
    assert (sb / "IRCUT" / "presets" / siril.PRESET_NAME).is_file()
    # LP present → LP-blend guidance offered
    assert "siril_lp_narrowband_galaxy_blend" in plan.guidance


def test_prepare_usable_frames_override(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=600)
    plan = siril.plan_prep(target, usable_frames=80)   # post-rejection
    assert plan.jobs[0].preset["drizzle"] is False     # <100 → no drizzle


def test_apply_copy_fallback(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=4)
    plan = siril.plan_prep(target)
    monkeypatch.setattr(siril.os, "link",
                        lambda s, d: (_ for _ in ()).throw(OSError("xdev")))
    siril.apply_prep(plan)
    f = next((config.siril_dir(target) / "lights").glob("*.fit"))
    assert f.read_text() == "x" and f.stat().st_nlink == 1   # copied


# ── autoprep (ingest hook) ───────────────────────────────────────────────────

def test_autoprep_sets_up_and_skips_pending(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    out = siril.autoprep([target])
    assert out["prepared"] == [target]
    assert (config.siril_dir(target) / "lights").is_dir()

    # drop a finished output → autoprep must now skip (don't disturb)
    (config.siril_dir(target) / f"{target}_processed.png").write_text("p")
    assert siril.autoprep([target]) == {"prepared": [], "skipped": [target]}


# ── import: detect / scan / apply / cleanup ──────────────────────────────────

def _processed(sb, target):
    (sb / f"{target}_2026_processed.png").write_text("PNG")   # render
    (sb / f"{target}_2026_processed.fit").write_text("STACK")  # stack
    (sb / f"{target}_og.fit").write_text("i")                  # intermediate (skip)
    (sb / f"starless_{target}.fit").write_text("i")            # intermediate (skip)


def test_scan_finished_classifies_and_excludes_intermediates(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    siril.apply_prep(siril.plan_prep(target))
    sb = config.siril_dir(target)
    _processed(sb, target)
    assert siril.has_unimported_output(target) is True

    plan = siril.scan_finished(target)
    kinds = {it.name: it.kind for it in plan.items}
    assert kinds == {f"{target}_2026_processed.png": "render",
                     f"{target}_2026_processed.fit": "stack"}
    assert plan.hero_candidates == [str(sb / f"{target}_2026_processed.png")]


def test_scan_finished_keeps_pipeline_step_tokens_in_final_name(tmp_path, monkeypatch):
    """A deliverable bakes its steps into the name ("…_spcc_processed.png"); the
    step tokens must NOT veto it (regression: NGC 6992 output never picked up)."""
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    siril.apply_prep(siril.plan_prep(target))
    sb = config.siril_dir(target)
    base = f"{target}_119x20sec_drizzle-1-5x_spcc"
    (sb / f"{base}_processed.png").write_text("PNG")   # render — has step + final
    (sb / f"{base}_processed.fit").write_text("STACK")  # stack — has step + final
    (sb / f"{base}.fit").write_text("i")                # bare step, no final → skip
    (sb / f"{base}_crop.fit").write_text("i")           # intermediate → skip
    (sb / f"starless_{base}_processed.fit").write_text("i")  # layer wins → skip

    assert siril.has_unimported_output(target) is True
    kinds = {it.name: it.kind for it in siril.scan_finished(target).items}
    assert kinds == {f"{base}_processed.png": "render",
                     f"{base}_processed.fit": "stack"}


def test_apply_import_routes_sets_hero_and_archives(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    siril.apply_prep(siril.plan_prep(target))
    sb = config.siril_dir(target)
    _processed(sb, target)

    plan = siril.scan_finished(target)
    srcs = [it.src for it in plan.items]
    hero = plan.hero_candidates[0]
    res = siril.apply_import(target, srcs, hero_src=hero, hero_slug="m101",
                             cleanup="archive")
    assert res["imported"] == 2 and res["cleaned"] == "archive"
    assert (config.finished_dir(target) / f"{target}_2026_processed.png").is_file()
    assert (config.stacks_dir(target) / f"{target}_2026_processed.fit").is_file()
    fm, _ = objects.read_journal("m101")
    assert fm.get("hero") == f"{target}_2026_processed.png"

    # sandbox is tidied + ready for another run: lights/ + presets/ kept…
    assert (sb / "lights").is_dir() and (sb / "presets" / siril.PRESET_NAME).is_file()
    # …outputs (incl. intermediates) moved into a visible archive/<ts>/…
    archived = list((sb / "archive").rglob("*"))
    names = {p.name for p in archived}
    assert f"{target}_2026_processed.png" in names      # imported original archived
    assert f"{target}_og.fit" in names                  # intermediate archived (not deleted)
    assert f"starless_{target}.fit" in names
    # …and the run's output is gone from the working root (ready to re-run)…
    assert not (sb / f"{target}_og.fit").exists()
    assert siril.has_unimported_output(target) is False
    # originals untouched
    assert len(list(config.lights_dir(target).glob("*.fit"))) == 120


def test_archive_per_filter_jobs(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=120, lp=40)
    siril.apply_prep(siril.plan_prep(target))
    sb = config.siril_dir(target)
    (sb / "IRCUT" / f"{target}_processed.png").write_text("p")
    siril.apply_import(target, [], cleanup="archive")
    # archived within the IRCUT job, lights kept
    assert any((sb / "IRCUT" / "archive").rglob("*_processed.png"))
    assert (sb / "IRCUT" / "lights").is_dir()


def test_keep_current_hero_on_reimport(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=10)
    siril.apply_prep(siril.plan_prep(target))
    objects.set_frontmatter_key("m101", "hero", "chosen.png")
    sb = config.siril_dir(target)
    (sb / f"{target}_processed.png").write_text("p")
    # hero_src=None → keep the current hero unchanged
    siril.apply_import(target, [str(sb / f"{target}_processed.png")],
                       hero_src=None, hero_slug="m101", cleanup="none")
    fm, _ = objects.read_journal("m101")
    assert fm.get("hero") == "chosen.png"


# ── frontmatter upsert ───────────────────────────────────────────────────────

def test_set_frontmatter_key_upsert(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBJECTS_DIR", tmp_path / "Objects")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    objects.write_journal("m1", '---\nname: "Crab"\nhero: "old.png"\n---\n\nbody\n')
    objects.set_frontmatter_key("m1", "hero", "new.png")
    fm, body = objects.read_journal("m1")
    assert fm["hero"] == "new.png" and fm["name"] == "Crab" and "body" in body
    # inserts when missing
    objects.set_frontmatter_key("m1", "hero_caption", "nice")
    fm2, _ = objects.read_journal("m1")
    assert fm2["hero_caption"] == "nice" and fm2["hero"] == "new.png"


def test_guidance_bundled():
    assert "siril_drizzle_guide" in siril.guidance_ids()
    assert siril.guidance_path("siril_drizzle_guide").is_file()
