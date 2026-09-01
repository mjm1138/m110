"""Retention across both snapshot formats, and the object sweep pooled storage
needs in place of a dependency graph.

Deleting a **mirrored** snapshot frees its unique inodes immediately. Deleting a
**pooled** snapshot frees nothing at all until the sweep decides which objects no
surviving manifest still references — a refcount over data we already have,
rather than the "can't drop this full until its incrementals expire" bookkeeping
a chain-based backup would force on us.
"""
from __future__ import annotations

import itertools
import time
from datetime import datetime

from .. import config
from . import mirrored, pooled
from .backends import backend_for
from .destination import free_bytes, parse_destination, store_backup_root
from .options import SnapshotInfo

# An object being written by a run happening *right now* is, by definition,
# recently modified — so an unreferenced-but-recent object is never swept. That
# single rule is what makes the sweep safe against a concurrent backup without a
# distributed lock, and it's how restic and borg solve the same problem.
GC_GRACE_SECONDS = 24 * 3600
GC_MAX_AGE_SECONDS = 7 * 86400      # re-sweep weekly to catch cancelled-run orphans


def list_snapshots(destination, store_name: str | None = None) -> list[SnapshotInfo]:
    """Every snapshot at this destination, newest first, in either format.

    Both can coexist in one store root: mirrored snapshots are directories whose
    *names* parse as timestamps, and `objects/`/`snapshots/`/`latest/` never will.
    So there is no flag day and no conversion — a user who switches format keeps
    full restore access to everything they already had. On object storage only
    pooled can exist, so mirrored isn't asked."""
    dest = parse_destination(destination)
    snaps = list(pooled.list_snapshots(dest, store_name))
    if dest.is_local:
        snaps += mirrored.list_snapshots(dest, store_name)
    snaps.sort(key=lambda s: s.created, reverse=True)
    return snaps


def _delete(snap: SnapshotInfo) -> None:
    if snap.format == pooled.FORMAT:
        pooled.delete_snapshot(snap)
    else:
        mirrored.delete_snapshot(snap)


def apply_retention(destination, *, keep: int | None = None,
                    min_free_gb: float | None = None,
                    store_name: str | None = None, gc: bool = True) -> dict:
    """Delete whole oldest snapshots per policy. No-op unless a policy is set.
    Never deletes the last remaining snapshot.

    Policies are count-based (`keep` newest) and space-based (`min_free_gb` free
    on the destination volume) — both prune the *oldest* first. There is
    deliberately no age-based ("older than N days") policy: it would silently wipe
    a whole backup history after a gap in use (e.g. a two-week vacation)."""
    dest = parse_destination(destination)
    snaps = list_snapshots(dest, store_name)   # newest first
    dropped: list[SnapshotInfo] = []

    if keep is not None and keep >= 1 and len(snaps) > keep:
        for s in snaps[keep:]:
            _delete(s)
            dropped.append(s)

    remaining = [s for s in snaps if s not in dropped]

    # A bucket has no volume to run out of, so the min-free policy has nothing to
    # measure — skipping it is what stops a meaningless 0-free reading from
    # pruning a cloud history down to one snapshot.
    if not dest.is_local:
        min_free_gb = None

    if min_free_gb is not None and min_free_gb > 0 and len(remaining) > 1:
        need = min_free_gb * (1024 ** 3)
        # Delete one at a time and re-measure. (The previous implementation read
        # free space inside a loop that deleted nothing until afterwards, so the
        # reading never moved and one pass queued every survivor but one.)
        if dropped and gc:
            sweep_objects(destination, store_name)
        while len(remaining) > 1 and free_bytes(destination) < need:
            oldest = remaining.pop()          # newest-first, so the last is oldest
            _delete(oldest)
            dropped.append(oldest)
            if oldest.format == pooled.FORMAT and gc:
                sweep_objects(destination, store_name)

    swept = 0
    if dropped:
        pooled_ts = [s.timestamp for s in dropped if s.format == pooled.FORMAT]
        if pooled_ts:
            pooled.forget_snapshots(dest, pooled_ts, store_name)
        if dest.is_local:
            root = store_backup_root(dest, store_name)
            if root.is_dir() and any(s.format == mirrored.FORMAT for s in dropped):
                mirrored.write_state(root, config.DATA_ROOT)

    if gc and _sweep_due(dest, store_name, bool(dropped)):
        swept = sweep_objects(dest, store_name).get("swept", 0)

    return {"pruned": len(dropped), "kept": len(snaps) - len(dropped), "swept": swept}


def _has_objects(dest, store_name: str | None) -> bool:
    """Whether this destination holds an object pool at all. One cheap `is_dir`
    locally; on object storage, the first page of a LIST."""
    if dest.is_local:
        return (store_backup_root(dest, store_name) / "objects").is_dir()
    backend = backend_for(dest, store_name)
    return any(True for _ in itertools.islice(backend.list_keys("objects"), 1))


def _sweep_due(destination, store_name: str | None, pruned: bool) -> bool:
    """Sweeping a store where nothing was dropped is pure cost — no snapshot went
    away, so no object became unreferenced. Still re-sweep weekly, to collect
    orphans left by cancelled runs."""
    dest = parse_destination(destination)
    if not _has_objects(dest, store_name):
        return False
    if pruned:
        return True
    state = pooled._read_state(backend_for(destination, store_name))
    last = state.get("last_gc")
    if not last:
        return True
    try:
        age = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
    except (TypeError, ValueError):
        return True
    return age >= GC_MAX_AGE_SECONDS


def sweep_objects(destination, store_name: str | None = None, *,
                  grace_seconds: float = GC_GRACE_SECONDS, now: float | None = None,
                  should_cancel=None) -> dict:
    """Delete objects no surviving manifest references.

    Mark: union the sha256s of every remaining pooled manifest. Sweep: everything
    under `objects/` that isn't in that set *and* is older than the grace window.

    Marking from *every* surviving manifest is also what makes narrowing a
    destination's scope safe: frames dropped from the new scope stay referenced
    by the older, wider snapshots until retention prunes those."""
    cancelled = should_cancel or (lambda: False)
    dest = parse_destination(destination)
    backend = backend_for(dest, store_name)
    if not _has_objects(dest, store_name):
        return {"swept": 0, "bytes": 0, "kept": 0}

    referenced: set[str] = set()
    for snap in pooled.list_snapshots(dest, store_name):
        for meta in pooled.snapshot_files(snap).values():
            referenced.add(meta.get("sha256", ""))

    now = time.time() if now is None else now
    doomed: list[str] = []
    freed = 0
    kept = 0
    for key, size, mtime in backend.list_keys("objects"):
        if cancelled():
            return {"swept": 0, "bytes": 0, "kept": kept, "cancelled": True}
        sha = key.rsplit("/", 1)[-1]
        if sha in referenced:
            kept += 1
            continue
        if now - mtime < grace_seconds:
            kept += 1                       # a concurrent run may still be writing it
            continue
        doomed.append(key)
        freed += size
    if doomed:
        backend.delete_many(doomed)
    _stamp_gc(backend)
    return {"swept": len(doomed), "bytes": freed, "kept": kept}


def _stamp_gc(backend) -> None:
    state = pooled._read_state(backend)
    if not state:
        return
    state["last_gc"] = datetime.now().isoformat(timespec="seconds")
    backend.put_bytes(pooled.STATE_KEY, pooled._json_bytes(state))
