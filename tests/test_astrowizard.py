"""Tests for the AstroWizard round-trip (astrowizard.py) — temp fixtures only.

Modelled on a real M27 finish: AstroWizard autosaves one file per user action, so
the sandbox holds a long `_AW<n>_` chain beside the handful of files the user
actually exported, plus the handed-off stack that started it all.
"""
import json
import pathlib

import pytest

from m110 import astrowizard, config, roundtrip, siril

STACK = "M_27_2117x20sec_2026-05-25_drizzle-2-0x_2026-08-20_1851_og.fit"

# The shape of a real run: init, three crops, six curve tweaks, star split, …
STEP_CHAIN = [
    f"{STACK[:-4]}_AW1_init.fits",
    f"{STACK[:-4]}_AW2_crop.fits",
    f"{STACK[:-4]}_AW3_crop.fits",
    f"{STACK[:-4]}_AW10_str_dee.fits",
    f"{STACK[:-4]}_AW11_starless.fits",
    f"{STACK[:-4]}_AW16_adj_curves.fits",
    f"{STACK[:-4]}_AW24_rescreen.fits",
    f"{STACK[:-4]}_AW10_str_dee_sn_starless.tif",
    # A raster with no intermediate hint: loose rasters are deliverables by
    # default, so this is the one the vocabulary alone does NOT catch.
    f"{STACK[:-4]}_AW10_str_dee_sn_in.tif",
]
EXPORTS = ["M27_2026-08-20_final.fits", "M27_2026-08-20_final.png"]


def _make_sandbox(tmp_path, monkeypatch, target="M27", *, handoff=True,
                  chain=True, exports=True):
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    base = config.astrowizard_dir(target)
    base.mkdir(parents=True)
    if handoff:
        # apply_handoff hardlinks the stack in and writes a provenance sidecar
        stacks = config.stacks_dir(target)
        stacks.mkdir(parents=True, exist_ok=True)
        (stacks / STACK).write_text("STACKBYTES")
        (base / STACK).write_text("STACKBYTES")
        (base / (STACK + ".src.json")).write_text(json.dumps({"frames": 2117}))
    if chain:
        for n in STEP_CHAIN:
            (base / n).write_text("step")
    if exports:
        for n in EXPORTS:
            (base / n).write_text("deliverable-" + n)
    return target, base


# ── discovery ────────────────────────────────────────────────────────────────

def test_the_exports_are_found_and_routed_to_finished(tmp_path, monkeypatch):
    target, _ = _make_sandbox(tmp_path, monkeypatch)
    plan = astrowizard.scan_finished(target)
    names = sorted(i.name for i in plan.items)
    assert names == sorted(EXPORTS)
    assert {i.kind for i in plan.items} == {"render"}
    for it in plan.items:
        assert it.dest.startswith(str(config.finished_dir(target)))
    assert plan.workflow == "astrowizard"


def test_the_autosaved_step_chain_is_not_offered(tmp_path, monkeypatch):
    """The `_AW<n>_` files are loose .fits with no finished hint, so the filename
    vocabulary leaves them out — which is what keeps a 26-file run from flooding
    the import preview."""
    target, _ = _make_sandbox(tmp_path, monkeypatch)
    offered = {i.name for i in astrowizard.scan_finished(target).items}
    for n in STEP_CHAIN:
        assert n not in offered


def test_the_handed_off_stack_is_not_offered_as_new_work(tmp_path, monkeypatch):
    """It is the workflow's input, and it is excluded structurally rather than by
    name. That matters because the user names their own exports: a stack handed
    over as `M27_final_stack.fit` carries a finished hint, and without the
    sidecar check the importer would offer the user their own input back as a
    deliverable."""
    target, base = _make_sandbox(tmp_path, monkeypatch)
    offered = {i.name for i in astrowizard.scan_finished(target).items}
    assert STACK not in offered

    finished_named = "M27_final_stack.fit"
    (base / finished_named).write_text("SAME")
    (base / (finished_named + ".src.json")).write_text("{}")
    offered = {i.name for i in astrowizard.scan_finished(target).items}
    assert finished_named not in offered

    # …but the same name with no sidecar is a genuine export, and is offered.
    (base / (finished_named + ".src.json")).unlink()
    offered = {i.name for i in astrowizard.scan_finished(target).items}
    assert finished_named in offered


