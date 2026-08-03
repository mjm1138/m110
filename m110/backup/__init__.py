"""Library backup — dated snapshots of the data store (ROADMAP item 10).

Qt-free engine (like `ingest`/`siril`/`publish`): pure functions taking optional
`should_cancel`/`progress` callbacks. A backup is an **external output** — it reads
`config.DATA_ROOT` and writes to a user-chosen destination *outside* the store, so
it never changes the on-disk store layout (no `.store_version` impact).

    errors      failures
    options     value types + persisted-setting names        (leaf)
    scope       what gets backed up (a denylist)             (leaf)
    destination where a store's backups live; what the FS can do
    mirrored    the snapshot format: dated full trees, hardlink-deduped
    retention   prune oldest snapshots per policy
    probe       pre-flight inspection of a destination
    schedule    when an automatic backup is due

This module is the façade: import `m110.backup` and use the names below.
"""
from __future__ import annotations

import os  # noqa: F401  (kept for callers/tests that reach through the façade)

from .destination import free_bytes as _free_bytes  # noqa: F401
from .destination import store_backup_root, supports_hardlinks
from .errors import BackupDestinationError, BackupError
from .mirrored import (
    INCOMPLETE_SUFFIX, MANIFEST_NAME, STATE_NAME, create_snapshot, preview_restore,
    restore, snapshot_files, sweep_incomplete, verify,
)
from .options import (
    BACKUPS_DIRNAME, DEFAULT_DAILY_HOUR, DEFAULT_INTERVAL_HOURS, DEFAULT_MIN_FREE_GB,
    SETTING_AUTO, SETTING_DAILY_HOUR, SETTING_DEST, SETTING_INTERVAL, SETTING_KEEP,
    SETTING_MIN_FREE, TIMESTAMP_FMT, BackupOptions, DestinationInfo, SnapshotInfo,
)
from .probe import probe_destination
from .retention import apply_retention, list_snapshots
from .schedule import due_for_auto_backup, due_for_scheduled_backup, options_from_settings
from .scope import is_excluded, iter_source_files

__all__ = [
    "BACKUPS_DIRNAME", "BackupDestinationError", "BackupError", "BackupOptions",
    "DEFAULT_DAILY_HOUR", "DEFAULT_INTERVAL_HOURS", "DEFAULT_MIN_FREE_GB",
    "DestinationInfo", "INCOMPLETE_SUFFIX", "MANIFEST_NAME", "SETTING_AUTO",
    "SETTING_DAILY_HOUR", "SETTING_DEST", "SETTING_INTERVAL", "SETTING_KEEP",
    "SETTING_MIN_FREE", "STATE_NAME", "SnapshotInfo", "TIMESTAMP_FMT",
    "apply_retention", "create_snapshot", "due_for_auto_backup",
    "due_for_scheduled_backup", "is_excluded", "iter_source_files", "list_snapshots",
    "options_from_settings", "preview_restore", "probe_destination", "restore",
    "snapshot_files", "store_backup_root", "supports_hardlinks", "sweep_incomplete",
    "verify",
]
