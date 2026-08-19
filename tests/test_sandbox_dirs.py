"""Per-target workflow sandboxes (`config.SANDBOX_DIRNAMES`) — temp fixtures only.

Each sandbox under `Images/<target>/` belongs to exactly one processing workflow.
Three separate walks must refuse to descend into one that isn't theirs, and every
one of those failures is **silent**: Siril claims another tool's exports as its own
output, ingest re-imports a working area, and a backup carries a regenerable
hardlink tree in every snapshot. So the policy is asserted directly, not just its
current consequences.
"""
import json
import os

from m110 import backup, config, ingest, siril
from m110.backup import scope
from tests._helpers import seed_capture, seed_root, seed_sandbox


def _seed_astrowizard(target="M51"):
    """An AstroWizard run: the handed-off stack plus what the user exported.

    The names are deliberately *not* recognisable — AstroWizard's final name is
    typed into a native save dialog, so only the place identifies these. The
    `-starless` suffix is one of its two hard-coded fragments.
    """
    aw = config.astrowizard_dir(target)
    aw.mkdir(parents=True, exist_ok=True)
    (aw / f"{target}_1746x20sec_og.fit").write_text("handed-off stack")
    (aw / "my final render.png").write_text("export")
    (aw / "my final render-starless.png").write_text("starless export")
    return aw


# ── the policy ───────────────────────────────────────────────────────────────

def test_every_sandbox_dirname_is_honoured_by_every_walk():
    assert config.SANDBOX_DIRNAMES, "the authority must not be empty"
    for name in config.SANDBOX_DIRNAMES:
        assert name in siril._ROOT_SKIP_DIRS, f"siril would claim {name}/ output"
        assert name in ingest._SKIP_DIRS, f"ingest would re-import {name}/"
        for d in config.SANDBOX_LINKED_INPUTS[name]:
            assert scope.is_excluded(f"Images/M51/{name}/{d}/a.fit"), \
                f"{name}/{d}/ hardlinks would land in every backup snapshot"
    # The exclusion is scoped to a sandbox, not to the name anywhere in the store.
    assert not scope.is_excluded("Images/M51/finished/M51.png")
    assert not scope.is_excluded("Images/siril/lights/a.fit")   # a target *named* siril


def test_every_sandbox_declares_its_linked_inputs():
    """The forcing function: a workflow cannot be added without saying which of its
    subdirectories are hardlinks to frames the store already holds. `SANDBOX_DIRNAMES`
    is derived from the mapping's keys, so an omission is a missing *sandbox*, which
    the test above catches loudly — not a silently un-narrowed backup."""
    assert config.SANDBOX_DIRNAMES == frozenset(config.SANDBOX_LINKED_INPUTS), \
        "SANDBOX_DIRNAMES is derived from SANDBOX_LINKED_INPUTS; they cannot drift"
    for name, linked in config.SANDBOX_LINKED_INPUTS.items():
        for d in linked:
            assert scope.is_excluded(f"Images/M51/{name}/{d}")           # the dir itself
            assert scope.is_excluded(f"Images/M51/{name}/{d}/a.fit")     # sandbox root job
            assert scope.is_excluded(f"Images/M51/{name}/Ha/{d}/a.fit")  # per-filter job
        # Whatever the workflow, everything else it holds is authored work.
        assert not scope.is_excluded(f"Images/M51/{name}/anything.fit")
        assert not scope.is_excluded(f"Images/M51/{name}/presets/p.ssf")
        assert not scope.is_excluded(f"Images/M51/{name}/archive/20260101-000000/x.fit")


def test_a_deeper_linked_input_name_is_kept_not_dropped():
    """The denylist fails toward backing a file up. `archive/<ts>/` is a past run —
    authored output — so a `lights` *inside* it is not the live hardlink tree, and a
    file merely named `lights.fit` is not a directory at all."""
    assert not scope.is_excluded("Images/M51/siril/archive/20260101-000000/lights/a.fit")
    assert not scope.is_excluded("Images/M51/siril/lights.fit")
    assert not scope.is_excluded("Images/M51/siril/archive/20260101-000000/lights.fit")


# ── the consequences, per walk ───────────────────────────────────────────────