def test_has_unimported_output_tracks_the_exports(tmp_path, monkeypatch):
    target, base = _make_sandbox(tmp_path, monkeypatch, exports=False)
    assert not astrowizard.has_unimported_output(target)
    (base / EXPORTS[0]).write_text("deliverable")
    assert astrowizard.has_unimported_output(target)


def test_astrowizard_does_not_claim_output_loose_in_the_object_dir(
        tmp_path, monkeypatch):
    """Siril scans the object dir to recover a mis-pointed working directory.
    AstroWizard must not: two workflows both claiming loose files is how one
    tool's importer ends up offering the other tool's exports."""
    target, _ = _make_sandbox(tmp_path, monkeypatch, chain=False, exports=False)
    stray = config.target_dir(target) / "M27_processed.png"
    stray.write_text("loose")
    assert not astrowizard.has_unimported_output(target)
    assert siril.SANDBOX.scan_root and not astrowizard.SANDBOX.scan_root


# ── the archive sweep ────────────────────────────────────────────────────────

def test_import_sweeps_the_chain_but_keeps_the_handoff(tmp_path, monkeypatch):
    target, base = _make_sandbox(tmp_path, monkeypatch)
    plan = astrowizard.scan_finished(target)
    res = astrowizard.apply_import(
        target, [i.src for i in plan.items], cleanup="archive")
    assert res["imported"] == len(EXPORTS) and res["cleaned"] == "archive"

    for n in EXPORTS:                       # landed in the content tier
        assert (config.finished_dir(target) / n).is_file()
    for n in STEP_CHAIN:                    # swept out of the working area
        assert not (base / n).exists()
    assert (base / STACK).is_file()         # the input survives
    assert (base / (STACK + ".src.json")).is_file()

    archived = list((base / "archive").iterdir())
    assert len(archived) == 1
    swept = {p.name for p in archived[0].iterdir()}
    assert set(STEP_CHAIN) <= swept         # moved, never deleted


def test_the_sweep_never_deletes_and_never_escapes_the_sandbox(
        tmp_path, monkeypatch):
    target, base = _make_sandbox(tmp_path, monkeypatch)
    before = sum(1 for p in base.rglob("*") if p.is_file())
    astrowizard.apply_import(target, [], cleanup="archive")
    after = sum(1 for p in base.rglob("*") if p.is_file())
    assert after == before                  # everything still inside the sandbox


def test_cleanup_none_leaves_the_working_area_alone(tmp_path, monkeypatch):
    target, base = _make_sandbox(tmp_path, monkeypatch)
    plan = astrowizard.scan_finished(target)
    res = astrowizard.apply_import(
        target, [i.src for i in plan.items], cleanup="none")
    assert res["cleaned"] == "none"
    assert (base / STEP_CHAIN[0]).is_file()


def test_a_second_run_archives_under_a_fresh_timestamp(tmp_path, monkeypatch):
    target, base = _make_sandbox(tmp_path, monkeypatch)
    astrowizard.apply_import(target, [], cleanup="archive")
    for n in STEP_CHAIN:
        (base / n).write_text("second run")
    astrowizard.apply_import(target, [], cleanup="archive")
    assert len(list((base / "archive").iterdir())) == 2


# ── the descriptor itself ────────────────────────────────────────────────────

def test_the_sandbox_id_is_a_declared_workflow(tmp_path, monkeypatch):
    """`config.SANDBOX_LINKED_INPUTS` is the single authority on which sandboxes
    exist; an id missing from it is invisible to every sandbox-skipping walk."""
    assert astrowizard.SANDBOX.id in config.SANDBOX_LINKED_INPUTS
    assert astrowizard.SANDBOX.id in config.SANDBOX_DIRNAMES


def test_is_handoff_keys_on_the_sidecar_not_the_filename(tmp_path, monkeypatch):
    _, base = _make_sandbox(tmp_path, monkeypatch, chain=False, exports=False)
    assert astrowizard.is_handoff(base / STACK)
    assert astrowizard.is_handoff(base / (STACK + ".src.json"))
    plain = base / "something_the_user_saved.fits"
    plain.write_text("x")
    assert not astrowizard.is_handoff(plain)


def test_working_dirs_is_the_root_and_only_when_a_handoff_exists(
        tmp_path, monkeypatch):
    target, base = _make_sandbox(tmp_path, monkeypatch)
    assert astrowizard.working_dirs(target) == [base]
    assert astrowizard.working_dirs("NeverHandedOff") == []


