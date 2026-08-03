"""The source hash cache — what makes a nightly pooled backup not re-read the
whole library, without ever being allowed to lie."""
import os
import time

from m110.backup.hashcache import HashCache, hash_file


def _write(path, data=b"contents"):
    path.write_bytes(data)
    return path


def test_second_lookup_is_a_hit(tmp_path):
    f = _write(tmp_path / "a.bin")
    with HashCache(tmp_path / "cache.sqlite3") as cache:
        first = cache.sha256(f)
        second = cache.sha256(f)
    assert first == second == hash_file(f)


def test_any_change_to_the_stat_tuple_is_a_miss(tmp_path):
    """Key on all four of size/mtime_ns/inode/dev. A miss costs a rehash; only a
    stale *hit* could be wrong, so the key errs toward missing."""
    f = _write(tmp_path / "a.bin", b"one")
    cache = HashCache(tmp_path / "cache.sqlite3")
    try:
        cache.sha256(f)
        assert (cache.hits, cache.misses) == (0, 1)

        # same size, different mtime → miss
        st = f.stat()
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        cache.sha256(f)
        assert cache.misses == 2

        # different size → miss, and the new content wins
        f.write_bytes(b"different length")
        assert cache.sha256(f) == hash_file(f)
        assert cache.misses == 3

        # unchanged → hit
        cache.sha256(f)
        assert cache.hits == 1
    finally:
        cache.close()


def test_a_rewritten_file_with_the_same_size_and_mtime_is_still_caught_by_inode(tmp_path):
    """The classic stale-hit shape: replace a file with same-size content and
    restore its mtime. A fresh file gets a new inode, so the key still misses."""
    f = _write(tmp_path / "a.bin", b"aaaa")
    st = f.stat()
    with HashCache(tmp_path / "cache.sqlite3") as cache:
        original = cache.sha256(f)
        tmp = tmp_path / "tmp.bin"
        tmp.write_bytes(b"bbbb")
        os.replace(tmp, f)
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
        assert cache.sha256(f) == hash_file(f) != original


def test_forget_drops_a_row(tmp_path):
    f = _write(tmp_path / "a.bin")
    with HashCache(tmp_path / "cache.sqlite3") as cache:
        cache.sha256(f)
        cache.forget(f)
        cache.sha256(f)
        assert cache.misses == 2


def test_sweep_evicts_rows_not_seen_recently(tmp_path):
    f = _write(tmp_path / "a.bin")
    cache = HashCache(tmp_path / "cache.sqlite3")
    try:
        cache.sha256(f)
        cache.flush()
        cache._conn.execute("UPDATE hashes SET seen=?", (int(time.time()) - 200 * 86400,))
        cache._conn.commit()
        assert cache.sweep(max_age_days=90) == 1
        cache.sha256(f)
        assert cache.misses == 2
    finally:
        cache.close()


def test_row_cap_trims_the_least_recently_seen(tmp_path):
    cache = HashCache(tmp_path / "cache.sqlite3")
    try:
        for i in range(5):
            cache.sha256(_write(tmp_path / f"f{i}.bin", b"x" * (i + 1)))
        cache.flush()
        assert cache.sweep(max_age_days=3650, max_rows=2) == 3
        (count,) = cache._conn.execute("SELECT COUNT(*) FROM hashes").fetchone()
        assert count == 2
    finally:
        cache.close()


def test_an_unusable_cache_file_degrades_to_plain_hashing(tmp_path):
    """Slower, never wrong — a cache that can't open must not stop a backup."""
    broken = tmp_path / "cache.sqlite3"
    broken.write_bytes(b"not a database")
    cache = HashCache(broken)
    try:
        f = _write(tmp_path / "a.bin")
        assert cache.sha256(f) == hash_file(f)
        assert cache.sha256(f) == hash_file(f)
        assert cache.misses == 2            # no cache, so every read is a miss
    finally:
        cache.close()
