"""Pooled (content-addressed) backups — object reuse, the manifest-last
invariant, GC, cross-format retention, and recovery without M110.

All on a temp store → temp destination (never live data).
"""
import gzip
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

import pytest

from m110 import backup, config, objects
from m110.backup import pooled
from tests._helpers import seed_capture, seed_root, seed_sandbox


def _use_pooled():
    config.save_setting(backup.SETTING_FORMAT, backup.FORMAT_POOLED)


def _snap(dest, **kw):
    return backup.create_snapshot(backup.BackupOptions(destination=dest, **kw))


def _store_root(dest):
    return backup.store_backup_root(dest)


def _object_files(dest):
    base = _store_root(dest) / "objects"
    return sorted(p.name for p in base.rglob("*") if p.is_file())


def _light_rel(tid):
    return f"Images/{tid}/lights/Light_{tid}_30.0s_LP_20260529-010101.fit"


# ── writing ─────────────────────────────────────────────────────────────────

def test_pooled_snapshot_stores_objects_and_a_manifest(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "# notes\nAuthored.\n")
    seed_sandbox(tid)
    dest = tmp_path / "backups"
    _use_pooled()

    res = _snap(dest)
    assert res["format"] == backup.FORMAT_POOLED
    assert res["objects_new"] >= 2

    snaps = backup.list_snapshots(dest)
    assert len(snaps) == 1 and snaps[0].format == backup.FORMAT_POOLED
    manifest = pooled.read_manifest(snaps[0].path)
    assert manifest["format"] == 2
    assert manifest["files"][_light_rel(tid)]["sha256"]
    # same scope rules as mirrored: regenerable + working areas stay out
    assert not any(k.startswith(f"{config.INTERNAL_DIRNAME}/derived")
                   for k in manifest["files"])
    assert not any(f"Images/{tid}/siril" in k for k in manifest["files"])
    # every object the manifest names is present, and named by its own hash
    for meta in manifest["files"].values():
        assert (_store_root(dest) / "objects" / meta["sha256"][:2] /
                meta["sha256"][2:4] / meta["sha256"]).is_file()


def test_second_run_stores_no_new_objects(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    _use_pooled()

    _snap(dest)
    before = _object_files(dest)
    second = _snap(dest)

    assert second["objects_new"] == 0
    assert second["bytes_new"] == 0
    assert _object_files(dest) == before          # dedup by content, not by link
    assert len(backup.list_snapshots(dest)) == 2


def test_changed_file_adds_an_object_and_the_old_snapshot_still_restores(tmp_path, monkeypatch):
    """The property that matters: an older snapshot is not a diff to replay. It
    restores its own contents, independently, forever."""
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "# notes\nfirst.\n")
    dest = tmp_path / "backups"
    _use_pooled()

    _snap(dest)
    objects.write_journal(slug, "# notes\nsecond — different bytes.\n")
    second = _snap(dest)
    assert second["objects_new"] == 1             # only the journal changed

    old, new = backup.list_snapshots(dest)[1], backup.list_snapshots(dest)[0]
    out_old, out_new = tmp_path / "old", tmp_path / "new"
    jrel = next(k for k in backup.snapshot_files(old.path) if k.endswith("journal.md"))
    backup.restore(old.path, [jrel], out_old)
    backup.restore(new.path, [jrel], out_new)

    assert "first." in (out_old / jrel).read_text()
    assert "second" in (out_new / jrel).read_text()
    # the raw frame is shared, not duplicated
    assert (out_old / jrel).read_bytes() != (out_new / jrel).read_bytes()