def test_the_autosave_raster_is_excluded_by_pattern_not_by_hints(
        tmp_path, monkeypatch):
    """Regression for a false positive only real data exposed: a loose raster is
    a deliverable with no hint required, so `…_AW10_str_dee_sn_in.tif` was
    offered for import beside the two genuine exports."""
    target, base = _make_sandbox(tmp_path, monkeypatch, chain=False,
                                 exports=False)
    raster = base / f"{STACK[:-4]}_AW10_str_dee_sn_in.tif"
    raster.write_text("working tiff")
    assert astrowizard.is_autosave(raster)
    assert not astrowizard.scan_finished(target).items

    # A raster the *user* named is still a deliverable — the pattern is the
    # tool's autosave signature, not a blanket veto on rasters.
    (base / "M27 my export.tif").write_text("mine")
    assert {i.name for i in astrowizard.scan_finished(target).items} == {
        "M27 my export.tif"}


def test_an_export_that_kept_the_autosave_token_is_offered(tmp_path, monkeypatch):
    """Regression (real M27 finish, 2026-09-18): AstroWizard's save dialog defaults
    to the current step's name, so accepting it and appending a word exports
    `…_og_AW23_final.png`. The bare `_AW<n>_` match hid it from the importer and
    the user's finish never reached `finished/`. A finished hint *after* the
    token is the user's word, not a step name, so it is an export."""
    target, base = _make_sandbox(tmp_path, monkeypatch, chain=False,
                                 exports=False)
    export = base / f"{STACK[:-4]}_AW23_final.png"
    export.write_text("the finish")
    assert not astrowizard.is_autosave(export)
    plan = astrowizard.scan_finished(target)
    assert [i.name for i in plan.items] == [export.name]
    assert plan.items[0].kind == "render"
    assert astrowizard.has_unimported_output(target)


def test_a_chain_descended_from_a_finished_named_master_stays_hidden(
        tmp_path, monkeypatch):
    """The chain inherits the master's stem, and a master a user imported from
    Siril as `…_finished.fit` puts the hint *before* every `_AW<n>_` token. Only
    the step suffix may carry the hint, so these are still autosaves."""
    target, base = _make_sandbox(tmp_path, monkeypatch, chain=False,
                                 exports=False)
    stem = "M_27_2888x20sec_2026-05-25_2026-09-17_1440_finished"
    chain = [f"{stem}_AW1_init.fits", f"{stem}_AW10_str_dee_sn_in.tif",
             f"{stem}_AW24_rescreen.fits"]
    for n in chain:
        (base / n).write_text("step")
        assert astrowizard.is_autosave(base / n), n
    assert not astrowizard.scan_finished(target).items
    # …and the export from that chain is still recognised by its suffix.
    (base / f"{stem}_AW25_final.png").write_text("the finish")
    assert {i.name for i in astrowizard.scan_finished(target).items} == {
        f"{stem}_AW25_final.png"}


def test_a_token_carrying_export_is_not_mistaken_for_a_wizardstack_master(
        tmp_path, monkeypatch):
    """`is_master` excludes the chain by the raw token, not by `is_autosave`:
    `M_15_wizardstack_AW3_final.fits` is neither an autosave nor the master, so
    it is offered (as a render — everything downstream of the master is) and
    the sweep does not spare it."""
    target, base = _make_sandbox(tmp_path, monkeypatch, handoff=False,
                                 chain=False, exports=False)
    master = base / "M_15_wizardstack.fits"
    master.write_text("stack")
    export = base / "M_15_wizardstack_AW3_final.fits"
    export.write_text("finish")
    assert astrowizard.is_master(master)
    assert not astrowizard.is_master(export)
    assert not astrowizard.is_autosave(export)
    items = {i.name: i.kind for i in astrowizard.scan_finished(target).items}
    assert items == {export.name: "render"}
    assert astrowizard._archive_keep(master)
    assert not astrowizard._archive_keep(export)


# ── registry wiring ──────────────────────────────────────────────────────────

def test_both_workflows_prepare_and_both_import():
    """AstroWizard gained a prepare step when StackingWizard joined its sandbox:
    that tool has no CLI and finds frames by walking the folder it is given, so
    the sandbox has to hold a `lights/` tree. Both halves symmetric again is what
    lets the Preferences checkbox mean one thing for both workflows."""
    from m110 import processing
    assert {w.id for w in processing.importers()} == {"siril", "astrowizard"}
    by_id = processing.WORKFLOWS_BY_ID
    assert by_id["siril"].autoprep is not None
    assert by_id["astrowizard"].autoprep is not None
    assert by_id["astrowizard"].importer is astrowizard


