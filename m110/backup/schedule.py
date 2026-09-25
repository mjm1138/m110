"""When an automatic backup is due (launch check + hourly while-running tick),
and the settings→options bridge both the dialog and the background worker use.
"""
from __future__ import annotations

from datetime import datetime

from .. import config
from .destination import parse_destination
from .options import DEFAULT_DAILY_HOUR, SETTING_DAILY_HOUR, BackupOptions
from .retention import list_snapshots
from .slots import SLOT_CLOUD, load_slot


def options_from_settings(slot: str) -> BackupOptions:
    """Build BackupOptions from one slot's saved destination and policy."""
    s = load_slot(slot)
    return BackupOptions(
        destination=s.destination,
        retention_keep=s.retention_keep or None,
        # A bucket has no volume to fill; the engine ignores it there anyway.
        min_free_gb=(s.min_free_gb or None) if slot != SLOT_CLOUD else None,
        scope=s.scope,
        slot=slot,
    )


def _auto_enabled_and_reachable(s):
    """The slot's destination iff it has auto-backup on and is reachable, else
    None (unset/unreachable → not due, no nag). Shared by both auto triggers.

    A cloud destination is taken on trust rather than probed: reachability there
    costs a network round-trip, and this runs at launch and on every hourly tick —
    on a laptop that is offline it would be a timeout, not an answer. Due-ness is
    a question about *time*; if the bucket turns out to be unreachable, the run
    itself reports it through the normal error path.

    The raw string goes to `parse_destination`, never `Path(dest)` first —
    `Path("s3://bucket/x")` collapses to `s3:/bucket/x`, a local folder."""
    if not (s.auto and s.destination):
        return None
    dest = parse_destination(s.destination)
    if not dest.is_local:
        return dest
    return dest if dest.path.is_dir() else None


def due_for_auto_backup(slot: str) -> bool:
    """True iff this slot has auto-backup on, its destination is reachable, and
    it's been at least the slot's interval since the newest snapshot there
    (drives the launch-time trigger)."""
    s = load_slot(slot)
    dest = _auto_enabled_and_reachable(s)
    if dest is None:
        return False
    snaps = list_snapshots(dest)
    if not snaps:
        return True
    age_hours = (datetime.now() - snaps[0].created).total_seconds() / 3600.0
    return age_hours >= s.interval_hours


def due_for_scheduled_backup(slot: str, now: datetime | None = None) -> bool:
    """True iff the slot has auto-backup on, its destination is reachable, the local clock
    has reached the daily backup hour (default 02:00), we haven't already backed up
    since that hour today, and the newest snapshot is at least `interval` hours old.

    Drives the hourly while-running tick, so a long-lived session (the app left
    running for days) still gets a daily snapshot rather than only backing up at
    launch. The interval acts as a min-age guard here so a fresh launch backup
    doesn't immediately re-fire at 02:00; the once-per-day guard keeps it from
    repeating through the rest of the day."""
    s = load_slot(slot)
    dest = _auto_enabled_and_reachable(s)
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
    return age_hours >= s.interval_hours
