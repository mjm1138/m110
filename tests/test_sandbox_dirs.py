"""Per-target workflow sandboxes (`config.SANDBOX_DIRNAMES`) — temp fixtures only.

Each sandbox under `Images/<target>/` belongs to exactly one processing workflow.
Three separate walks must refuse to descend into one that isn't theirs, and every
one of those failures is **silent**: Siril claims another tool's exports as its own
output, ingest re-imports a working area, and a backup carries a regenerable
hardlink tree in every snapshot. So the policy is asserted directly, not just its
current consequences.
"""
import json

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
        assert scope.is_excluded(f"Images/M51/{name}/anything.fit"), \
            f"{name}/ would land in every backup snapshot"
    # The exclusion is scoped to a sandbox, not to the name anywhere in the store.
    assert not scope.is_excluded("Images/M51/finished/M51.png")
    assert not scope.is_excluded("Images/siril/lights/a.fit")   # a target *named* siril


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


def test_backup_skips_every_workflow_sandbox(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _slug, tid = seed_capture(root)
    seed_sandbox(tid)
    _seed_astrowizard(tid)

    backup.create_snapshot(backup.BackupOptions(destination=tmp_path / "backups"))
    snap = backup.list_snapshots(tmp_path / "backups")[0].path

    for name in config.SANDBOX_DIRNAMES:
        assert not (snap / f"Images/{tid}/{name}").exists()
    manifest = json.loads((snap / backup.MANIFEST_NAME).read_text())
    assert not [k for k in manifest["files"] if "/astrowizard/" in k]


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