def test_workflows_with_output_names_the_tool_holding_work(tmp_path, monkeypatch):
    from m110 import processing
    target, base = _make_sandbox(tmp_path, monkeypatch, exports=False)
    assert processing.workflows_with_output(target) == []
    (base / EXPORTS[1]).write_text("a finish")
    assert [w.id for w in processing.workflows_with_output(target)] == ["astrowizard"]


def test_the_import_dialog_defaults_to_siril_but_takes_a_workflow():
    """The dialog is handed a `processing.Workflow`, so its wording and the
    sandbox it scans follow the workflow instead of being hardcoded."""
    pytest.importorskip("PySide6")
    from m110 import processing
    from m110.ui import import_dialog
    src = pathlib.Path(import_dialog.__file__).read_text()
    assert "siril." not in src, "dialog should not call the siril module directly"
    aw = processing.WORKFLOWS_BY_ID["astrowizard"]
    assert aw.importer is astrowizard
    assert import_dialog.ImportDialog._KEEPS["astrowizard"] == "the handed-off stack"


# ── retention: bounding archived runs ────────────────────────────────────────

def _fake_runs(base, names, size=2048):
    arch = base / "archive"
    for n in names:
        d = arch / n
        d.mkdir(parents=True, exist_ok=True)
        (d / "run.fit").write_bytes(b"x" * size)
    return arch


def test_prune_keeps_the_newest_n_runs(tmp_path, monkeypatch):
    target, base = _make_sandbox(tmp_path, monkeypatch, chain=False, exports=False)
    arch = _fake_runs(base, ["20260101-010000", "20260102-010000",
                             "20260103-010000", "20260104-010000"])
    res = roundtrip.prune_archives(target, astrowizard.SANDBOX, keep=2)
    assert res["removed"] == 2 and res["freed_bytes"] > 0
    assert sorted(p.name for p in arch.iterdir()) == [
        "20260103-010000", "20260104-010000"]


def test_prune_is_off_when_keep_is_zero(tmp_path, monkeypatch):
    """0 means keep everything — the setting's own escape hatch, and off has to
    be the safe direction."""
    target, base = _make_sandbox(tmp_path, monkeypatch, chain=False, exports=False)
    arch = _fake_runs(base, ["20260101-010000", "20260102-010000"])
    assert roundtrip.prune_archives(target, astrowizard.SANDBOX, keep=0) == {
        "removed": 0, "freed_bytes": 0}
    assert len(list(arch.iterdir())) == 2


def test_prune_never_touches_a_directory_that_is_not_a_run(tmp_path, monkeypatch):
    """The containment check on a recursive delete: `archive/` is ours, but a
    folder the user put there is not."""
    target, base = _make_sandbox(tmp_path, monkeypatch, chain=False, exports=False)
    arch = _fake_runs(base, ["20260101-010000", "20260102-010000",
                             "20260103-010000"])
    mine = arch / "my notes"
    mine.mkdir()
    (mine / "keep.txt").write_text("hand-written")
    roundtrip.prune_archives(target, astrowizard.SANDBOX, keep=1)
    assert (mine / "keep.txt").is_file()
    assert [p.name for p in sorted(arch.iterdir()) if p.name != "my notes"] == [
        "20260103-010000"]


def test_prune_orders_by_name_not_mtime(tmp_path, monkeypatch):
    """mtime lies here — ingest and import copy bytes, so it is copy time. The
    timestamp in the name is what the pipeline recorded."""
    import os
    target, base = _make_sandbox(tmp_path, monkeypatch, chain=False, exports=False)
    arch = _fake_runs(base, ["20260101-010000", "20260209-010000"])
    # touch the OLD run so it looks newest by mtime
    os.utime(arch / "20260101-010000", (2 ** 31 - 1, 2 ** 31 - 1))
    roundtrip.prune_archives(target, astrowizard.SANDBOX, keep=1)
    assert [p.name for p in arch.iterdir()] == ["20260209-010000"]


def test_import_prunes_only_when_it_archived(tmp_path, monkeypatch):
    from m110 import processing
    monkeypatch.setattr(processing, "archive_keep", lambda: 1)
    target, base = _make_sandbox(tmp_path, monkeypatch)
    _fake_runs(base, ["20260101-010000", "20260102-010000"])

    res = astrowizard.apply_import(target, [], cleanup="none")
    assert res["pruned"] == 0
    assert len(list((base / "archive").iterdir())) == 2

    res = astrowizard.apply_import(target, [], cleanup="archive")
    assert res["pruned"] == 2          # the two old ones; this run's is kept
    assert len(list((base / "archive").iterdir())) == 1


