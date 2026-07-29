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


def _add_calibration(target, darks=0, flats=0, biases=0):
    """Drop calibration frames into the target's darks/flats/biases tiers."""
    for n, dir_fn, tag in ((darks, config.darks_dir, "Dark"),
                           (flats, config.flats_dir, "Flat"),
                           (biases, config.biases_dir, "Bias")):
        if not n:
            continue
        d = dir_fn(target)
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (d / f"{tag}_{i:03d}.fit").write_text("c")


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


def test_link_or_copy_is_idempotent_when_already_linked(tmp_path):
    """Regression: a second/concurrent prep where the sandbox hardlink already
    exists must NOT fall back to copyfile onto the same inode (SameFileError) —
    the bug that surfaced when two autopreps raced an import (ROADMAP 6a)."""
    src = tmp_path / "a.fit"
    src.write_text("data")
    dst = tmp_path / "b.fit"
    os.link(str(src), str(dst))                 # a prior/concurrent pass linked it
    siril._link_or_copy(str(src), str(dst))     # must be a no-op, not raise
    assert dst.exists() and os.path.samefile(str(src), str(dst))


def test_prepare_multi_filter_per_job(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=120, lp=40)
    plan = siril.plan_prep(target)
    assert plan.multi_filter is True and {j.filt for j in plan.jobs} == {"IRCUT", "LP"}
    siril.apply_prep(plan)
    sb = config.siril_dir(target)
    assert (sb / "IRCUT" / "lights").is_dir() and (sb / "LP" / "lights").is_dir()
    assert (sb / "IRCUT" / "presets" / siril.PRESET_NAME).is_file()


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


# ── prepare: calibration-aware sandbox (#57 part B) ──────────────────────────

def test_prep_hardlinks_calibration_and_sets_toggles(tmp_path, monkeypatch):
    """#57: darks/flats/biases present → hardlinked into the sandbox root beside
    lights/, and the Naztronomy preset's calibration toggles turned on."""
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    _add_calibration(target, darks=10, flats=8, biases=8)
    plan = siril.plan_prep(target)
    assert plan.calib_kinds == ["darks", "flats", "biases"]

    siril.apply_prep(plan)
    sb = config.siril_dir(target)
    for kind, n in (("darks", 10), ("flats", 8), ("biases", 8)):
        got = list((sb / kind).glob("*.fit"))
        assert len(got) == n
        assert got[0].stat().st_nlink > 1                 # hardlinked, no extra bytes
    d = json.loads((sb / "presets" / siril.PRESET_NAME).read_text())
    assert (d["darks"], d["flats"], d["biases"]) == (True, True, True)
    assert siril.is_default_preset(d)                     # still pristine/re-tunable