def test_siril_import_ignores_another_workflows_sandbox(tmp_path, monkeypatch):
    """The sharp case: AstroWizard's exports must not become Siril's finished work."""
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    target = "M51"
    _seed_astrowizard(target)

    # Nothing of Siril's own is pending, so nothing at all is.
    assert siril.scan_finished(target).items == []
    assert not siril.has_unimported_output(target)

    # With a genuine Siril deliverable present, only that one is offered.
    seed_sandbox(target)
    names = {i.name for i in siril.scan_finished(target).items}
    assert names == {f"{target}_x_processed.png", f"{target}_x_processed.fit"}
    assert siril.has_unimported_output(target)


def _seed_siril_run(target, filt=None):
    """A Siril sandbox as `apply_prep` leaves it: hardlinked inputs beside the work.

    The lights are real `os.link`s — being a second path to bytes the store already
    holds is the entire reason they are excluded, so faking them as copies would
    test nothing.
    """
    base = config.siril_dir(target)
    job = base / filt if filt else base
    (job / "lights").mkdir(parents=True, exist_ok=True)
    for src in config.lights_dir(target).iterdir():
        os.link(src, job / "lights" / src.name)
    (job / "presets").mkdir(parents=True, exist_ok=True)
    (job / "presets" / "naztronomy.ssf").write_text("a hand-edited preset")
    run = job / "archive" / "20260819-120000"
    run.mkdir(parents=True, exist_ok=True)
    (run / f"{target}_stretch.fit").write_text("hours of hand-processing")
    (base / "next-steps.md").write_text("guidance")
    return base


def test_backup_keeps_sandbox_work_and_skips_only_its_linked_inputs(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _slug, tid = seed_capture(root)
    _seed_siril_run(tid)
    _seed_astrowizard(tid)

    backup.create_snapshot(backup.BackupOptions(destination=tmp_path / "backups"))
    snap = backup.list_snapshots(tmp_path / "backups")[0].path

    # Authored work is kept: an archived run, a hand-edited preset, the guidance
    # file, and another workflow's exports. Nothing regenerates any of it.
    assert (snap / f"Images/{tid}/siril/archive/20260819-120000/{tid}_stretch.fit").exists()
    assert (snap / f"Images/{tid}/siril/presets/naztronomy.ssf").exists()
    assert (snap / f"Images/{tid}/siril/next-steps.md").exists()
    assert (snap / f"Images/{tid}/astrowizard/my final render.png").exists()

    # The linked inputs are not — and the frames themselves still are, under the
    # path they actually live at.
    assert not (snap / f"Images/{tid}/siril/lights").exists()
    assert (snap / f"Images/{tid}/lights").exists()


def test_a_sub_is_stored_once_not_once_per_sandbox_that_links_it(tmp_path, monkeypatch):
    """The cost this exclusion exists to avoid. Mirrored dedups by *relative path*,
    so a sandbox link tree is a second full copy of every sub — on a real library,
    +139 GB against 186 GB backed up. Per-filter jobs would make it a third."""
    root = seed_root(tmp_path, monkeypatch)
    _slug, tid = seed_capture(root)
    _seed_siril_run(tid)
    _seed_siril_run(tid, filt="Ha")

    backup.create_snapshot(backup.BackupOptions(destination=tmp_path / "backups"))
    snap = backup.list_snapshots(tmp_path / "backups")[0].path
    manifest = json.loads((snap / backup.MANIFEST_NAME).read_text())

    subs = [k for k in manifest["files"] if k.endswith(".fit") and "/lights/" in k]
    assert len(subs) == 1, f"each sub belongs in the snapshot once, got {subs}"
    assert subs[0] == f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"


def test_ingest_does_not_recurse_into_a_workflow_sandbox(tmp_path, monkeypatch):
    """Importing a foreign store must not pull its working areas across."""
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    src = tmp_path / "other-store"
    for name in config.SANDBOX_DIRNAMES:
        d = src / "M51" / name
        d.mkdir(parents=True)
        (d / "M51_stack.fit").write_text("working area")

    ops = ingest.scan_directory_plan(src)
    assert not [o for o in ops
                if any(f"/{n}/" in str(o.src) for n in config.SANDBOX_DIRNAMES)]
