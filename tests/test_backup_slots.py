"""The two backup slots (local + cloud): defaults, the legacy flat-key read,
per-slot persistence, and each slot scheduling on its own settings.

All on a temp store and a throwaway settings file (never live data).
"""
import json
from datetime import datetime, timedelta

import pytest

from m110 import backup, config
from tests._helpers import seed_capture, seed_root

LOCAL, CLOUD = backup.SLOT_LOCAL, backup.SLOT_CLOUD


@pytest.fixture
def root(tmp_path, monkeypatch):
    return seed_root(tmp_path, monkeypatch)


# ── defaults ────────────────────────────────────────────────────────────────

def test_fresh_settings_give_two_unconfigured_slots_with_their_own_defaults(root):
    slots = backup.load_slots()
    assert backup.configured_slots() == []
    assert slots[LOCAL].scope == backup.SCOPE_EVERYTHING
    assert slots[LOCAL].min_free_gb == backup.DEFAULT_MIN_FREE_GB
    assert slots[LOCAL].format == backup.FORMAT_MIRRORED
    # Offsite: essentials, and never surprise-delete a copy by count.
    assert slots[CLOUD].scope == backup.SCOPE_ESSENTIALS
    assert slots[CLOUD].retention_keep == 0
    assert slots[CLOUD].format == backup.FORMAT_POOLED


# ── legacy flat keys ────────────────────────────────────────────────────────

def _legacy(dest, **extra):
    config.save_setting(backup.SETTING_DEST, dest)
    config.save_setting(backup.SETTING_AUTO, True)
    config.save_setting(backup.SETTING_INTERVAL, 6)
    config.save_setting(backup.SETTING_KEEP, 30)
    for k, v in extra.items():
        config.save_setting(k, v)


def test_a_legacy_folder_destination_becomes_the_local_slot(root):
    _legacy("/Volumes/Archive/M110", **{backup.SETTING_MIN_FREE: 0,
                                         backup.SETTING_FORMAT: backup.FORMAT_POOLED,
                                         backup.SETTING_SCOPE: backup.SCOPE_ESSENTIALS})
    local, cloud = backup.load_slot(LOCAL), backup.load_slot(CLOUD)
    assert local.destination == "/Volumes/Archive/M110"
    assert (local.auto, local.interval_hours, local.retention_keep) == (True, 6, 30)
    assert local.scope == backup.SCOPE_ESSENTIALS
    assert local.min_free_gb == 0                    # a stored 0 stays "off"
    assert local.format == backup.FORMAT_POOLED
    assert not cloud.configured
    assert backup.configured_slots() == [LOCAL]


def test_a_legacy_bucket_destination_becomes_the_cloud_slot(root):
    _legacy("s3://bucket/m110", **{backup.SETTING_FORMAT: backup.FORMAT_MIRRORED})
    local, cloud = backup.load_slot(LOCAL), backup.load_slot(CLOUD)
    assert cloud.destination == "s3://bucket/m110"
    assert (cloud.auto, cloud.interval_hours, cloud.retention_keep) == (True, 6, 30)
    # Format and free-space were always about a local volume: they stay local.
    assert not local.configured
    assert local.format == backup.FORMAT_MIRRORED
    assert local.min_free_gb == backup.DEFAULT_MIN_FREE_GB


def test_the_first_save_writes_the_new_shape_and_keeps_the_old_keys(root):
    _legacy("/Volumes/Archive/M110")
    backup.update_slot(CLOUD, destination="s3://bucket/m110")

    stored = json.loads(config.SETTINGS_FILE.read_text())
    assert stored[backup.SETTING_DESTINATIONS]["local"]["destination"] == \
        "/Volumes/Archive/M110"
    assert stored[backup.SETTING_DESTINATIONS]["cloud"]["destination"] == \
        "s3://bucket/m110"
    # Never destructive: a downgrade still finds its settings.
    assert stored[backup.SETTING_DEST] == "/Volumes/Archive/M110"
    assert backup.configured_slots() == [LOCAL, CLOUD]


