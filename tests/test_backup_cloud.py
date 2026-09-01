"""Backing up to a destination with no filesystem (issue #93).

This is the file that proves the de-Path refactor actually landed. Every other
pooled test passes a `Path` and would keep passing if `pooled.py` still stat'd
the destination behind the seam; here the destination is a bucket, so any
surviving `Path(...)`/`is_dir()`/`read_bytes()` on it fails loudly.

The backend is the **real** `S3Backend` — only its boto3 client is faked — so the
whole stack runs: destination parsing → `backend_for` → adapter → transport.
"""
import pytest

from m110 import backup, config, objects
from m110.backup import pooled
from m110.backup.backends.s3 import S3Backend
from tests._fake_s3 import FakeS3Client
from tests._helpers import seed_capture, seed_root, seed_sandbox

DEST = "s3://bucket/backups"


@pytest.fixture
def cloud(monkeypatch):
    """Route every S3Backend in the process at one in-memory bucket."""
    client = FakeS3Client("bucket")
    monkeypatch.setattr(S3Backend, "_build_client", lambda self: client)
    return client


def _store(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    slug, tid = seed_capture(root)
    objects.write_journal(slug, "# notes\nAuthored, irreplaceable.\n")
    return root, slug, tid


def _snap(**kw):
    return backup.create_snapshot(backup.BackupOptions(destination=DEST, **kw))


# ── the round trip ──────────────────────────────────────────────────────────

def test_backup_verify_and_restore_against_a_bucket(tmp_path, monkeypatch, cloud):
    _store(tmp_path, monkeypatch)

    res = _snap()
    assert res["format"] == backup.FORMAT_POOLED
    assert res["file_count"] > 0
    assert res["snapshot"].startswith("s3://bucket/backups/M110-Backups/")

    snaps = backup.list_snapshots(DEST)
    assert len(snaps) == 1
    snap = snaps[0]
    # The point of the refactor: reachable with no filesystem path at all.
    assert snap.path is None
    assert snap.ref is not None and snap.ref.key.startswith("snapshots/")
    assert snap.file_count == res["file_count"]

    files = backup.snapshot_files(snap)
    assert files and any(f.endswith("journal.md") for f in files)

    out = tmp_path / "restored"
    r = backup.restore(snap, sorted(files), out)
    assert r["written"] == len(files)
    restored = out / next(f for f in files if f.endswith("journal.md"))
    assert "irreplaceable" in restored.read_text()


def test_a_bucket_gets_no_latest_tree(tmp_path, monkeypatch, cloud):
    """`latest/` is a hardlink tree; object storage has no such concept, so it is
    simply absent rather than silently duplicated as a second full copy."""
    _store(tmp_path, monkeypatch)
    res = _snap()
    assert res["hardlinks"] is False
    assert res["linked"] == 0
    assert not [k for k in cloud.objects if "/latest/" in k]
    # …but the recovery artifacts still travel with the data, since a bag of
    # hash-named blobs is not a backup anyone can get back into.
    assert any(k.endswith("restore.py") for k in cloud.objects)
    assert any(k.endswith("README.txt") for k in cloud.objects)


def test_second_snapshot_uploads_nothing_new(tmp_path, monkeypatch, cloud):
    """Content addressing gives incrementals by construction — the second run
    re-hashes locally and finds every object already there."""
    _store(tmp_path, monkeypatch)
    _snap()
    objects_before = {k for k in cloud.objects if "/objects/" in k}

    second = _snap()

    assert second["objects_new"] == 0
    assert second["bytes_new"] == 0
    # A new manifest and a rewritten state file, but not one new object.
    assert {k for k in cloud.objects if "/objects/" in k} == objects_before
    assert len(backup.list_snapshots(DEST)) == 2


# ── verify depth ────────────────────────────────────────────────────────────

def test_verify_is_shallow_on_a_bucket_but_deep_on_request(tmp_path, monkeypatch,
                                                           cloud):
    """A deep verify over the internet is a full download of the backup, with the
    egress bill to match, for a button a user may press idly — so the default
    follows the destination and the result says which check actually ran."""
    _store(tmp_path, monkeypatch)
    _snap()
    snap = backup.list_snapshots(DEST)[0]

    cloud.calls.clear()
    shallow = backup.verify(snap)
    assert shallow["ok"] is True and shallow["deep"] is False
    assert cloud.calls.get("get_object", 0) <= 1        # the manifest itself only

    cloud.calls.clear()
    deep = backup.verify(snap, deep=True)
    assert deep["ok"] is True and deep["deep"] is True
    assert cloud.calls.get("get_object", 0) > 1         # every object read back


def test_shallow_verify_still_catches_a_damaged_object(tmp_path, monkeypatch, cloud):
    """Presence-and-size is weaker than re-hashing, but a size is a function of
    the bytes — so truncation is caught, and the tier is honest about the rest."""
    _store(tmp_path, monkeypatch)
    _snap()
    snap = backup.list_snapshots(DEST)[0]
    obj_key = next(k for k in cloud.objects if "/objects/" in k)
    cloud.objects[obj_key] = b""                        # truncated in place

    result = backup.verify(snap)
    assert result["ok"] is False
    assert result["mismatched"]


# ── scope ───────────────────────────────────────────────────────────────────

def test_essentials_scope_leaves_the_frames_at_home(tmp_path, monkeypatch, cloud):
    root, slug, tid = _store(tmp_path, monkeypatch)

    everything = _snap(scope=backup.SCOPE_EVERYTHING)
    essentials = _snap(scope=backup.SCOPE_ESSENTIALS)

    assert essentials["file_count"] < everything["file_count"]
    newest = backup.list_snapshots(DEST)[0]         # newest first
    assert newest.timestamp == essentials["timestamp"]
    narrow = backup.snapshot_files(newest)
    assert not any("/lights/" in f for f in narrow)
    assert any(f.endswith("journal.md") for f in narrow)


def test_narrowing_scope_does_not_delete_the_frames_yet(tmp_path, monkeypatch, cloud):
    """The safety property behind shipping the tier without a byte estimate:
    `sweep_objects` marks from *every surviving manifest*, so the frames stay
    referenced by the older, wider snapshot until retention prunes it."""
    _store(tmp_path, monkeypatch)
    _snap(scope=backup.SCOPE_EVERYTHING)
    objects_before = len([k for k in cloud.objects if "/objects/" in k])

    _snap(scope=backup.SCOPE_ESSENTIALS)
    backup.sweep_objects(DEST, now=9_999_999_999)       # well past the grace window

    assert len([k for k in cloud.objects if "/objects/" in k]) == objects_before


def test_the_snapshot_records_its_own_scope(tmp_path, monkeypatch, cloud):
    """A restore has to be able to say what a backup did and didn't contain."""
    _store(tmp_path, monkeypatch)
    _snap(scope=backup.SCOPE_ESSENTIALS)
    manifest = pooled.read_manifest(backup.list_snapshots(DEST)[0])
    assert manifest["scope"] == backup.SCOPE_ESSENTIALS


# ── retention ───────────────────────────────────────────────────────────────

def test_min_free_retention_is_skipped_where_there_is_no_volume(tmp_path, monkeypatch,
                                                                cloud):
    """`free_bytes` on a bucket is 0 by necessity, which as a min-free reading
    would prune a cloud history down to a single snapshot on every run."""
    _store(tmp_path, monkeypatch)
    _snap()
    _snap()
    assert len(backup.list_snapshots(DEST)) == 2

    result = backup.apply_retention(DEST, min_free_gb=1_000_000)

    assert result["pruned"] == 0
    assert len(backup.list_snapshots(DEST)) == 2


def test_keep_n_retention_still_applies(tmp_path, monkeypatch, cloud):
    _store(tmp_path, monkeypatch)
    _snap()
    _snap()
    _snap()

    backup.apply_retention(DEST, keep=1)

    assert len(backup.list_snapshots(DEST)) == 1


# ── uploads ─────────────────────────────────────────────────────────────────

def test_parallel_uploads_store_exactly_what_serial_would(tmp_path, monkeypatch):
    """`parallel_puts` is pure throughput: it must not change a single byte of
    what lands, or which manifest describes it."""
    def run(width, sub):
        client = FakeS3Client("bucket")
        monkeypatch.setattr(S3Backend, "_build_client", lambda self: client)
        monkeypatch.setattr("m110.backup.backends.s3.PARALLEL_PUTS", width)
        _store(tmp_path / sub, monkeypatch)
        res = _snap()
        stored = {k.rsplit("/", 1)[-1] for k in client.objects if "/objects/" in k}
        manifest = pooled.read_manifest(backup.list_snapshots(DEST)[0])
        return res["file_count"], stored, {r: m["sha256"]
                                           for r, m in manifest["files"].items()}

    serial = run(1, "a")
    parallel = run(8, "b")

    assert serial == parallel


def test_an_upload_failure_stops_the_snapshot_before_the_manifest(tmp_path,
                                                                  monkeypatch, cloud):
    """The invariant — a manifest exists ⇒ every object it names exists — has to
    survive uploads that run concurrently, which is what `_drain` is for."""
    _store(tmp_path, monkeypatch)
    boom = {"n": 0}
    real = FakeS3Client.upload_file

    def flaky(self, filename, bucket, key, **kw):
        boom["n"] += 1
        if boom["n"] == 2:
            raise OSError("network went away")
        return real(self, filename, bucket, key, **kw)

    monkeypatch.setattr(FakeS3Client, "upload_file", flaky)
    with pytest.raises(Exception):
        _snap()

    assert not [k for k in cloud.objects if "/snapshots/" in k]
    assert backup.list_snapshots(DEST) == []