def test_siril_archives_are_pruned_by_the_same_setting(tmp_path, monkeypatch):
    """Retention is a property of the shared round-trip, not of one workflow."""
    from m110 import siril
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    base = config.siril_dir("M13")
    base.mkdir(parents=True)
    arch = _fake_runs(base, ["20260101-010000", "20260102-010000",
                             "20260103-010000"])
    roundtrip.prune_archives("M13", siril.SANDBOX, keep=1)
    assert [p.name for p in arch.iterdir()] == ["20260103-010000"]


# ── retention defaults: new store vs existing library ────────────────────────

def _isolated_settings(tmp_path, monkeypatch, name="settings.json"):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / name)
    monkeypatch.setattr(config, "APP_CONFIG_DIR", tmp_path / "cfg")


def test_a_brand_new_store_starts_at_three(tmp_path, monkeypatch):
    from m110 import processing
    _isolated_settings(tmp_path, monkeypatch)
    config.ensure_data_root(tmp_path / "NewStore")
    assert processing.archive_keep() == processing.NEW_STORE_ARCHIVE_KEEP == 3


def test_an_existing_library_keeps_everything(tmp_path, monkeypatch):
    """Retention deletes processing history, so it must never arrive as a
    surprise for a library that predates it."""
    from m110 import processing
    _isolated_settings(tmp_path, monkeypatch)
    old = tmp_path / "OldStore"
    (old / config.INTERNAL_DIRNAME).mkdir(parents=True)
    (old / "Images").mkdir(parents=True)
    config.ensure_data_root(old)
    assert processing.archive_keep() == 0        # 0 == keep all


def test_the_seeded_answer_is_not_recomputed_later(tmp_path, monkeypatch):
    """Written down once. A store is only 'new' the first time, and the user must
    be able to change it in Preferences without the next launch overruling them."""
    from m110 import processing
    _isolated_settings(tmp_path, monkeypatch)
    store = tmp_path / "NewStore"
    config.ensure_data_root(store)
    processing.set_archive_keep(0)               # user turns it off
    config.ensure_data_root(store)               # next launch
    assert processing.archive_keep() == 0


def test_an_unset_setting_reads_as_keep_all(tmp_path, monkeypatch):
    """The absence of an answer falls on the safe side; the 3 a new store gets is
    written explicitly, never implied by the reader."""
    from m110 import processing
    _isolated_settings(tmp_path, monkeypatch, "empty.json")
    assert processing.archive_keep() == 0


# ── StackingWizard shares the sandbox ────────────────────────────────────────

MASTER = "M_15_wizardstack.fits"


def _with_raw_lights(tmp_path, monkeypatch, target="M27", n=3):
    _, base = _make_sandbox(tmp_path, monkeypatch, target=target,
                            chain=False, exports=False)
    raw = config.lights_dir(target)
    raw.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (raw / f"Light_{target}_20s_LP_20260101-{i:06d}.fit").write_text(f"sub{i}")
    return target, base, raw


def test_prepare_lights_hardlinks_the_subs_into_the_sandbox(tmp_path, monkeypatch):
    """StackingWizard has no CLI and finds frames by walking the folder it is
    given, so the frames have to actually be there."""
    target, base, raw = _with_raw_lights(tmp_path, monkeypatch)
    assert astrowizard.prepare_lights(target) == 3
    linked = sorted(p.name for p in astrowizard.lights_dir(target).iterdir())
    assert linked == sorted(p.name for p in raw.iterdir())
    # the same inode — a second frame tree must cost no image data
    a = next(raw.iterdir())
    assert (astrowizard.lights_dir(target) / a.name).stat().st_ino == a.stat().st_ino


def test_prepare_lights_is_add_only_and_idempotent(tmp_path, monkeypatch):
    target, base, raw = _with_raw_lights(tmp_path, monkeypatch)
    astrowizard.prepare_lights(target)
    (raw / "Light_M27_20s_LP_20260102-000009.fit").write_text("new sub")
    assert astrowizard.prepare_lights(target) == 4
    assert len(list(astrowizard.lights_dir(target).iterdir())) == 4


