"""The storage-seam contract.

One suite, run against every backend, so an adapter either satisfies the contract
the pooled format relies on or fails here. `S3Backend` (issue #93) plugs into
this list rather than getting a bespoke test file.
"""
import os

import pytest

from m110.backup.backends import LocalBackend, MemoryBackend


@pytest.fixture(params=["local", "memory"])
def backend(request, tmp_path):
    if request.param == "local":
        b = LocalBackend(tmp_path / "M110-Backups" / "store")
    else:
        b = MemoryBackend()
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