def test_cancelled_run_writes_no_manifest_and_its_objects_are_reused(tmp_path, monkeypatch):
    """The invariant: a manifest exists ⇒ every object it names exists. Because
    the manifest is written last, a cancelled run leaves objects but no snapshot —
    and since objects are addressed by content, the next run finds them, so an
    interrupted first sync resumes for free instead of starting over."""
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    _use_pooled()

    calls = {"n": 0}

    def cancel_after_one():
        calls["n"] += 1
        return calls["n"] > 2       # let a file or two through, then stop

    res = _snap_cancelled(dest, cancel_after_one)
    assert res == {"cancelled": True}
    assert backup.list_snapshots(dest) == []                    # no snapshot
    orphans = _object_files(dest)
    assert orphans                                              # but objects landed

    full = _snap(dest)
    assert full["objects_new"] >= 1
    # nothing was re-stored twice: every orphan is still there, same names
    assert set(orphans).issubset(set(_object_files(dest)))
    assert backup.verify(backup.list_snapshots(dest)[0].path)["ok"] is True


def _snap_cancelled(dest, should_cancel):
    return backup.create_snapshot(backup.BackupOptions(destination=dest),
                                  should_cancel=should_cancel)


def test_a_lying_hash_cache_is_caught_by_the_stored_size(tmp_path, monkeypatch):
    """The one hazard of caching hashes is a stale *hit*. An object's size is a
    function of its bytes, so comparing the size the destination already has for
    that hash catches it — and it costs nothing, since the sizes come back with
    the object listing we need anyway."""
    from m110.backup.hashcache import HashCache

    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "# notes\na journal of a different length.\n")
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)

    files = backup.snapshot_files(backup.list_snapshots(dest)[0].path)
    light, jrel = _light_rel(tid), next(k for k in files if k.endswith("journal.md"))
    assert files[light]["size"] != files[jrel]["size"]

    # Poison the cache: claim the light frame hashes to the journal's object.
    src = root / light
    with HashCache() as cache:
        cache.remember(src, src.stat(), files[jrel]["sha256"])

    _snap(dest)
    again = backup.snapshot_files(backup.list_snapshots(dest)[0].path)
    assert again[light]["sha256"] == files[light]["sha256"]      # corrected
    assert backup.verify(backup.list_snapshots(dest)[0].path)["ok"] is True


# ── verify ──────────────────────────────────────────────────────────────────

def test_verify_detects_a_damaged_or_missing_object(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)
    snap = backup.list_snapshots(dest)[0]

    assert backup.verify(snap.path)["ok"] is True

    files = backup.snapshot_files(snap.path)
    rels = sorted(files)
    obj = (_store_root(dest) / "objects" / files[rels[0]]["sha256"][:2] /
           files[rels[0]]["sha256"][2:4] / files[rels[0]]["sha256"])
    os.chmod(obj, 0o644)
    obj.write_bytes(b"corrupted")
    res = backup.verify(snap.path)
    assert res["ok"] is False and rels[0] in res["mismatched"]

    obj.unlink()
    assert rels[0] in backup.verify(snap.path)["missing"]


# ── the browsable latest/ tree ──────────────────────────────────────────────

def test_latest_tree_mirrors_the_newest_backup_without_extra_bytes(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "# notes\nfirst.\n")
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)

    latest = _store_root(dest) / "latest"
    light = latest / _light_rel(tid)
    assert light.is_file()
    files = backup.snapshot_files(backup.list_snapshots(dest)[0].path)
    sha = files[_light_rel(tid)]["sha256"]
    obj = _store_root(dest) / "objects" / sha[:2] / sha[2:4] / sha
    assert light.stat().st_ino == obj.stat().st_ino     # shared inode, no copy

    # a changed file is relinked; an removed one disappears from latest/
    objects.write_journal(slug, "# notes\nsecond.\n")
    _snap(dest)
    jrel = os.path.relpath(config.DATA_ROOT / "Objects", root)
    assert "second." in next((latest / jrel).rglob("journal.md")).read_text()