def test_the_linked_tree_is_declared_so_backup_skips_it(tmp_path, monkeypatch):
    """The +139 GB trap. `astrowizard` held `frozenset()` while it linked nothing;
    the moment it grew a tree, its name had to go in — an undeclared link tree is
    a second full copy of every sub in every mirrored snapshot."""
    from m110.backup import scope
    assert "lights" in config.SANDBOX_LINKED_INPUTS["astrowizard"]
    assert scope.is_excluded("Images/M27/astrowizard/lights/sub.fit")
    # …and authored work in the same sandbox is still backed up
    assert not scope.is_excluded("Images/M27/astrowizard/M27_final.fits")
    assert not scope.is_excluded(f"Images/M27/astrowizard/{MASTER}")


def test_the_importer_never_offers_the_linked_subs(tmp_path, monkeypatch):
    target, base, raw = _with_raw_lights(tmp_path, monkeypatch)
    astrowizard.prepare_lights(target)
    assert not astrowizard.scan_finished(target).items
    assert not astrowizard.has_unimported_output(target)


def test_a_stackingwizard_master_is_input_not_output(tmp_path, monkeypatch):
    """It is what AstroWizard works *from*. Offering it back as a deliverable
    would file the user's own stack into finished/."""
    target, base, _ = _with_raw_lights(tmp_path, monkeypatch)
    (base / MASTER).write_text("the stack")
    assert astrowizard.is_master(base / MASTER)
    assert not astrowizard.scan_finished(target).items
    # combined-nights variant too
    assert astrowizard.is_master(base / "M_15_combined_wizardstack.fits")
    # …but a normal export is still a deliverable
    (base / "M27 final.fits").write_text("a finish")
    assert {i.name for i in astrowizard.scan_finished(target).items} == {
        "M27 final.fits"}


def test_the_sweep_spares_the_master_and_the_linked_frames(tmp_path, monkeypatch):
    """The lifetime argument that split siril/ from astrowizard/ said a cheap,
    iterated finish must not archive an expensive, stable stack. Sharing one
    directory is only safe because the stack is never treated as output."""
    target, base, _ = _with_raw_lights(tmp_path, monkeypatch)
    astrowizard.prepare_lights(target)
    (base / MASTER).write_text("hours of compute")
    (base / f"{MASTER[:-5]}_AW1_init.fits").write_text("a step")
    (base / "M27 final.fits").write_text("a finish")

    plan = astrowizard.scan_finished(target)
    astrowizard.apply_import(target, [i.src for i in plan.items], cleanup="archive")

    assert (base / MASTER).is_file(), "the master must survive a re-finish"
    assert astrowizard.lights_dir(target).is_dir(), "the frames must survive"
    assert len(list(astrowizard.lights_dir(target).iterdir())) == 3
    swept = {p.name for p in (base / "archive").rglob("*") if p.is_file()}
    assert f"{MASTER[:-5]}_AW1_init.fits" in swept


def test_autoprep_respects_the_guards(tmp_path, monkeypatch):
    target, base, _ = _with_raw_lights(tmp_path, monkeypatch)
    # only_missing skips a sandbox that already exists
    assert astrowizard.autoprep([target], only_missing=True)["prepared"] == []
    # a target with work waiting is left alone
    (base / "M27 final.fits").write_text("a finish")
    assert astrowizard.autoprep([target])["skipped"] == [target]


def test_stackingwizard_is_registered_but_cannot_be_pointed(tmp_path, monkeypatch):
    """Verified against the shipped build, not assumed: `argv` appears in no code
    object of StackingWizard 2026.08.22. M110 can start it and nothing more."""
    from m110 import launch
    assert "stackingwizard" in launch.tool_ids()
    assert launch.sets_working_dir("stackingwizard") is False
    assert launch.opens_file("stackingwizard") is False


def test_an_autosave_is_not_mistaken_for_the_master(tmp_path, monkeypatch):
    """AstroWizard names every step after the file it opened, so the whole chain
    carries the master's stem — `_wizardstack_AW1_init` must not read as a master
    or the sweep spares the entire working area."""
    _, base = _make_sandbox(tmp_path, monkeypatch, chain=False, exports=False)
    assert astrowizard.is_master(base / "M_15_wizardstack.fits")
    for step in ("M_15_wizardstack_AW1_init.fits",
                 "M_15_wizardstack_AW12_adj_sat.fits"):
        assert astrowizard.is_autosave(base / step)
        assert not astrowizard.is_master(base / step)
