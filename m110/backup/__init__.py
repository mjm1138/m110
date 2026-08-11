"""Library backup — dated snapshots of the data store (ROADMAP item 10).

Qt-free engine (like `ingest`/`siril`/`publish`): pure functions taking optional
`should_cancel`/`progress` callbacks. A backup is an **external output** — it reads
`config.DATA_ROOT` and writes to a user-chosen destination *outside* the store, so
it never changes the on-disk store layout (no `.store_version` impact).

    errors      failures
    options     value types + persisted-setting names        (leaf)
    scope       what gets backed up (a denylist)             (leaf)
    destination where a store's backups live; what the FS can do
    backends    the storage seam a pooled backup writes through
    hashcache   remember what we've already hashed
    mirrored    format: dated full trees, hardlink-deduped   (the default)
    pooled      format: files stored once, addressed by content
    recovery    the artifacts that make a pooled backup readable without M110
    retention   prune oldest snapshots; sweep unreferenced objects
    formats     which format a destination gets; dispatch by snapshot
    probe       pre-flight inspection of a destination
    schedule    when an automatic backup is due

Two formats, both always readable at the same destination — see `formats.py` for
why mirrored stays the default and when pooled takes over.

This module is the façade: import `m110.backup` and use the names below.
"""
from __future__ import annotations

import os  # noqa: F401  (kept for callers/tests that reach through the façade)
import threading

from .backends import BACKEND_KINDS, Backend, Capabilities, backend_for
from .destination import free_bytes as _free_bytes  # noqa: F401
from .destination import store_backup_root, supports_hardlinks
from .errors import BackupDestinationError, BackupError
from .formats import (
    DEFAULT_FORMAT, FORMAT_BLURBS, FORMAT_LABELS, FORMAT_MIRRORED, FORMAT_POOLED,
    FORMATS, detect_format, format_of, preferred_format, preview_restore,
    resolve_format, restore, snapshot_files, verify,
)
from .formats import create_snapshot as _create_snapshot
from .mirrored import INCOMPLETE_SUFFIX, MANIFEST_NAME, STATE_NAME, sweep_incomplete
from .options import (
    BACKUPS_DIRNAME, DEFAULT_DAILY_HOUR, DEFAULT_INTERVAL_HOURS, DEFAULT_MIN_FREE_GB,
    SETTING_AUTO, SETTING_DAILY_HOUR, SETTING_DEST, SETTING_FORMAT, SETTING_INTERVAL,
    SETTING_KEEP, SETTING_MIN_FREE, TIMESTAMP_FMT, BackupOptions, DestinationInfo,
    SnapshotInfo,
)
from .probe import probe_destination
from .retention import apply_retention, list_snapshots, sweep_objects
from .schedule import due_for_auto_backup, due_for_scheduled_backup, options_from_settings
from .scope import is_excluded, iter_source_files

# One backup at a time per process. The dialog's "Back up now" worker and the
# window's scheduled background worker don't know about each other, and two
# concurrent runs would double the source read I/O, contend on the hash cache,
# and put the object sweep in the position of judging a half-written run.
_RUN_LOCK = threading.Lock()


def create_snapshot(options: BackupOptions, should_cancel=None, progress=None) -> dict:
    """Write a new snapshot of the current store to the destination, in whichever
    format that destination resolves to. Returns a summary dict (or
    `{"cancelled": True}`)."""
    if not _RUN_LOCK.acquire(blocking=False):
        raise BackupError("A backup is already running.")
    try:
        return _create_snapshot(options, should_cancel=should_cancel, progress=progress)
    finally:
        _RUN_LOCK.release()


__all__ = [
    "BACKEND_KINDS", "BACKUPS_DIRNAME", "Backend", "BackupDestinationError",
    "BackupError", "BackupOptions", "Capabilities", "DEFAULT_DAILY_HOUR",
    "DEFAULT_FORMAT", "DEFAULT_INTERVAL_HOURS", "DEFAULT_MIN_FREE_GB",
    "DestinationInfo", "FORMATS", "FORMAT_BLURBS", "FORMAT_LABELS",
    "FORMAT_MIRRORED", "FORMAT_POOLED", "INCOMPLETE_SUFFIX", "MANIFEST_NAME",
    "SETTING_AUTO", "SETTING_DAILY_HOUR", "SETTING_DEST", "SETTING_FORMAT",
    "SETTING_INTERVAL", "SETTING_KEEP", "SETTING_MIN_FREE", "STATE_NAME",
    "SnapshotInfo", "TIMESTAMP_FMT", "apply_retention", "backend_for",
    "create_snapshot", "detect_format", "due_for_auto_backup",
    "due_for_scheduled_backup", "format_of", "is_excluded", "iter_source_files",
    "list_snapshots", "options_from_settings", "preferred_format",
    "preview_restore", "probe_destination", "resolve_format", "restore",
    "snapshot_files", "store_backup_root", "supports_hardlinks",
    "sweep_incomplete", "sweep_objects", "verify",
]
