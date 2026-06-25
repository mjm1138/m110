"""Tests for build_derived.py pure functions:
- parse_size_arcmin (catalog size string → max dimension in arcmin)
- default_star_removal_recommended (catalog entry → bool)
- recommend_star_removal_for_folder (slugs + catalog + override → bool)
- build_priorities (progress attachment, incl. track=false campaign entries)
"""
import pytest

from m110 import config, build_derived
from m110.build_derived import (
    parse_size_arcmin,
    default_star_removal_recommended,
    recommend_star_removal_for_folder,
    build_priorities,
    STAR_REMOVAL_MIN_ARCMIN,
)


# ── Seestar-stack-only captures (no lights → no sessions) ────────────────────

def test_seestar_only_target_is_captured(tmp_path, monkeypatch):
    images = tmp_path / "Images"
    (images / "M57" / "seestar-stacks").mkdir(parents=True)
    (images / "Empty").mkdir()                       # bare folder, not a capture
    monkeypatch.setattr(config, "IMAGES_DIR", images)
    totals = build_derived.build_totals({}, [])      # no sessions at all
    # the Seestar-only target is surfaced as a zero-integration capture
    assert "M57" in totals["by_folder"]
    assert totals["by_slug"]["m57"]["status"] == "initial"
    assert totals["by_slug"]["m57"]["integration_min"] == 0.0
    # a folder without any capture subdir is NOT a phantom capture
    assert "Empty" not in totals["by_folder"]


# ── build_priorities: the track flag ─────────────────────────────────────────

def _totals_with(folder, slug, minutes=300.0):
    """Minimal totals dict shaped like build_totals output."""
    rec = {
        "integration_min": minutes,
        "integration_hms": "5:00",
        "frames": 600,
        "session_count": 3,
        "status": "deep_stack",
    }
    return {"by_folder": {folder: rec}, "by_slug": {slug: rec}}


class TestBuildPrioritiesTrack:
    def test_tracked_entry_gets_progress(self):
        # A normal entry whose id maps to a folder picks up progress + percent.
        totals = _totals_with("M81 M82", "m81", minutes=300.0)
        pri = [{"id": "M81/M82", "target_integration_min": 600}]
        out = build_priorities(pri, totals, catalog={})
        assert out[0]["track"] is True
        assert out[0]["progress"] is not None
        assert out[0]["percent_complete"] == 50.0

    def test_untracked_campaign_entry_has_no_progress(self):
        # track=false: even though "M81/M82" *would* match a folder, the
        # campaign entry must render without an auto-rollup.
        totals = _totals_with("M81 M82", "m81", minutes=1500.0)
        pri = [{
            "id": "M81/M82 (LP Hα)",
            "target_integration_min": 240,
            "track": False,
        }]
        out = build_priorities(pri, totals, catalog={})
        assert out[0]["track"] is False
        assert out[0]["progress"] is None
        assert out[0]["percent_complete"] is None

    def test_track_defaults_true_when_absent(self):
        totals = {"by_folder": {}, "by_slug": {}}
        out = build_priorities([{"id": "M109"}], totals, catalog={})
        assert out[0]["track"] is True


# ── parse_size_arcmin ────────────────────────────────────────────────────────

class TestParseSizeArcmin:
    def test_simple_arcminutes(self):
        assert parse_size_arcmin("11'×7'") == 11.0

    def test_picks_longer_axis(self):
        # Returns max, not first
        assert parse_size_arcmin("3'×8'") == 8.0

    def test_degrees_converted_to_arcmin(self):
        assert parse_size_arcmin("3°×1°") == 180.0  # 3° = 180'

    def test_mixed_units(self):
        # Hypothetical mix — degrees and arcmin in one string
        assert parse_size_arcmin("1°×30'") == 60.0  # 1° wins

    def test_single_dimension(self):
        # Some catalog entries are just one number (e.g. "20'" for a globular)
        assert parse_size_arcmin("20'") == 20.0

    def test_decimal_values(self):
        assert parse_size_arcmin("1.5°") == 90.0
        assert parse_size_arcmin("8.5'×4.2'") == 8.5

    def test_empty_string(self):
        assert parse_size_arcmin("") == 0.0

    def test_no_dimensions_found(self):
        # String without unit markers
        assert parse_size_arcmin("unknown") == 0.0

    def test_none_input(self):
        # parse_size_arcmin should tolerate None (some catalog entries miss size)
        assert parse_size_arcmin(None) == 0.0


# ── default_star_removal_recommended ─────────────────────────────────────────

