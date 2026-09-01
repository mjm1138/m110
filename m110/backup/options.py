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
# How much of the library goes to this destination — see scope.py. One setting
# rather than a map keyed by destination: there is exactly one destination today,
# and it becomes a per-row field when destinations become a list (issue #93).
SETTING_SCOPE = "backup_scope"

# S3-compatible cloud destinations (issue #93). The **secret** access key is NOT
# here — it lives in the OS keyring (see backends/s3.py). An access key id is an
# identifier rather than a secret, and the UI has to be able to show which key is
# configured, so it stays in settings alongside the endpoint.
SETTING_S3_ENDPOINT = "backup_s3_endpoint_url"
SETTING_S3_REGION = "backup_s3_region"
SETTING_S3_ACCESS_KEY = "backup_s3_access_key_id"


@dataclass
class BackupOptions:
    destination: Path
    retention_keep: int | None = None       # keep N newest snapshots (None = all)
    min_free_gb: float | None = None         # delete oldest until ≥ this free
    scope: str | None = None                 # None = the "everything" default


@dataclass(frozen=True)
class SnapshotRef:
    """How to reach one snapshot's bytes when it has no filesystem path.

    A pooled snapshot on object storage isn't addressable as a `Path`, so this —
    destination plus the manifest's key — is the handle the UI carries and the
    format resolves through. Local snapshots keep `SnapshotInfo.path` as well, so
    every existing caller that passes a path still works unchanged.
    """
    destination: str
    key: str
    store_name: str | None = None


@dataclass
class SnapshotInfo:
    # None for a snapshot with no filesystem path (pooled on object storage) —
    # reach those through `ref`. Deliberately not faked with a pseudo-path: code
    # that assumes a path should fail loudly rather than build a wrong one.
    path: Path | None
    timestamp: str
    created: datetime
    file_count: int
    total_bytes: int
    store_version: str | None = None
    hardlinks: bool = True
    format: str = "mirrored"
    ref: SnapshotRef | None = None


@dataclass
class DestinationInfo:
    """What we can learn about a destination *before* backing up to it.

    The hardlink answer is the important one: where a filesystem can't link,
    every snapshot silently becomes a full copy of the library (issue #92), and
    until now the user could only find that out after the first run — the
    warning was read back out of a manifest. Probing up front means the dialog
    can say so while the destination is still being chosen.
    """
    path: Path | None
    exists: bool
    writable: bool
    hardlinks: bool
    free_bytes: int | None      # None = no volume to measure (an object store)
    snapshot_count: int
    newest: SnapshotInfo | None = None
    error: str | None = None
    # What the user typed, and which backend it resolved to. `path` is None for a
    # cloud destination, so callers that need to identify a destination — cache
    # keys, "is this still what's in the field?" — must use `destination`.
    destination: str = ""
    kind: str = "local"
    # Which snapshot format the *next* backup here would use, what's already
    # there (None = unused destination), and whether the destination left no
    # choice (it can't hardlink, so mirrored isn't an option).
    format: str = "mirrored"
    detected_format: str | None = None
    format_forced: bool = False
