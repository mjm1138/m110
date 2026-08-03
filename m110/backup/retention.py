"""Snapshot retention — delete whole oldest snapshots per policy."""
from __future__ import annotations

from pathlib import Path

from .. import config
from . import mirrored
from .destination import free_bytes, store_backup_root
from .options import SnapshotInfo


def list_snapshots(destination: Path, store_name: str | None = None) -> list[SnapshotInfo]:
    """Every snapshot at this destination, newest first, regardless of format."""
    return mirrored.list_snapshots(destination, store_name)


def _delete(snap: SnapshotInfo) -> None:
    mirrored.delete_snapshot(snap)


def apply_retention(destination: Path, *, keep: int | None = None,
                    min_free_gb: float | None = None,
                    store_name: str | None = None) -> dict:
    """Delete whole oldest snapshots per policy. No-op unless a policy is set.
    Never deletes the last remaining snapshot. Because unchanged files are
    hardlinked across snapshots, deleting one frees only its unique inodes.

    Policies are count-based (`keep` newest) and space-based (`min_free_gb` free
    on the destination volume) — both prune the *oldest* first. There is
    deliberately no age-based ("older than N days") policy: it would silently wipe
    a whole backup history after a gap in use (e.g. a two-week vacation)."""
    snaps = list_snapshots(destination, store_name)   # newest first
    to_delete: list[SnapshotInfo] = []

    if keep is not None and keep >= 1 and len(snaps) > keep:
        to_delete.extend(snaps[keep:])

    survivors = [s for s in snaps if s not in to_delete]
    if min_free_gb is not None and min_free_gb > 0:
        need = min_free_gb * (1024 ** 3)
        # Delete oldest survivors until free space clears the threshold.
        for s in sorted(survivors, key=lambda s: s.created):
            if free_bytes(destination) >= need or len(survivors) <= 1:
                break
            to_delete.append(s)
            survivors.remove(s)

    # Never delete every snapshot — keep at least the newest.
    remaining = [s for s in snaps if s not in to_delete]
    if not remaining and snaps:
        newest = max(snaps, key=lambda s: s.created)
        to_delete = [s for s in to_delete if s is not newest]

    pruned = 0
    for s in to_delete:
        _delete(s)
        pruned += 1
    if pruned:
        root = store_backup_root(destination, store_name)
        mirrored.write_state(root, config.DATA_ROOT)
    return {"pruned": pruned, "kept": len(snaps) - pruned}