def test_latest_tree_is_absent_when_the_destination_cannot_link(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    _use_pooled()
    monkeypatch.setattr(os, "link",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no links")))

    res = _snap(dest)
    assert res["hardlinks"] is False and res["linked"] == 0
    assert not (_store_root(dest) / "latest").exists()
    # …and the backup is still complete and restorable, which is the point.
    assert backup.verify(backup.list_snapshots(dest)[0].path)["ok"] is True


# ── retention + object sweep ────────────────────────────────────────────────

def test_pruning_a_snapshot_sweeps_only_its_unshared_objects(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "# notes\nv1.\n")
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)
    v1 = {m["sha256"] for m in
          backup.snapshot_files(backup.list_snapshots(dest)[0].path).values()}

    objects.write_journal(slug, "# notes\nv2 — new bytes.\n")
    _snap(dest)
    v2 = {m["sha256"] for m in
          backup.snapshot_files(backup.list_snapshots(dest)[0].path).values()}
    only_v1 = v1 - v2
    assert only_v1                                   # the old journal's object

    res = backup.apply_retention(dest, keep=1)
    assert res["pruned"] == 1
    # the grace window protects freshly written objects from a concurrent run
    assert res["swept"] == 0
    assert set(_object_files(dest)) >= only_v1

    swept = backup.sweep_objects(dest, grace_seconds=0)
    assert swept["swept"] == len(only_v1)
    remaining = set(_object_files(dest))
    assert remaining == v2                           # shared frames untouched
    assert backup.verify(backup.list_snapshots(dest)[0].path)["ok"] is True


def test_sweep_leaves_recent_unreferenced_objects_alone(tmp_path, monkeypatch):
    """A run happening right now writes objects no manifest references yet.
    Sweeping them would corrupt it, so recency is the guard."""
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)

    store = _store_root(dest)
    stray = store / "objects" / "ff" / "ee" / ("f" * 64)
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"in flight")

    assert backup.sweep_objects(dest)["swept"] == 0          # 24h grace
    assert stray.is_file()
    assert backup.sweep_objects(dest, grace_seconds=0)["swept"] == 1
    assert not stray.exists()


