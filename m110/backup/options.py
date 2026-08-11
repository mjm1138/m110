"""Backup value types + persisted-setting names.

Leaf module: data and constants only, no logic and no imports from the rest of
the package, so every other module can depend on it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

BACKUPS_DIRNAME = "M110-Backups"
TIMESTAMP_FMT = "%Y-%m-%d_%H%M%S_%f"   # microseconds → unique even on rapid runs

# Persisted settings (global `~/.m110/settings.json`, via config.get/save_setting).
SETTING_DEST = "backup_destination"
SETTING_AUTO = "backup_auto_on_launch"
SETTING_INTERVAL = "backup_interval_hours"
SETTING_KEEP = "backup_retention_keep"
SETTING_MIN_FREE = "backup_min_free_gb"
DEFAULT_MIN_FREE_GB = 100       # prune oldest snapshots to keep this much free
SETTING_DAILY_HOUR = "backup_daily_hour"
DEFAULT_INTERVAL_HOURS = 12
DEFAULT_DAILY_HOUR = 2          # 02:00 local — the while-running daily backup time
# "mirrored" | "pooled" — see formats.py. Mirrored is the default; a destination
# that can't hardlink flips this to pooled and the app persists that.
SETTING_FORMAT = "backup_format"


@dataclass
class BackupOptions:
    destination: Path
    retention_keep: int | None = None       # keep N newest snapshots (None = all)
    min_free_gb: float | None = None         # delete oldest until ≥ this free


@dataclass
class SnapshotInfo:
    path: Path
    timestamp: str
    created: datetime
    file_count: int
    total_bytes: int
    store_version: str | None = None
    hardlinks: bool = True
    format: str = "mirrored"


@dataclass
class DestinationInfo:
    """What we can learn about a destination *before* backing up to it.

    The hardlink answer is the important one: where a filesystem can't link,
    every snapshot silently becomes a full copy of the library (issue #92), and
    until now the user could only find that out after the first run — the
    warning was read back out of a manifest. Probing up front means the dialog
    can say so while the destination is still being chosen.
    """
    path: Path
    exists: bool
    writable: bool
    hardlinks: bool
    free_bytes: int | None
    snapshot_count: int
    newest: SnapshotInfo | None = None
    error: str | None = None
    # Which snapshot format the *next* backup here would use, what's already
    # there (None = unused destination), and whether the destination left no
    # choice (it can't hardlink, so mirrored isn't an option).
    format: str = "mirrored"
    detected_format: str | None = None
    format_forced: bool = False
