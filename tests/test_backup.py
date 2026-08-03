"""Library backup engine — snapshots, hardlink incrementals, verify, restore,
retention. All on a temp store → temp destination (never live data)."""
import json
import os
from datetime import datetime, timedelta

from m110 import backup, config, objects
from tests._helpers import seed_capture, seed_root, seed_sandbox


def _age_newest(dest, when: datetime):
    """Rename the newest snapshot dir so `list_snapshots` reports `created == when`
    (its timestamp is parsed from the dir name), letting tests control snapshot age."""
    snap = backup.list_snapshots(dest)[0].path
    snap.rename(snap.with_name(when.strftime(backup.TIMESTAMP_FMT)))


def test_snapshot_mirrors_store_and_excludes_derived(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "# notes\nAuthored.\n")   # an authored file
    seed_sandbox(tid)                                  # a siril sandbox to exclude
    dest = tmp_path / "backups"

    res = backup.create_snapshot(backup.BackupOptions(destination=dest))
    snap = backup.list_snapshots(dest)[0].path

    # included: the raw light + the journal + library.toml
    light_rel = f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"
    assert (snap / light_rel).is_file()
    assert (snap / f"{config.INTERNAL_DIRNAME}/library.toml").is_file()
    assert list((snap / "Objects").rglob("journal.md"))
    # excluded: derived rollups, renders, sessions.jsonl, and the siril sandbox
    assert not (snap / config.INTERNAL_DIRNAME / "derived").exists()
    assert not (snap / config.INTERNAL_DIRNAME / "sessions.jsonl").exists()
    assert not (snap / f"Images/{tid}/siril").exists()
    # manifest present, with a checksum for the light frame
    manifest = json.loads((snap / backup.MANIFEST_NAME).read_text())
    assert manifest["files"][light_rel]["sha256"]
    assert res["file_count"] == manifest["file_count"] >= 2


def test_incremental_hardlinks_unchanged_files(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"

    backup.create_snapshot(backup.BackupOptions(destination=dest))
    second = backup.create_snapshot(backup.BackupOptions(destination=dest))
    snaps = backup.list_snapshots(dest)
    assert len(snaps) == 2

    light_rel = f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"
    a = (snaps[0].path / light_rel).stat()
    b = (snaps[1].path / light_rel).stat()
    assert a.st_ino == b.st_ino                # same inode → hardlinked
    assert second["linked"] >= 1
    assert second["bytes_new"] == 0            # nothing changed → no new bytes


def test_changed_file_recopied_others_still_linked(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    jp = objects.write_journal(slug, "# notes\nfirst.\n")
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))

    objects.write_journal(slug, "# notes\nfirst.\nEdited — changes size + mtime.\n")
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    snaps = backup.list_snapshots(dest)

    jrel = os.path.relpath(jp, root)
    light_rel = f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"
    # journal changed → distinct inodes; light unchanged → shared inode
    assert (snaps[0].path / jrel).stat().st_ino != (snaps[1].path / jrel).stat().st_ino
    assert (snaps[0].path / light_rel).stat().st_ino == (snaps[1].path / light_rel).stat().st_ino