def test_retention_spans_both_formats_and_keeps_the_last(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"

    config.save_setting(backup.SETTING_FORMAT, backup.FORMAT_MIRRORED)
    _snap(dest)
    _use_pooled()
    _snap(dest)
    snaps = backup.list_snapshots(dest)
    assert {s.format for s in snaps} == {backup.FORMAT_MIRRORED, backup.FORMAT_POOLED}

    backup.apply_retention(dest, keep=1)
    left = backup.list_snapshots(dest)
    assert len(left) == 1 and left[0].format == backup.FORMAT_POOLED   # newest kept
    backup.apply_retention(dest, keep=1)
    assert len(backup.list_snapshots(dest)) == 1        # never deletes the last


def test_mirrored_snapshots_stay_readable_beside_pooled_ones(tmp_path, monkeypatch):
    """Switching format must never strand a backup you already have."""
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"

    config.save_setting(backup.SETTING_FORMAT, backup.FORMAT_MIRRORED)
    _snap(dest)
    _use_pooled()
    _snap(dest)

    for snap in backup.list_snapshots(dest):
        assert backup.verify(snap.path)["ok"] is True
        assert _light_rel(tid) in backup.snapshot_files(snap.path)
        out = tmp_path / f"out-{snap.format}"
        backup.restore(snap.path, [_light_rel(tid)], out)
        assert (out / _light_rel(tid)).read_bytes() == \
            (root / _light_rel(tid)).read_bytes()


# ── format resolution ───────────────────────────────────────────────────────

def test_format_defaults_to_mirrored_and_follows_the_destination(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"

    assert backup.preferred_format() == backup.FORMAT_MIRRORED   # the default
    assert backup.resolve_format(dest) == (backup.FORMAT_MIRRORED, False)
    assert _snap(dest)["format"] == backup.FORMAT_MIRRORED

    # An unset preference on a destination that already holds mirrored snapshots
    # keeps writing mirrored — the destination's own state is the first answer.
    assert backup.detect_format(dest) == backup.FORMAT_MIRRORED
    assert backup.resolve_format(dest)[0] == backup.FORMAT_MIRRORED


def test_a_destination_without_hardlinks_forces_pooled_and_persists_it(tmp_path, monkeypatch):
    """The #92 case. Mirrored on a link-less destination means a full copy every
    night; rather than let that happen quietly, switch and remember."""
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"
    dest.mkdir()
    monkeypatch.setattr(os, "link",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no links")))

    fmt, forced = backup.resolve_format(dest)
    assert (fmt, forced) == (backup.FORMAT_POOLED, True)
    # resolve_format alone is read-only — it reports, it doesn't rewrite settings
    assert config.get_setting(backup.SETTING_FORMAT) is None

    assert _snap(dest)["format"] == backup.FORMAT_POOLED
    assert config.get_setting(backup.SETTING_FORMAT) == backup.FORMAT_POOLED


def test_two_backups_cannot_run_at_once(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    seed_capture(root)
    dest = tmp_path / "backups"

    def reentrant():
        with pytest.raises(backup.BackupError, match="already running"):
            _snap(dest)
        return False

    _snap_cancelled(dest, reentrant)


# ── recovery without M110 ───────────────────────────────────────────────────

def test_recovery_artifacts_describe_the_backup_in_plain_form(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)
    store = _store_root(dest)

    index = (store / "INDEX.tsv").read_text()
    assert _light_rel(tid) in index                      # greppable, no tools
    assert (store / "README.txt").is_file()

    mirror = json.loads(gzip.decompress((store / "latest-manifest.json.gz").read_bytes()))
    live = pooled.read_manifest(backup.list_snapshots(dest)[0].path)
    assert mirror["files"] == live["files"]              # full fidelity, not a summary


def test_restore_script_rebuilds_the_tree_with_only_the_standard_library(tmp_path, monkeypatch):
    """`objects/` alone is a bag of hash-named blobs. The embedded script is what
    keeps the backup recoverable when M110 isn't there to read it."""
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)
    store = _store_root(dest)
    out = tmp_path / "hand-restore"

    proc = subprocess.run(
        [sys.executable, "-S", str(store / "restore.py"),
         str(store / "latest-manifest.json.gz"), str(out)],
        capture_output=True, text=True, cwd=tmp_path, env={"PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr

    restored = out / _light_rel(tid)
    assert restored.read_bytes() == (root / _light_rel(tid)).read_bytes()
    assert os.access(restored, os.W_OK)      # restores are editable; objects aren't


def test_restore_script_honours_a_path_prefix(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "# notes\nAuthored.\n")
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)
    store = _store_root(dest)
    out = tmp_path / "partial"

    proc = subprocess.run(
        [sys.executable, str(store / "restore.py"),
         str(store / "latest-manifest.json.gz"), str(out), "Objects/"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert (out / "Objects").is_dir()
    assert not (out / "Images").exists()


# ── restore semantics shared with mirrored ──────────────────────────────────

def test_restore_preserves_capture_mtime_not_storage_time(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    src = root / _light_rel(tid)
    old = (datetime.now() - timedelta(days=400)).timestamp()
    os.utime(src, (old, old))
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)

    out = tmp_path / "out"
    backup.restore(backup.list_snapshots(dest)[0].path, [_light_rel(tid)], out)
    assert abs((out / _light_rel(tid)).stat().st_mtime - old) < 2


def test_restore_skips_existing_unless_told_otherwise(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    dest = tmp_path / "backups"
    _use_pooled()
    _snap(dest)
    snap = backup.list_snapshots(dest)[0]
    rel = _light_rel(tid)

    prev = backup.preview_restore(snap.path, [f"Images/{tid}/lights"], root)
    assert rel in prev["overwrites"]
    assert backup.restore(snap.path, [rel], root)["skipped"] == 1
    assert backup.restore(snap.path, [rel], root, overwrite=True)["written"] == 1