def test_prep_without_calibration_is_lights_only(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    plan = siril.plan_prep(target)
    assert plan.calib_kinds == [] and plan.calib_links == []
    siril.apply_prep(plan)
    sb = config.siril_dir(target)
    assert not (sb / "darks").exists() and not (sb / "flats").exists()
    d = json.loads((sb / "presets" / siril.PRESET_NAME).read_text())
    assert (d["darks"], d["flats"], d["biases"]) == (False, False, False)


def test_prep_partial_calibration_toggles_only_present_tiers(tmp_path, monkeypatch):
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    _add_calibration(target, darks=10)                    # darks only
    plan = siril.plan_prep(target)
    assert plan.calib_kinds == ["darks"]
    siril.apply_prep(plan)
    sb = config.siril_dir(target)
    assert (sb / "darks").is_dir() and not (sb / "flats").exists()
    d = json.loads((sb / "presets" / siril.PRESET_NAME).read_text())
    assert (d["darks"], d["flats"], d["biases"]) == (True, False, False)


def test_is_default_preset_reads_calibration_toggles():
    """A calibration-on default still reads as pristine (re-tunable); a hand edit
    on top of it does not — so autoprep never clobbers a user's changes."""
    pristine = siril.default_preset(200, darks=True, flats=True)
    assert siril.is_default_preset(pristine)
    assert not siril.is_default_preset(dict(pristine, batch_size=999))


def test_import_archive_keeps_calibration(tmp_path, monkeypatch):
    """Importing finished work archives the run's output but KEEPS calibration
    (like lights + preset) so the sandbox is ready to re-run (#57)."""
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    _add_calibration(target, darks=10, flats=8, biases=8)
    siril.apply_prep(siril.plan_prep(target))
    sb = config.siril_dir(target)
    _processed(sb, target)                                # a render + stack to import
    plan = siril.scan_finished(target)
    siril.apply_import(target, [it.src for it in plan.items], cleanup="archive")
    for kind in ("lights", "darks", "flats", "biases"):
        assert (sb / kind).is_dir() and any((sb / kind).glob("*.fit"))


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


def test_working_dirs_single_multi_and_absent(tmp_path, monkeypatch):
    """working_dirs() feeds "Process in Siril": the sandbox root for a
    single-filter target, the per-filter job dirs when split, [] with no
    sandbox."""
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    assert siril.working_dirs(target) == []          # no sandbox prepared yet

    siril.apply_prep(siril.plan_prep(target))
    assert siril.working_dirs(target) == [config.siril_dir(target)]

    multi = _make_target(tmp_path, monkeypatch, ircut=120, lp=40, name="M27")
    siril.apply_prep(siril.plan_prep(multi))
    sb = config.siril_dir(multi)
    assert set(siril.working_dirs(multi)) == {sb / "IRCUT", sb / "LP"}


def test_scan_finished_picks_up_output_loose_in_object_dir(tmp_path, monkeypatch):
    """The mis-pointed-working-directory case: Siril's working dir was set to
    Images/<target>/ instead of the siril/ sandbox, so the run's output landed
    directly in the object dir. It must still be found — and the managed tiers,
    raw inputs, and Siril's process/ scratch must be excluded."""
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    siril.apply_prep(siril.plan_prep(target))
    root = config.target_dir(target)

    # Output the run dropped loose in the object dir.
    (root / f"{target}_processed.png").write_text("PNG")   # render → finished/
    (root / f"{target}_processed.fit").write_text("STACK")  # stack → stacks/
    # Noise that must be ignored: bare intermediate, raw sub, siril scratch, and
    # a file already sitting in a managed tier.
    (root / f"{target}_og.fit").write_text("i")            # intermediate → skip
    (root / "process").mkdir()
    (root / "process" / f"{target}_processed.fit").write_text("scratch")  # skip
    (config.finished_dir(target) / f"old_processed.png").parent.mkdir(
        parents=True, exist_ok=True)
    (config.finished_dir(target) / "old_processed.png").write_text("done")  # tier

    assert siril.has_unimported_output(target) is True
    plan = siril.scan_finished(target)
    got = {it.name: (it.kind, it.dest) for it in plan.items}
    assert got == {
        f"{target}_processed.png": ("render", str(config.finished_dir(target)
                                                  / f"{target}_processed.png")),
        f"{target}_processed.fit": ("stack", str(config.stacks_dir(target)
                                                 / f"{target}_processed.fit")),
    }

    siril.apply_import(target, [it.src for it in plan.items], cleanup="none")
    assert (config.finished_dir(target) / f"{target}_processed.png").is_file()
    assert (config.stacks_dir(target) / f"{target}_processed.fit").is_file()
    # Now imported (dest exists) → no longer nags, even though the loose
    # originals remain in the object dir (we never delete outside the sandbox).
    assert siril.has_unimported_output(target) is False


def test_scan_finished_classifies_output_by_tier_directory(tmp_path, monkeypatch):
    """#85: Siril's working dir is the sandbox, and the user (or Siril) saved the
    outputs into siril/stacks/ and siril/finished/ subdirs. None of the .fit files
    carry a "finished" hint in their name, so filename-only classification dropped
    them (only the .jpg was ever picked up) — the tier directory now classifies
    them outright: stacks/ → stack, finished/ → deliverable."""
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    siril.apply_prep(siril.plan_prep(target))
    sb = config.siril_dir(target)
    (sb / "stacks").mkdir()
    (sb / "finished").mkdir()
    (sb / "stacks" / "M_27_387x20sec_0813_og.fit").write_text("STACK")  # no hint
    (sb / "finished" / "M_27_387_2026-07-21.fit").write_text("MASTER")  # no hint
    (sb / "finished" / "M_27_387_2026-07-21.jpg").write_text("JPG")

    assert siril.has_unimported_output(target) is True
    got = {it.name: (it.kind, it.dest) for it in siril.scan_finished(target).items}
    assert got == {
        "M_27_387x20sec_0813_og.fit":
            ("stack", str(config.stacks_dir(target) / "M_27_387x20sec_0813_og.fit")),
        "M_27_387_2026-07-21.fit":
            ("render", str(config.finished_dir(target) / "M_27_387_2026-07-21.fit")),
        "M_27_387_2026-07-21.jpg":
            ("render", str(config.finished_dir(target) / "M_27_387_2026-07-21.jpg")),
    }

    siril.apply_import(target, [it.src for it in siril.scan_finished(target).items],
                       cleanup="none")
    assert (config.stacks_dir(target) / "M_27_387x20sec_0813_og.fit").is_file()
    assert (config.finished_dir(target) / "M_27_387_2026-07-21.fit").is_file()
    assert (config.finished_dir(target) / "M_27_387_2026-07-21.jpg").is_file()


def test_scan_finished_skips_files_already_in_their_tier(tmp_path, monkeypatch):
    """Now that the managed tiers are scanned, files already correctly sitting in
    stacks/ / finished/ (p == dest) must NOT flood the preview — the gallery and
    derived data already read them in place. Only files that would move surface."""
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    siril.apply_prep(siril.plan_prep(target))
    config.stacks_dir(target).mkdir(parents=True, exist_ok=True)
    config.finished_dir(target).mkdir(parents=True, exist_ok=True)
    (config.stacks_dir(target) / "already.fit").write_text("S")
    (config.finished_dir(target) / "already.jpg").write_text("J")
    (config.finished_dir(target) / "already.fit").write_text("F")

    assert siril.has_unimported_output(target) is False
    assert siril.scan_finished(target).items == []


def test_tier_directory_wins_over_intermediate_filename(tmp_path, monkeypatch):
    """Directory wins over filename (#85): a star-layer name vetoes a *loose* file
    (starless/starmask are always intermediates when unsorted), but the same name
    filed under finished/ is imported as a deliverable — the user put it there."""
    target = _make_target(tmp_path, monkeypatch, ircut=120)
    siril.apply_prep(siril.plan_prep(target))
    sb = config.siril_dir(target)
    (sb / "finished").mkdir()
    (sb / "finished" / "M101_starless.tif").write_text("KEEP")  # tier wins → render
    (sb / "M101_starless.tif").write_text("SKIP")               # loose → vetoed

    items = siril.scan_finished(target).items
    assert [(it.name, it.kind) for it in items] == [("M101_starless.tif", "render")]
    assert items[0].dest == str(config.finished_dir(target) / "M101_starless.tif")


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


def test_resolve_import_dest_dispositions(tmp_path):
    src = tmp_path / "src.png"; src.write_bytes(b"AAA")
    dest = tmp_path / "M42.png"
    assert siril._resolve_import_dest(dest, src) == (dest, "new")   # nothing there
    dest.write_bytes(b"AAA")
    assert siril._resolve_import_dest(dest, src) == (dest, "duplicate")  # identical → skip
    dest.write_bytes(b"BBB")                                        # same name, new content
    assert siril._resolve_import_dest(dest, src) == (tmp_path / "M42-2.png", "renamed")
    (tmp_path / "M42-2.png").write_bytes(b"CCC")                    # -2 taken (different)
    assert siril._resolve_import_dest(dest, src) == (tmp_path / "M42-3.png", "renamed")
    (tmp_path / "M42-3.png").write_bytes(b"AAA")                    # src already here as -3
    assert siril._resolve_import_dest(dest, src) == (tmp_path / "M42-3.png", "duplicate")


def _sandbox_render(tmp_path, monkeypatch, content: bytes, existing: bytes | None):
    """A target whose sandbox holds one render; optionally pre-seed finished/ with a
    same-named file of `existing` bytes to force a collision."""
    target = _make_target(tmp_path, monkeypatch, ircut=10)
    sb = config.siril_dir(target); sb.mkdir(parents=True, exist_ok=True)
    render = sb / f"{target}_processed.png"; render.write_bytes(content)
    if existing is not None:
        fin = config.finished_dir(target); fin.mkdir(parents=True, exist_ok=True)
        (fin / f"{target}_processed.png").write_bytes(existing)
    return target, render


def test_apply_import_keeps_both_on_content_collision(tmp_path, monkeypatch):
    """A re-processed render (same name, new bytes) imports as `<stem>-2.png`; the old
    finished file is kept untouched — the footgun that used to skip it + archive it."""
    target, render = _sandbox_render(tmp_path, monkeypatch, b"REPROCESSED", b"ORIGINAL")
    assert siril.has_unimported_output(target) is True             # not "already imported"
    it = next(i for i in siril.scan_finished(target).items if i.src == str(render))
    assert it.already is False and "processed-2.png" in it.note
    res = siril.apply_import(target, [str(render)], cleanup="none")
    assert (res["imported"], res["skipped"]) == (1, 0)
    fin = config.finished_dir(target)
    assert (fin / f"{target}_processed.png").read_bytes() == b"ORIGINAL"      # old kept
    assert (fin / f"{target}_processed-2.png").read_bytes() == b"REPROCESSED"  # new kept


def test_apply_import_skips_true_duplicate(tmp_path, monkeypatch):
    """A byte-identical re-import is skipped and does NOT pile up a `-2` copy."""
    target, render = _sandbox_render(tmp_path, monkeypatch, b"SAME", b"SAME")
    assert siril.has_unimported_output(target) is False
    res = siril.apply_import(target, [str(render)], cleanup="none")
    assert (res["imported"], res["skipped"]) == (0, 1)
    assert not (config.finished_dir(target) / f"{target}_processed-2.png").exists()


def test_apply_import_hero_follows_renamed_file(tmp_path, monkeypatch):
    """When the chosen hero render lands under a `-2` name, the hero frontmatter must
    point at the name it actually landed under, not the source name."""
    target, render = _sandbox_render(tmp_path, monkeypatch, b"NEW", b"OLD")
    siril.apply_import(target, [str(render)], hero_src=str(render),
                       hero_slug="m101", cleanup="none")
    fm, _ = objects.read_journal("m101")
    assert fm.get("hero") == f"{target}_processed-2.png"


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