def test_verify_detects_corruption_and_missing(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    snap = backup.list_snapshots(dest)[0].path

    assert backup.verify(snap)["ok"] is True

    manifest = json.loads((snap / backup.MANIFEST_NAME).read_text())
    rels = list(manifest["files"].keys())
    (snap / rels[0]).write_bytes(b"corrupted")     # flip contents
    (snap / rels[1]).unlink()                        # delete a file
    res = backup.verify(snap)
    assert res["ok"] is False
    assert rels[0] in res["mismatched"]
    assert rels[1] in res["missing"]


def test_restore_to_folder_and_conflict_preview(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    snap = backup.list_snapshots(dest)[0].path
    light_rel = f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"

    out = tmp_path / "restore-out"
    prev = backup.preview_restore(snap, [light_rel], out)
    assert light_rel in prev["creates"] and not prev["overwrites"]
    backup.restore(snap, [light_rel], out)
    assert (out / light_rel).read_bytes() == (snap / light_rel).read_bytes()

    # restoring a whole subtree into the store flags the existing file as an overwrite
    prev2 = backup.preview_restore(snap, [f"Images/{tid}/lights"], root)
    assert light_rel in prev2["overwrites"]
    r = backup.restore(snap, [light_rel], root)        # default: don't overwrite
    assert r["written"] == 0 and r["skipped"] == 1
    r2 = backup.restore(snap, [light_rel], root, overwrite=True)
    assert r2["written"] == 1


def test_retention_keep_n_never_deletes_last(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"
    for _ in range(3):
        backup.create_snapshot(backup.BackupOptions(destination=dest))
    assert len(backup.list_snapshots(dest)) == 3

    res = backup.apply_retention(dest, keep=2)
    assert res["pruned"] == 1
    snaps = backup.list_snapshots(dest)
    assert len(snaps) == 2                          # oldest dropped, newest kept
    # a file shared with a surviving snapshot is still intact
    light_rel = f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"
    assert (snaps[0].path / light_rel).is_file()

    # keep=1 leaves exactly one; keep below that never nukes the last
    backup.apply_retention(dest, keep=1)
    assert len(backup.list_snapshots(dest)) == 1


def test_options_default_min_free_and_explicit_off(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    dest = tmp_path / "backups"

    # Unconfigured → keep all snapshots + default 100 GB free floor.
    opts = backup.options_from_settings(dest)
    assert opts.retention_keep is None
    assert opts.min_free_gb == backup.DEFAULT_MIN_FREE_GB

    # Explicit 0 means "off" (distinct from unset → no space-based pruning).
    config.save_setting(backup.SETTING_MIN_FREE, 0)
    assert backup.options_from_settings(dest).min_free_gb is None


def test_incomplete_snapshot_ignored_and_swept(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))

    store_root = backup.store_backup_root(dest)
    leftover = store_root / f"2020-01-01_000000_000000{backup.INCOMPLETE_SUFFIX}"
    leftover.mkdir()
    (leftover / "junk").write_text("partial")

    assert all(not s.path.name.endswith(backup.INCOMPLETE_SUFFIX)
               for s in backup.list_snapshots(dest))    # not listed
    assert backup.sweep_incomplete(dest) == 1
    assert not leftover.exists()


def test_hardlink_unsupported_falls_back_to_copy(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"

    # Simulate a destination filesystem without hardlink support.
    monkeypatch.setattr(os, "link",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no links")))
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    second = backup.create_snapshot(backup.BackupOptions(destination=dest))
    snaps = backup.list_snapshots(dest)

    assert snaps[0].hardlinks is False
    light_rel = f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"
    # distinct inodes (full copies), but both snapshots verify intact
    assert (snaps[0].path / light_rel).stat().st_ino != (snaps[1].path / light_rel).stat().st_ino
    assert backup.verify(snaps[1].path)["ok"] is True
    assert second["linked"] == 0


def test_probe_destination_reports_capabilities(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"

    # Missing folder: reported, not raised — the dialog shows the reason.
    missing = backup.probe_destination(dest)
    assert (missing.exists, missing.writable, missing.snapshot_count) == (False, False, 0)
    assert missing.error

    # A real, empty destination: writable + hardlinks, and the answer is available
    # *before* any snapshot exists (the point of the probe — issue #92).
    dest.mkdir()
    info = backup.probe_destination(dest)
    assert (info.exists, info.writable, info.hardlinks) == (True, True, True)
    assert info.snapshot_count == 0 and info.newest is None
    assert info.free_bytes and info.free_bytes > 0
    # Probing must not create the backup tree for a destination the user hasn't
    # committed to, and must leave no probe files behind.
    assert not backup.store_backup_root(dest).exists()
    assert list(dest.iterdir()) == []

    backup.create_snapshot(backup.BackupOptions(destination=dest))
    after = backup.probe_destination(dest)
    assert after.snapshot_count == 1 and after.newest is not None


def test_probe_destination_detects_no_hardlink_support(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    dest = tmp_path / "backups"
    dest.mkdir()
    monkeypatch.setattr(os, "link",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no links")))

    info = backup.probe_destination(dest)
    assert info.exists and info.writable
    assert info.hardlinks is False
    assert list(dest.iterdir()) == []       # probe files cleaned up on failure too


def test_due_for_auto_backup_uses_interval(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    config.save_setting(backup.SETTING_AUTO, True)

    # Default interval is now 12h: a 6h-old snapshot is not due; a 13h-old one is.
    _age_newest(dest, datetime.now() - timedelta(hours=6))
    assert backup.due_for_auto_backup(dest) is False
    _age_newest(dest, datetime.now() - timedelta(hours=13))
    assert backup.due_for_auto_backup(dest) is True

    # Disabled → never due, even when stale.
    config.save_setting(backup.SETTING_AUTO, False)
    assert backup.due_for_auto_backup(dest) is False


def test_due_for_scheduled_backup_daily_at_02(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    backup.create_snapshot(backup.BackupOptions(destination=dest))
    config.save_setting(backup.SETTING_AUTO, True)

    today_0200 = datetime.now().replace(hour=2, minute=0, second=0, microsecond=0)

    # Stale snapshot (2 days old), clock past 02:00 → due.
    _age_newest(dest, today_0200 - timedelta(days=2))
    assert backup.due_for_scheduled_backup(dest, now=today_0200 + timedelta(hours=1)) is True

    # Before the scheduled hour → not due.
    assert backup.due_for_scheduled_backup(dest, now=today_0200 - timedelta(hours=1)) is False

    # Already backed up since 02:00 today → not due (once per day).
    _age_newest(dest, today_0200 + timedelta(minutes=10))
    assert backup.due_for_scheduled_backup(dest, now=today_0200 + timedelta(hours=5)) is False

    # Launch backup 30 min before 02:00 → min-age (interval) guard skips 02:00.
    _age_newest(dest, today_0200 - timedelta(minutes=30))
    assert backup.due_for_scheduled_backup(dest, now=today_0200 + timedelta(minutes=30)) is False

    # Disabled → never due.
    config.save_setting(backup.SETTING_AUTO, False)
    assert backup.due_for_scheduled_backup(dest, now=today_0200 + timedelta(hours=1)) is False
