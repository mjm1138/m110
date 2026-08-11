"""Remember what we've already hashed.

A pooled backup addresses files by the sha256 of their contents, so every run
would otherwise re-read the entire library — hours for a 500 GB store, every
night, to discover that nothing changed. The cache is keyed on the **source**
path (not the destination), so it survives switching destinations and serves all
of them.

The safety property: **a miss is always safe** — it costs a rehash, never a wrong
answer. Only a stale *hit* could be wrong, so the key is all four of
`(size, mtime_ns, inode, dev)`; and the caller cross-checks the size the
destination reports for that hash, which catches the remaining sliver for free
(an object's size is a function of its bytes).

Worth noting this is strictly *stronger* than the mirrored format's reuse test,
which matches size + mtime and then inherits a sha it never recomputes — possibly
across many generations of snapshot.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

from .. import config

CACHE_FILENAME = "backup-hashes.sqlite3"
HASH_CHUNK = 1 << 20            # 1 MiB
_COMMIT_EVERY = 500             # so a cancel doesn't discard the run's hashing
MAX_AGE_DAYS = 90
MAX_ROWS = 2_000_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hashes (
  path     TEXT PRIMARY KEY,
  size     INTEGER NOT NULL,
  mtime_ns INTEGER NOT NULL,
  inode    INTEGER NOT NULL,
  dev      INTEGER NOT NULL,
  sha256   TEXT NOT NULL,
  seen     INTEGER NOT NULL
);
"""


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_path() -> Path:
    return config.APP_CONFIG_DIR / CACHE_FILENAME


class HashCache:
    """Degrades to plain hashing if sqlite is unavailable (read-only home, a
    corrupt file, a filesystem without locking) — slower, never wrong."""

    def __init__(self, path: Path | None = None):
        self._path = Path(path) if path is not None else cache_path()
        self._conn: sqlite3.Connection | None = None
        self._pending = 0
        self.hits = 0
        self.misses = 0
        self._open()

    def _open(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.executescript(_SCHEMA)
            conn.commit()
            self._conn = conn
        except (sqlite3.Error, OSError):
            self._conn = None

    # ---- lookup ----
    def sha256(self, path: Path, st=None) -> str:
        """The sha256 of `path`, from cache when the file is provably unchanged."""
        path = Path(path)
        st = st or path.stat()
        cached = self._lookup(str(path), st)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        sha = hash_file(path)
        self.remember(path, st, sha)
        return sha

    def _lookup(self, key: str, st) -> str | None:
        if self._conn is None:
            return None
        try:
            row = self._conn.execute(
                "SELECT sha256 FROM hashes WHERE path=? AND size=? AND mtime_ns=? "
                "AND inode=? AND dev=?",
                (key, st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev)).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        self._touch(key)
        return row[0]

    def remember(self, path: Path, st, sha: str) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO hashes(path,size,mtime_ns,inode,dev,sha256,seen) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                "size=excluded.size, mtime_ns=excluded.mtime_ns, inode=excluded.inode, "
                "dev=excluded.dev, sha256=excluded.sha256, seen=excluded.seen",
                (str(path), st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev, sha,
                 int(time.time())))
            self._bump()
        except sqlite3.Error:
            pass

    def forget(self, path: Path) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute("DELETE FROM hashes WHERE path=?", (str(path),))
            self._bump()
        except sqlite3.Error:
            pass

    def _touch(self, key: str) -> None:
        try:
            self._conn.execute("UPDATE hashes SET seen=? WHERE path=?",
                               (int(time.time()), key))
            self._bump()
        except sqlite3.Error:
            pass

    def _bump(self) -> None:
        self._pending += 1
        if self._pending >= _COMMIT_EVERY:
            self.flush()

    def flush(self) -> None:
        if self._conn is None or not self._pending:
            return
        try:
            self._conn.commit()
        except sqlite3.Error:
            pass
        self._pending = 0

    # ---- housekeeping ----
    def sweep(self, *, max_age_days: int = MAX_AGE_DAYS,
              max_rows: int = MAX_ROWS) -> int:
        """Drop rows for files we haven't seen in a long time, then cap the table.
        Losing a row only costs a rehash."""
        if self._conn is None:
            return 0
        removed = 0
        cutoff = int(time.time()) - max_age_days * 86400
        try:
            cur = self._conn.execute("DELETE FROM hashes WHERE seen < ?", (cutoff,))
            removed += cur.rowcount or 0
            (count,) = self._conn.execute("SELECT COUNT(*) FROM hashes").fetchone()
            if count > max_rows:
                cur = self._conn.execute(
                    "DELETE FROM hashes WHERE path IN "
                    "(SELECT path FROM hashes ORDER BY seen ASC LIMIT ?)",
                    (count - max_rows,))
                removed += cur.rowcount or 0
            self._conn.commit()
            self._pending = 0
        except sqlite3.Error:
            return removed
        return removed

    def close(self) -> None:
        self.flush()
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
