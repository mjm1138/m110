"""Backup scope tiers (issue #93).

The `essentials` tier is what makes offsite backup affordable, and it is a
*deletion policy in disguise*: anything it leaves out is something the user will
not get back from a cloud restore. So these tests pin both directions — what it
drops, and, more importantly, what it must never drop.
"""
import pytest

from m110 import config
from m110.backup.scope import (DEFAULT_SCOPE, SCOPE_ESSENTIALS, SCOPE_EVERYTHING,
                               is_excluded, iter_source_files)

# Kept at every tier. Each is either hand-written, a deliverable, or the state
# that makes the rest meaningful — none of it is regenerable from the frames.
KEEP_ALWAYS = [
    "Objects/M51/journal.md",
    "Plans/2026-09-01_messier-marathon.md",
    f"{config.INTERNAL_DIRNAME}/library.toml",
    f"{config.INTERNAL_DIRNAME}/goals.toml",
    f"{config.INTERNAL_DIRNAME}/pins.toml",
    f"{config.INTERNAL_DIRNAME}/profiles/default.toml",
    "Images/M51/finished/M51_final.tif",
    "Images/M51/stacks/M51_stacked.fit",
    "Images/M51/seestar-stacks/M51_device.fit",
    "Images/M51/siril/presets/naztronomy.ssf",
    "Images/M51/siril/next-steps.md",
    "Media/Lunar_photo/moon.jpg",
]

# Dropped at `essentials` only — the bulk that a user can keep locally.
BULK = [
    "Images/M51/lights/Light_M51_10s_001.fit",
    "Images/M51/rejected/Light_M51_10s_002.fit",
    "Images/M51/previews/Light_M51_10s_001.jpg",
    "Images/M51/siril/archive/20260101-120000/result.fit",
    "Images/M51/siril/Ha/archive/20260101-120000/result.fit",
    "Images/M51/astrowizard/archive/20260101-120000/M51_AW3_str.tif",
]

# Never backed up at any tier — regenerable, or a hardlink to bytes already
# stored under their real path.
NEVER = [
    f"{config.INTERNAL_DIRNAME}/derived/totals.json",
    f"{config.INTERNAL_DIRNAME}/renders/hero/m51.jpg",
    f"{config.INTERNAL_DIRNAME}/sessions.jsonl",
    "Images/M51/siril/lights/Light_M51_10s_001.fit",
    "Images/M51/siril/Ha/lights/Light_M51_10s_001.fit",
]


@pytest.mark.parametrize("rel", KEEP_ALWAYS)
@pytest.mark.parametrize("scope", [SCOPE_EVERYTHING, SCOPE_ESSENTIALS])
def test_irreplaceable_work_survives_every_tier(rel, scope):
    assert is_excluded(rel, scope) is False


@pytest.mark.parametrize("rel", BULK)
def test_bulk_frames_are_kept_at_everything_and_dropped_at_essentials(rel):
    assert is_excluded(rel, SCOPE_EVERYTHING) is False
    assert is_excluded(rel, SCOPE_ESSENTIALS) is True


@pytest.mark.parametrize("rel", NEVER)
@pytest.mark.parametrize("scope", [SCOPE_EVERYTHING, SCOPE_ESSENTIALS])
def test_regenerable_and_linked_inputs_are_never_backed_up(rel, scope):
    assert is_excluded(rel, scope) is True


def test_the_default_is_everything_so_existing_backups_do_not_narrow():
    """A stored setting that predates tiers reads as absent, and the tier that
    absence resolves to has to be the one that keeps backing up what it always
    did — a silent narrowing would quietly stop protecting the frames."""
    assert DEFAULT_SCOPE == SCOPE_EVERYTHING
    for rel in BULK:
        assert is_excluded(rel) is False


def test_iter_source_files_applies_the_tier(tmp_path):
    for rel in KEEP_ALWAYS + BULK + NEVER:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")

    everything = set(iter_source_files(tmp_path, SCOPE_EVERYTHING))
    essentials = set(iter_source_files(tmp_path, SCOPE_ESSENTIALS))

    assert set(KEEP_ALWAYS) <= essentials <= everything
    assert set(BULK) <= everything
    assert not (set(BULK) & essentials)
    assert not (set(NEVER) & everything)


def test_a_target_named_like_a_tier_is_not_confused(tmp_path):
    """The rule matches `Images/<target>/<tier>/`, so the tier name has to be read
    at the right depth — a capture folder called `lights` is a target, not a tier."""
    assert is_excluded("Images/lights/finished/x.tif", SCOPE_ESSENTIALS) is False
    assert is_excluded("Images/lights/lights/x.fit", SCOPE_ESSENTIALS) is True
