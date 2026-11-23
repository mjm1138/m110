"""The store-version gate on a restore **into the store** (BUGS #40d).

Every snapshot records the `.store_version` it was taken at. A *full* restore
brings that stamp back and the next launch migrates, but the restore dialog
restores any subset of files, and a subset from an older snapshot lands in an
older shape under the current stamp. Migration never looks at it again. After the
v5 → v6 rename, a restored `Images/<t>/seestar-stacks/` sits beside
`device-stacks/` where nothing reads it.

So the writer guards it, rather than trusting the caller (the F1 lesson):

* a snapshot from a **newer** store is refused: this build can't know that
  layout, and nothing can migrate it backwards. Extracting it to a folder is
  still allowed (`formats.restore` to any other directory);
* after restoring from an **older** snapshot, or one with no recorded version,
  every migration step runs again over the store (`migrate.migrate_restored`).
  Each step detects its own structure and never overwrites, so a pass over files
  that are already current changes nothing.

Qt-free. Extracting to a folder never goes through here.
"""
from __future__ import annotations

from pathlib import Path

from .. import config, migrate
from .errors import BackupError
from .formats import restore

SAME, OLDER, NEWER, UNKNOWN = "same", "older", "newer", "unknown"


def store_compat(snapshot_version, current: int | None = None) -> str:
    """How a snapshot's recorded store version compares with this build's:
    `same`, `older`, `newer`, or `unknown` (none recorded, or unreadable)."""
    current = migrate.STORE_VERSION if current is None else current
    try:
        v = int(str(snapshot_version).strip())
    except (TypeError, ValueError):
        return UNKNOWN
    if v == current:
        return SAME
    return OLDER if v < current else NEWER


def newer_store_message(snapshot_version) -> str:
    return (f"This backup was made by a newer version of M110 (store version "
            f"{snapshot_version}; this version uses {migrate.STORE_VERSION}), so its "
            "files can't be put back into your Library by this version. Update M110 "
            "first, or extract the files to a folder instead.")


def restore_into_store(snap, relpaths, *, root: Path | None = None,
                       overwrite: bool = False, should_cancel=None,
                       progress=None) -> dict:
    """Restore `relpaths` from `snap` (a `SnapshotInfo`) into the data store, then
    bring anything restored from an older layout up to date. The result is
    `formats.restore`'s plus `migrated` (True when the migration pass changed
    something). Raises `BackupError` for a snapshot from a newer store."""
    root = Path(root if root is not None else config.DATA_ROOT)
    version = getattr(snap, "store_version", None)
    compat = store_compat(version)
    if compat == NEWER:
        raise BackupError(newer_store_message(version))
    res = restore(snap, relpaths, root, overwrite=overwrite,
                  should_cancel=should_cancel, progress=progress)
    res["migrated"] = False
    # Even a cancelled restore may have written old-shape files before it stopped.
    if compat != SAME and res.get("written"):
        res["migrated"] = migrate.migrate_restored(root)
    return res


__all__ = ["NEWER", "OLDER", "SAME", "UNKNOWN", "newer_store_message",
           "restore_into_store", "store_compat"]