def test_garbage_in_the_stored_dict_falls_back_per_field(root):
    config.save_setting(backup.SETTING_DESTINATIONS, {
        "local": {"destination": "/x", "scope": "bogus", "interval_hours": "abc",
                  "retention_keep": -3, "unknown": 1},
    })
    local = backup.load_slot(LOCAL)
    assert local.destination == "/x"
    assert local.scope == backup.SCOPE_EVERYTHING
    assert local.interval_hours == backup.DEFAULT_INTERVAL_HOURS
    assert local.retention_keep == 0
    assert not backup.load_slot(CLOUD).configured


# ── writing ─────────────────────────────────────────────────────────────────

def test_update_slot_changes_only_the_named_fields_of_one_slot(root):
    backup.update_slot(LOCAL, destination="/a", auto=True)
    backup.update_slot(CLOUD, destination="s3://b/c")
    backup.record_backup(LOCAL, datetime(2026, 9, 1, 3, 0))
    backup.update_slot(LOCAL, retention_keep=5)

    local = backup.load_slot(LOCAL)
    assert (local.destination, local.auto, local.retention_keep) == ("/a", True, 5)
    assert local.last_backup == datetime(2026, 9, 1, 3, 0)
    assert backup.load_slot(CLOUD).destination == "s3://b/c"


@pytest.mark.parametrize("slot,dest,ok", [
    (LOCAL, "/Volumes/Backup", True),
    (LOCAL, "s3://bucket/x", False),
    (CLOUD, "s3://bucket/x", True),
    (CLOUD, "/Volumes/Backup", False),
    (LOCAL, "", True),
    (CLOUD, "", True),
])
def test_each_slot_only_takes_its_own_kind_of_destination(slot, dest, ok):
    assert (backup.check_slot_destination(slot, dest) is None) is ok


# ── running + scheduling per slot ───────────────────────────────────────────

def test_a_successful_run_stamps_its_slot_only(root, tmp_path):
    seed_capture(root)
    backup.update_slot(LOCAL, destination=str(tmp_path / "backups"))
    backup.create_snapshot(backup.options_from_settings(LOCAL))

    assert backup.load_slot(LOCAL).last_backup is not None
    assert backup.load_slot(CLOUD).last_backup is None


def test_an_ad_hoc_run_stamps_nothing(root, tmp_path):
    seed_capture(root)
    backup.create_snapshot(backup.BackupOptions(destination=tmp_path / "b"))
    assert backup.load_slot(LOCAL).last_backup is None


def test_options_come_from_the_slot(root):
    backup.update_slot(CLOUD, destination="s3://b/c", retention_keep=4)
    opts = backup.options_from_settings(CLOUD)
    assert opts.destination == "s3://b/c"
    assert opts.retention_keep == 4
    assert opts.scope == backup.SCOPE_ESSENTIALS
    assert opts.min_free_gb is None          # a bucket has no volume to fill
    assert opts.slot == CLOUD


def test_each_slot_is_due_on_its_own_interval(root, tmp_path, monkeypatch):
    """Two destinations, two schedules — the local drive every 6 h, the cloud
    every 48 h — from one run of snapshots a day old."""
    seed_capture(root)
    local_dest = tmp_path / "local"
    backup.update_slot(LOCAL, destination=str(local_dest), auto=True,
                       interval_hours=6)
    backup.update_slot(CLOUD, destination="s3://b/c", auto=True, interval_hours=48)
    day_old = backup.SnapshotInfo(path=None, timestamp="", file_count=1,
                                  total_bytes=1,
                                  created=datetime.now() - timedelta(hours=24))
    monkeypatch.setattr("m110.backup.schedule.list_snapshots",
                        lambda dest: [day_old])
    local_dest.mkdir()

    assert backup.due_for_auto_backup(LOCAL) is True
    assert backup.due_for_auto_backup(CLOUD) is False

    backup.update_slot(CLOUD, auto=False, interval_hours=1)
    assert backup.due_for_auto_backup(CLOUD) is False     # off → never due


def test_an_unconfigured_slot_is_never_due(root):
    backup.update_slot(CLOUD, auto=True)
    assert backup.due_for_auto_backup(CLOUD) is False
    assert backup.due_for_scheduled_backup(CLOUD) is False
