"""The storage-seam contract.

One suite, run against every backend, so an adapter either satisfies the contract
the pooled format relies on or fails here. `S3Backend` (issue #93) plugs into
this list rather than getting a bespoke test file — it runs against
`tests/_fake_s3.FakeS3Client`, so the contract is proved with no AWS SDK
installed and no network.
"""
import os

import pytest

from m110.backup.backends import LocalBackend, MemoryBackend
from m110.backup.backends.s3 import S3Backend

from tests._fake_s3 import FakeS3Client


@pytest.fixture(params=["local", "memory", "s3"])
def backend(request, tmp_path):
    if request.param == "local":
        b = LocalBackend(tmp_path / "M110-Backups" / "store")
    elif request.param == "memory":
        b = MemoryBackend()
    else:
        b = S3Backend("test-bucket", "prefix/M110-Backups/store",
                      client=FakeS3Client("test-bucket"))
    b.ensure_root()
    return b


def _put(backend, key, data: bytes, tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(data)
    backend.put_file(key, src, size=len(data))
    return src


def test_put_then_get_round_trips(backend, tmp_path):
    _put(backend, "objects/ab/cd/abcd", b"hello", tmp_path)
    assert backend.exists("objects/ab/cd/abcd")
    out = tmp_path / "out" / "x.bin"
    backend.get_file("objects/ab/cd/abcd", out)
    assert out.read_bytes() == b"hello"


def test_put_file_is_idempotent(backend, tmp_path):
    """Content addressing means a repeat put is the *same* bytes by definition;
    the backend must not corrupt or duplicate on the second call."""
    _put(backend, "objects/ab/cd/abcd", b"hello", tmp_path)
    _put(backend, "objects/ab/cd/abcd", b"hello", tmp_path)
    assert backend.object_sizes() == {"abcd": 5}


def test_object_sizes_enumerates_the_whole_store_at_once(backend, tmp_path):
    for i, sha in enumerate(("aabb", "ccdd", "eeff")):
        _put(backend, f"objects/{sha[:2]}/{sha[2:4]}/{sha}", b"x" * (i + 1), tmp_path)
    assert backend.object_sizes() == {"aabb": 1, "ccdd": 2, "eeff": 3}


def test_put_bytes_overwrites_and_reads_back(backend):
    backend.put_bytes("state.json", b"{}")
    backend.put_bytes("state.json", b'{"a":1}')
    assert backend.get_bytes("state.json") == b'{"a":1}'


def test_list_keys_reports_size_and_mtime(backend, tmp_path):
    _put(backend, "objects/aa/bb/aabb", b"12345", tmp_path)
    listed = list(backend.list_keys("objects"))
    assert len(listed) == 1
    key, size, mtime = listed[0]
    assert key == "objects/aa/bb/aabb" and size == 5 and mtime > 0


def test_delete_and_delete_many(backend, tmp_path):
    for sha in ("aabb", "ccdd"):
        _put(backend, f"objects/{sha[:2]}/{sha[2:4]}/{sha}", b"x", tmp_path)
    assert backend.delete_many([f"objects/aa/bb/aabb"]) == 1
    assert set(backend.object_sizes()) == {"ccdd"}
    backend.delete("objects/nope/nope/nope")        # missing key is not an error


def test_missing_key_reads_raise(backend):
    with pytest.raises(Exception):
        backend.get_bytes("objects/00/00/nothing")


# ── local-only behaviours ───────────────────────────────────────────────────

def test_local_objects_are_read_only(tmp_path):
    """A `latest/` entry shares the object's inode, so an in-place edit there
    would rewrite content every snapshot referencing it shares. 0444 is the guard."""
    b = LocalBackend(tmp_path / "store")
    b.ensure_root()
    src = tmp_path / "src.bin"
    src.write_bytes(b"immutable")
    b.put_file("objects/aa/bb/aabb", src)
    obj = tmp_path / "store" / "objects" / "aa" / "bb" / "aabb"
    assert not os.access(obj, os.W_OK)
    # …and deleting one still works despite that (Windows refuses read-only unlinks)
    b.delete("objects/aa/bb/aabb")
    assert not obj.exists()


def test_local_get_file_writes_an_editable_copy(tmp_path):
    b = LocalBackend(tmp_path / "store")
    b.ensure_root()
    src = tmp_path / "src.bin"
    src.write_bytes(b"data")
    b.put_file("objects/aa/bb/aabb", src)
    out = tmp_path / "restored.bin"
    b.get_file("objects/aa/bb/aabb", out)
    assert os.access(out, os.W_OK)


def test_local_link_builds_and_prunes_the_latest_tree(tmp_path):
    b = LocalBackend(tmp_path / "store")
    b.ensure_root()
    src = tmp_path / "src.bin"
    src.write_bytes(b"shared")
    b.put_file("objects/aa/bb/aabb", src)

    assert b.link("objects/aa/bb/aabb", "Images/M51/lights/a.fit") is True
    entry = tmp_path / "store" / "latest" / "Images" / "M51" / "lights" / "a.fit"
    obj = tmp_path / "store" / "objects" / "aa" / "bb" / "aabb"
    assert entry.stat().st_ino == obj.stat().st_ino     # no extra bytes

    b.unlink_rel("Images/M51/lights/a.fit")
    assert not entry.exists()
    assert not entry.parent.exists()                    # empty dirs pruned
    b.drop_latest()
    assert not (tmp_path / "store" / "latest").exists()


def test_local_reports_hardlink_capability(tmp_path, monkeypatch):
    b = LocalBackend(tmp_path / "store")
    b.ensure_root()
    assert b.capabilities().hardlinks is True
    monkeypatch.setattr(os, "link",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no links")))
    assert b.capabilities().hardlinks is False
    assert b.link("objects/aa/bb/aabb", "x") is False


def test_memory_backend_stands_in_for_a_link_less_destination():
    b = MemoryBackend()
    assert b.capabilities().hardlinks is False
    assert b.capabilities().free_bytes is None
    assert b.link("objects/aa/bb/aabb", "x") is False


# ── s3-only behaviours ──────────────────────────────────────────────────────
#
# These are the reasons the adapter exists rather than incidental details: each
# one is a cost or a failure mode that only shows up against object storage.

@pytest.fixture
def s3(tmp_path):
    client = FakeS3Client("test-bucket")
    return S3Backend("test-bucket", "prefix/M110-Backups/store", client=client), client


def test_s3_object_sizes_is_one_list_not_a_head_per_object(s3, tmp_path):
    """The whole reason `object_sizes()` is on the seam. Per-file `exists()` on a
    100k-frame library is 100k billed round-trips; this must stay one LIST."""
    backend, client = s3
    src = tmp_path / "src.bin"
    src.write_bytes(b"x")
    for sha in ("aabb", "ccdd", "eeff", "1122", "3344"):
        backend.put_file(f"objects/{sha[:2]}/{sha[2:4]}/{sha}", src)
    client.calls.clear()

    sizes = backend.object_sizes()

    assert set(sizes) == {"aabb", "ccdd", "eeff", "1122", "3344"}
    assert client.calls.get("head_object", 0) == 0
    assert client.calls.get("list_objects_v2") == 1     # paginated, but one call


def test_s3_keys_land_under_the_configured_prefix(s3, tmp_path):
    """A bucket can hold more than M110's backups, so every key must sit under the
    store's prefix — and `list_keys` must hand back keys relative to it, or the
    sweep would compare full keys against manifest shas."""
    backend, client = s3
    backend.put_bytes("state.json", b"{}")
    assert "prefix/M110-Backups/store/state.json" in client.objects
    assert [k for k, _s, _m in backend.list_keys("state.json")] == ["state.json"]


def test_s3_missing_object_raises_keyerror_so_restore_skips_it(s3):
    """`pooled.restore` catches `(OSError, KeyError)` and skips that file. A raw
    ClientError would abort the whole restore over one absent object."""
    backend, _client = s3
    with pytest.raises(KeyError):
        backend.get_bytes("objects/00/00/nothing")


def test_s3_capabilities_shape_the_format_and_the_verify_depth(s3):
    """Each field here changes behaviour elsewhere: no hardlinks means no
    `latest/` tree, no free_bytes means the min-free retention rule is skipped,
    cheap_list=False sends `pooled.verify` down the shallow path, and
    parallel_puts>1 is what turns on concurrent uploads."""
    backend, _client = s3
    caps = backend.capabilities()
    assert caps.hardlinks is False
    assert caps.free_bytes is None
    assert caps.cheap_list is False
    assert caps.parallel_puts > 1
    assert backend.link("objects/aa/bb/aabb", "Images/M51/lights/a.fit") is False


def test_s3_delete_many_batches(s3, tmp_path):
    """The sweep can drop thousands of objects; one DELETE apiece is thousands of
    round-trips where `delete_objects` is a handful."""
    backend, client = s3
    src = tmp_path / "src.bin"
    src.write_bytes(b"x")
    keys = [f"objects/{i:02d}/00/{i:04d}" for i in range(25)]
    for k in keys:
        backend.put_file(k, src)
    client.calls.clear()

    assert backend.delete_many(keys) == 25

    assert client.calls.get("delete_object", 0) == 0
    assert client.calls.get("delete_objects") == 1
    assert backend.object_sizes() == {}


def test_s3_ensure_root_reports_an_unreachable_bucket(tmp_path):
    """`ensure_root` is the reachability check on object storage — there are no
    directories to create — so a wrong bucket has to surface here, in the probe,
    rather than halfway through a backup."""
    from m110.backup.errors import BackupDestinationError
    backend = S3Backend("wrong-bucket", "", client=FakeS3Client("test-bucket"))
    with pytest.raises(BackupDestinationError):
        backend.ensure_root()


def test_s3_list_keys_reports_storage_time_for_the_gc_grace_window(s3, tmp_path):
    """The 24h grace window is what makes the sweep safe against a concurrent run
    without a lock, and it compares against the time the object was *stored*."""
    backend, client = s3
    src = tmp_path / "src.bin"
    src.write_bytes(b"x")
    backend.put_file("objects/aa/bb/aabb", src)
    (_key, _size, mtime), = list(backend.list_keys("objects"))
    assert mtime > 0
    client.set_mtime("prefix/M110-Backups/store/objects/aa/bb/aabb", 1_000.0)
    (_key, _size, aged), = list(backend.list_keys("objects"))
    assert aged == 1_000.0