class TestDefaultStarRemoval:
    # Galaxies — type "galaxy"
    def test_large_galaxy_recommended(self):
        entry = {"type": "galaxy", "size": "27'×14'"}
        assert default_star_removal_recommended(entry) is True

    def test_small_galaxy_not_recommended(self):
        # 5' < 8' threshold
        entry = {"type": "galaxy", "size": "5'×3'"}
        assert default_star_removal_recommended(entry) is False

    def test_threshold_boundary_inclusive(self):
        # Exactly 8' should qualify (>= threshold)
        entry = {"type": "galaxy", "size": "8'×6'"}
        assert default_star_removal_recommended(entry) is True

    def test_galaxy_group(self):
        # "galaxy_group" contains "galaxy" → matches keyword
        entry = {"type": "galaxy_group", "size": "1.5°"}
        assert default_star_removal_recommended(entry) is True

    # Nebulae — catalog uses shorthand: "emission", "planetary", "reflection"
    def test_emission_nebula_large(self):
        entry = {"type": "emission", "size": "85'×60'"}  # M42
        assert default_star_removal_recommended(entry) is True

    def test_planetary_nebula_large(self):
        entry = {"type": "planetary", "size": "8'×6'"}  # M27
        assert default_star_removal_recommended(entry) is True

    def test_planetary_nebula_small(self):
        entry = {"type": "planetary", "size": "4'×3'"}  # M57
        assert default_star_removal_recommended(entry) is False

    def test_supernova_remnant(self):
        # "emission_snr" should match via the "emission" or "snr" keyword
        entry = {"type": "emission_snr", "size": "7'×5'"}
        # 7 < 8 → not recommended on size grounds, but type would qualify
        assert default_star_removal_recommended(entry) is False

    def test_reflection_nebula(self):
        entry = {"type": "reflection", "size": "10'×8'"}
        assert default_star_removal_recommended(entry) is True

    # Clusters — never recommended (no type keyword match)
    def test_globular_never_recommended(self):
        # Even at huge sizes, globulars are point sources of stars
        entry = {"type": "globular", "size": "20'"}
        assert default_star_removal_recommended(entry) is False

    def test_open_cluster_never_recommended(self):
        entry = {"type": "open_cluster", "size": "95'"}  # M44 size
        assert default_star_removal_recommended(entry) is False

    # Edge cases
    def test_missing_type(self):
        entry = {"size": "20'×10'"}
        assert default_star_removal_recommended(entry) is False

    def test_missing_size(self):
        entry = {"type": "galaxy"}
        assert default_star_removal_recommended(entry) is False

    def test_empty_dict(self):
        assert default_star_removal_recommended({}) is False


# ── recommend_star_removal_for_folder ────────────────────────────────────────

class TestFolderRecommendation:
    @pytest.fixture
    def catalog(self):
        """Minimal catalog fixture matching real entries."""
        return {
            "m51": {"type": "galaxy", "size": "11'×7'"},       # qualifies
            "m81": {"type": "galaxy", "size": "27'×14'"},      # qualifies
            "m82": {"type": "galaxy", "size": "11'×4'"},       # qualifies
            "m13": {"type": "globular", "size": "20'"},        # never
            "m92": {"type": "globular", "size": "14'"},        # never
            "m57": {"type": "planetary", "size": "4'×3'"},     # too small
            "m97": {"type": "planetary", "size": "3'"},        # too small
        }

    def test_single_qualifying_slug(self, catalog):
        assert recommend_star_removal_for_folder(["m51"], catalog, None) is True

    def test_single_non_qualifying_slug(self, catalog):
        assert recommend_star_removal_for_folder(["m13"], catalog, None) is False

    def test_multi_slug_any_qualifies(self, catalog):
        # M81 M82 — both qualify
        assert recommend_star_removal_for_folder(
            ["m81", "m82"], catalog, None
        ) is True

    def test_multi_slug_some_qualify(self, catalog):
        # If a folder fed both M51 (galaxy ≥8') and M97 (small planetary),
        # the ANY-qualifies rule says yes
        assert recommend_star_removal_for_folder(
            ["m51", "m97"], catalog, None
        ) is True

    def test_multi_slug_none_qualify(self, catalog):
        # M97 alone wouldn't qualify; M57 alone wouldn't either
        assert recommend_star_removal_for_folder(
            ["m97", "m57"], catalog, None
        ) is False

    def test_override_true_wins_over_default_false(self, catalog):
        # M97 wouldn't qualify by default, but override forces True
        assert recommend_star_removal_for_folder(
            ["m97"], catalog, override=True
        ) is True

    def test_override_false_wins_over_default_true(self, catalog):
        # M51 qualifies by default, but override forces False
        assert recommend_star_removal_for_folder(
            ["m51"], catalog, override=False
        ) is False

    def test_override_none_falls_through_to_default(self, catalog):
        # Explicit None == "no override, use default"
        assert recommend_star_removal_for_folder(
            ["m51"], catalog, override=None
        ) is True

    def test_unknown_slug_does_not_qualify(self, catalog):
        # Slug missing from catalog → no entry → no recommendation
        assert recommend_star_removal_for_folder(
            ["nonexistent"], catalog, None
        ) is False

    def test_empty_slug_list(self, catalog):
        # No slugs → no recommendation
        assert recommend_star_removal_for_folder([], catalog, None) is False


# ── threshold sanity check ───────────────────────────────────────────────────

class TestThresholdConfig:
    def test_threshold_is_8(self):
        # If someone bumps the threshold, this fails loudly so the change is
        # explicit (rather than a silent tightening / loosening).
        assert STAR_REMOVAL_MIN_ARCMIN == 8.0
