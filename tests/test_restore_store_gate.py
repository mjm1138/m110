"""The store-version gate on a restore into the store (BUGS #40d, a 1.0 blocker).
Temp store → temp destination only."""
import dataclasses

import pytest

from m110 import backup, config, migrate
from m110.backup import storegate
from tests._helpers import seed_capture, seed_root


def _stamp(root, version):
    (root / config.INTERNAL_DIRNAME / migrate.VERSION_FILE).write_text(str(version))


def _v5_snapshot_of_a_device_stack(tmp_path, monkeypatch):
    """A store backed up at v5 (stack under `seestar-stacks/`), then upgraded to v6,
    then the stack lost. Returns (root, snapshot, the snapshot's rel, the v6 path)."""
    root = seed_root(tmp_path, monkeypatch)
    _slug, tid = seed_capture(root)
    legacy = root / "Images" / tid / migrate.LEGACY_DEVICE_STACKS / "Stacked_30_x.fit"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"STACK")
    _stamp(root, 5)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    snap = backup.list_snapshots(dest)[0]
    assert snap.store_version == "5"
    assert migrate.migrate_store(root)                      # the upgrade to v6
    current = root / "Images" / tid / migrate.DEVICE_STACKS / "Stacked_30_x.fit"
    assert current.read_bytes() == b"STACK" and not legacy.parent.exists()
    current.unlink()                                        # …and the stack is lost
    return root, snap, legacy.relative_to(root).as_posix(), current


@pytest.mark.parametrize("snap_v,expected", [
    ("6", storegate.SAME), (6, storegate.SAME), ("5", storegate.OLDER),
    ("7", storegate.NEWER), (None, storegate.UNKNOWN), ("", storegate.UNKNOWN),
    ("v5", storegate.UNKNOWN)])
def test_store_compat(snap_v, expected):
    assert storegate.store_compat(snap_v, current=6) == expected


def test_a_partial_restore_from_an_older_store_is_migrated(tmp_path, monkeypatch):
    root, snap, old_rel, current = _v5_snapshot_of_a_device_stack(tmp_path, monkeypatch)
    res = backup.restore_into_store(snap, [old_rel], root=root)
    assert res["written"] == 1 and res["migrated"] is True
    assert current.read_bytes() == b"STACK"                 # where v6 reads it
    assert not (root / old_rel).exists()
    assert (root / config.INTERNAL_DIRNAME / migrate.VERSION_FILE).read_text() == "6"


def test_without_the_gate_the_old_file_is_stranded(tmp_path, monkeypatch):
    """The bug itself: a plain restore puts the file where nothing in v6 reads it,
    and the store's stamp says there's nothing left to migrate."""
    root, snap, old_rel, current = _v5_snapshot_of_a_device_stack(tmp_path, monkeypatch)
    backup.restore(snap, [old_rel], root)
    assert (root / old_rel).is_file() and not current.exists()
    assert migrate.migrate_store(root) is False


def test_a_full_restore_of_the_older_stamp_still_lands_current(tmp_path, monkeypatch):
    root, snap, old_rel, current = _v5_snapshot_of_a_device_stack(tmp_path, monkeypatch)
    stamp_rel = f"{config.INTERNAL_DIRNAME}/{migrate.VERSION_FILE}"
    res = backup.restore_into_store(snap, [old_rel, stamp_rel], root=root,
                                    overwrite=True)
    assert res["migrated"] is True and current.is_file()
    assert (root / stamp_rel).read_text() == "6"


def test_a_snapshot_from_a_newer_store_is_refused(tmp_path, monkeypatch):
    root, snap, old_rel, current = _v5_snapshot_of_a_device_stack(tmp_path, monkeypatch)
    newer = dataclasses.replace(snap, store_version=str(migrate.STORE_VERSION + 1))
    with pytest.raises(backup.BackupError, match="newer version of M110"):
        backup.restore_into_store(newer, [old_rel], root=root)
    assert not (root / old_rel).exists()                     # nothing written
    # …but extracting it to a folder is still allowed
    out = tmp_path / "out"
    assert backup.restore(newer, [old_rel], out)["written"] == 1


def test_a_same_version_restore_runs_no_migration(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    _slug, tid = seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    snap = backup.list_snapshots(dest)[0]
    assert storegate.store_compat(snap.store_version) == storegate.SAME
    monkeypatch.setattr(migrate, "migrate_restored",
                        lambda root: pytest.fail("migrated a same-version restore"))
    rel = f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"
    (root / rel).unlink()
    res = backup.restore_into_store(snap, [rel], root=root)
    assert res["written"] == 1 and res["migrated"] is False


def test_an_unversioned_snapshot_is_migrated(tmp_path, monkeypatch):
    root, snap, old_rel, current = _v5_snapshot_of_a_device_stack(tmp_path, monkeypatch)
    unknown = dataclasses.replace(snap, store_version=None)
    res = backup.restore_into_store(unknown, [old_rel], root=root)
    assert res["migrated"] is True and current.is_file()


def test_migrate_restored_leaves_a_current_store_alone(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    lib = (root / config.INTERNAL_DIRNAME / "library.toml").read_text()
    assert migrate.migrate_restored(root) is False
    assert (root / config.INTERNAL_DIRNAME / "library.toml").read_text() == lib


def test_restore_dialog_refuses_a_newer_snapshot_into_the_store(tmp_path, monkeypatch, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from m110.ui import restore_dialog
    root = seed_root(tmp_path, monkeypatch)
    _slug, tid = seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    dlg = restore_dialog.RestoreDialog(str(dest))
    try:
        snap = dlg._current_snapshot()
        dlg._snap_combo.setItemData(0, dataclasses.replace(snap, store_version="99"))
        top = dlg._tree.topLevelItem(0)
        top.setCheckState(0, Qt.Checked)
        dlg._to_store.setChecked(True)
        warned = []
        monkeypatch.setattr(QMessageBox, "warning",
                            staticmethod(lambda *a, **k: warned.append(a[2])))
        monkeypatch.setattr(dlg, "_run", lambda *a, **k: pytest.fail("restore ran"))
        dlg._restore_btn.click()
        assert warned and "newer version of M110" in warned[0]
    finally:
        dlg.deleteLater()
        qapp.processEvents()


def test_restore_dialog_routes_a_store_restore_through_the_gate(tmp_path, monkeypatch, qapp):
    from PySide6.QtCore import Qt
    from m110.ui import restore_dialog
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    dlg = restore_dialog.RestoreDialog(str(dest))
    try:
        dlg._tree.topLevelItem(0).setCheckState(0, Qt.Checked)
        dlg._to_store.setChecked(True)
        calls = []
        monkeypatch.setattr(backup, "restore_into_store",
                            lambda *a, **k: calls.append(("gate", k.get("root"))) or {})
        monkeypatch.setattr(backup, "restore",
                            lambda *a, **k: calls.append(("plain", None)) or {})
        monkeypatch.setattr(dlg, "_run", lambda fn, *a, **k: fn())
        monkeypatch.setattr(restore_dialog.QMessageBox, "question",
                            staticmethod(lambda *a, **k: restore_dialog.QMessageBox.No))
        dlg._restore_btn.click()
        assert calls == [("gate", config.DATA_ROOT)]
    finally:
        dlg.deleteLater()
        qapp.processEvents()
