"""When an automatic backup is due (launch check + hourly while-running tick),
and the settings→options bridge both the dialog and the background worker use.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .. import config
from .options import (
    DEFAULT_DAILY_HOUR, DEFAULT_INTERVAL_HOURS, DEFAULT_MIN_FREE_GB, SETTING_AUTO,
    SETTING_DAILY_HOUR, SETTING_INTERVAL, SETTING_KEEP, SETTING_MIN_FREE, BackupOptions,
)
from .retention import list_snapshots


def options_from_settings(destination: Path) -> BackupOptions:
    """Build BackupOptions with the saved retention policy for a destination."""
    def _int(key):
        v = config.get_setting(key)
        return int(v) if v not in (None, "", 0) else None

    # Min-free defaults to 100 GB when never configured; an explicit 0 means "off".
    # (Only an absent key gets the default — a stored 0/null is an intentional off.)
    mf = config.get_setting(SETTING_MIN_FREE, DEFAULT_MIN_FREE_GB)
    try:
        min_free = float(mf)
    except (TypeError, ValueError):
        min_free = DEFAULT_MIN_FREE_GB
    return BackupOptions(
        destination=Path(destination),
        retention_keep=_int(SETTING_KEEP),
        min_free_gb=min_free if min_free > 0 else None,
    )


def _auto_enabled_and_reachable(destination: Path) -> Path | None:
    """The destination path iff auto-backup is on and the folder is reachable, else
    None (missing/unreachable → not due, no nag). Shared by both auto triggers."""
    if not config.get_setting(SETTING_AUTO, False):
        return None
    dest = Path(destination)
    return dest if dest.is_dir() else None


def _interval_hours() -> float:
    return float(config.get_setting(SETTING_INTERVAL, DEFAULT_INTERVAL_HOURS) or
                 DEFAULT_INTERVAL_HOURS)


def due_for_auto_backup(destination: Path) -> bool:
    """True iff auto-backup is enabled, the destination is reachable, and it's been
    at least the configured interval since the newest snapshot (drives the
    launch-time trigger). Missing/unreachable destination → not due (no nag)."""
    dest = _auto_enabled_and_reachable(destination)
    if dest is None:
        return False
    snaps = list_snapshots(dest)
    if not snaps:
        return True
    age_hours = (datetime.now() - snaps[0].created).total_seconds() / 3600.0
    return age_hours >= _interval_hours()


def due_for_scheduled_backup(destination: Path, now: datetime | None = None) -> bool:
    """True iff auto-backup is enabled, the destination is reachable, the local clock
    has reached the daily backup hour (default 02:00), we haven't already backed up
    since that hour today, and the newest snapshot is at least `interval` hours old.

    Drives the hourly while-running tick, so a long-lived session (the app left
    running for days) still gets a daily snapshot rather than only backing up at
    launch. The interval acts as a min-age guard here so a fresh launch backup
    doesn't immediately re-fire at 02:00; the once-per-day guard keeps it from
    repeating through the rest of the day."""
    dest = _auto_enabled_and_reachable(destination)
    if dest is None:
        return False
    now = now or datetime.now()
    hour = int(config.get_setting(SETTING_DAILY_HOUR, DEFAULT_DAILY_HOUR) or
               DEFAULT_DAILY_HOUR)
    if now.hour < hour:
        return False                        # before today's scheduled time
    snaps = list_snapshots(dest)
    if not snaps:
        return True
    newest = snaps[0].created
    scheduled_today = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if newest >= scheduled_today:
        return False                        # already backed up since 02:00 today
    age_hours = (now - newest).total_seconds() / 3600.0
    return age_hours >= _interval_hours()
