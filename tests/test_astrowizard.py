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


# ── registry wiring ──────────────────────────────────────────────────────────

def test_both_workflows_can_import_but_only_siril_prepares():
    """AstroWizard is a registered workflow with no prepare step — work is handed
    in by `m110-stack --handoff`. Offering to "prepare objects for processing in
    AstroWizard" in Preferences would promise something that does not exist."""
    from m110 import processing
    assert {w.id for w in processing.importers()} == {"siril", "astrowizard"}
    prep_ids = {w.id for w in processing.preparing_workflows()}
    assert "siril" in prep_ids and "astrowizard" not in prep_ids


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
