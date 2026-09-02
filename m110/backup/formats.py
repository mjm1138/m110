"""Which snapshot format a destination gets, and dispatching by snapshot.

**Mirrored** stays the default wherever it works. It has a property nothing else
does: a snapshot is your files, in the right folders, restorable in Finder with
no software at all. That's worth keeping for everyone whose destination can do
it.

**Pooled** exists for the destinations mirrored can't serve — a share or
filesystem that can't hardlink, where mirrored silently stores a *full copy* of
the library every night (issue #92) — and for offsite object storage, which has
no concept of a link at all (#93).

Resolution order, most specific first:

1. **What the destination already holds.** State lives on the destination, so a
   second machine reaches the same answer, and a destination never changes shape
   under you.
2. **The preference.**
3. **Unless the filesystem can't hardlink** — then pooled, necessarily. The
   caller persists that so the choice sticks (detect, don't ask — the same
   instinct as `launch.find_app`).

Both formats stay listable, verifiable and restorable at the same destination,
always. Switching format never strands a backup you already have.
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from . import mirrored, pooled
from .destination import parse_destination, store_backup_root, supports_hardlinks
from .options import SETTING_FORMAT, SnapshotInfo
from .retention import list_snapshots

FORMAT_MIRRORED = mirrored.FORMAT
FORMAT_POOLED = pooled.FORMAT
DEFAULT_FORMAT = FORMAT_MIRRORED
FORMATS = (FORMAT_MIRRORED, FORMAT_POOLED)

FORMAT_LABELS = {
    FORMAT_MIRRORED: "Mirrored backups",
    FORMAT_POOLED: "Pooled backups",
}

FORMAT_BLURBS = {
    FORMAT_MIRRORED: (
        "Every backup is a complete, browsable copy of your Library. Unchanged "
        "files are shared with the previous backup, so repeat backups cost only "
        "what changed. Needs a destination that supports file links — most "
        "drives and network shares do."),
    FORMAT_POOLED: (
        "Files are stored once, named by their contents; each backup is a small "
        "index of what it contains. Works on any destination, including ones "
        "that can't share files. A browsable copy of the newest backup is kept "
        "alongside where the destination allows it."),
}


def preferred_format() -> str:
    value = config.get_setting(SETTING_FORMAT, DEFAULT_FORMAT)
    return value if value in FORMATS else DEFAULT_FORMAT


def detect_format(destination, store_name: str | None = None) -> str | None:
    """The format already in use at this destination, or None if it's unused."""
    dest = parse_destination(destination)
    if not dest.is_local:
        # No filesystem to stat: ask the store whether it holds any manifest.
        # Mirrored can't exist here — it is directories and hardlinks by design.
        return FORMAT_POOLED if pooled.list_snapshots(dest, store_name) else None
    root = store_backup_root(dest, store_name)
    if not root.is_dir():
        return None
    if (root / "snapshots").is_dir() and any(
            (root / "snapshots").glob(f"*{pooled.SNAPSHOT_SUFFIX}")):
        return FORMAT_POOLED
    if mirrored.list_snapshots(dest, store_name):
        return FORMAT_MIRRORED
    return None


def resolve_format(destination, store_name: str | None = None, *,
                   hardlinks: bool | None = None) -> tuple[str, bool]:
    """`(format, forced)` for the *next* backup here. `forced` is True when the
    destination left no choice — the caller shows the reason and persists it."""
    dest = parse_destination(destination)
    # Object storage has no hardlinks and no directories to browse, so mirrored
    # isn't a choice being declined — it has no meaning there. Forced, and the UI
    # says so as a fact about the destination rather than as a warning.
    if not dest.is_local:
        return FORMAT_POOLED, True

    existing = detect_format(dest, store_name)
    if existing is not None:
        preferred = preferred_format()
        # An explicit preference for the other format still wins for *new*
        # snapshots; what's already there stays readable either way.
        return (preferred, False) if preferred != existing else (existing, False)

    preferred = preferred_format()
    if preferred == FORMAT_POOLED:
        return FORMAT_POOLED, False
    if hardlinks is None:
        root = store_backup_root(dest, store_name)
        probe_dir = root if root.is_dir() else dest.path
        hardlinks = supports_hardlinks(probe_dir) if probe_dir.is_dir() else True
    if not hardlinks:
        return FORMAT_POOLED, True
    return FORMAT_MIRRORED, False


def _module(fmt: str):
    return pooled if fmt == FORMAT_POOLED else mirrored


def create_snapshot(options, should_cancel=None, progress=None) -> dict:
    dest = parse_destination(options.destination)
    fmt, forced = resolve_format(dest)
    # Persist a *discovered* limitation (this filesystem can't hardlink) so the
    # choice sticks. Don't persist the inherent one: a bucket being pooled says
    # nothing about the user's local drive, and `backup_format` is global — this
    # is where backing up to S3 once would otherwise have silently converted the
    # next backup to the external disk.
    if forced and dest.is_local:
        config.save_setting(SETTING_FORMAT, fmt)
    return _module(fmt).create_snapshot(options, should_cancel=should_cancel,
                                        progress=progress)


# ── dispatch by snapshot ────────────────────────────────────────────────────

def format_of(ref) -> str:
    """Which format a snapshot reference belongs to. Accepts a `SnapshotInfo` or
    the path the UI carries around."""
    if isinstance(ref, SnapshotInfo):
        return ref.format
    return FORMAT_POOLED if pooled.is_pooled_ref(ref) else FORMAT_MIRRORED


def _ref_for(fmt: str, ref):
    """Mirrored addresses a snapshot by its directory; pooled resolves its own
    references, so it gets the `SnapshotInfo` untouched — that is what carries the
    `ref` by which a snapshot with no filesystem path is reachable."""
    if fmt == FORMAT_POOLED:
        return ref
    return ref.path if isinstance(ref, SnapshotInfo) else ref


def snapshot_files(ref) -> dict[str, dict]:
    fmt = format_of(ref)
    return _module(fmt).snapshot_files(_ref_for(fmt, ref))


def verify(ref, should_cancel=None, progress=None, deep: bool | None = None) -> dict:
    """Verify one snapshot. `deep` is meaningful for pooled only — see
    `pooled.verify` for why a bucket defaults to the shallow check."""
    fmt = format_of(ref)
    extra = {"deep": deep} if fmt == FORMAT_POOLED else {}
    return _module(fmt).verify(_ref_for(fmt, ref), should_cancel=should_cancel,
                               progress=progress, **extra)


def preview_restore(ref, relpaths, dest_dir) -> dict:
    fmt = format_of(ref)
    return _module(fmt).preview_restore(_ref_for(fmt, ref), relpaths, dest_dir)


def restore(ref, relpaths, dest_dir, *, overwrite: bool = False,
            should_cancel=None, progress=None) -> dict:
    fmt = format_of(ref)
    return _module(fmt).restore(
        _ref_for(fmt, ref), relpaths, dest_dir, overwrite=overwrite,
        should_cancel=should_cancel, progress=progress)


__all__ = ["DEFAULT_FORMAT", "FORMATS", "FORMAT_BLURBS", "FORMAT_LABELS",
           "FORMAT_MIRRORED", "FORMAT_POOLED", "create_snapshot", "detect_format",
           "format_of", "preferred_format", "preview_restore", "resolve_format",
           "restore", "snapshot_files", "verify", "list_snapshots"]
