"""Tests for the horizon / obstruction mask + the light-pollution glow layer
(m110/horizon.py). Mask-parsing cases are ported from the sibling Astronomy
project's planning tests; effective_floor / is_below_floor are new for M110."""
import pytest

from m110 import horizon


def _write_mask(tmp_path, body, name="mask.csv"):
    p = tmp_path / name
    p.write_text(body)
    return str(p)


# ── parsing / interpolation (ported) ─────────────────────────────────────────

def test_mask_parses_comments_header_and_trailing_commas(tmp_path):
    p = _write_mask(tmp_path, "# comment,,,\naz,alt,,\n0,30,,\n90,65,,\n180,17,,\n270,60,,\n")
    assert horizon.load_mask(p) == [(0.0, 30.0), (90.0, 65.0), (180.0, 17.0), (270.0, 60.0)]


def test_horizon_interpolation_midpoint(tmp_path):
    pts = horizon.load_mask(_write_mask(tmp_path, "az,alt\n0,10\n90,30\n"))
    assert horizon.horizon_alt(45, pts) == pytest.approx(20.0)


def test_horizon_wraps_through_north(tmp_path):
    pts = horizon.load_mask(_write_mask(tmp_path, "az,alt\n350,20\n10,40\n"))
    assert horizon.horizon_alt(0, pts) == pytest.approx(30.0)
    assert horizon.horizon_alt(355, pts) == pytest.approx(25.0)


def test_is_obstructed(tmp_path):
    pts = horizon.load_mask(_write_mask(tmp_path, "az,alt\n0,10\n90,65\n180,17\n270,60\n"))
    assert horizon.is_obstructed(90, 50, pts)       # below the east house
    assert not horizon.is_obstructed(90, 70, pts)   # above it
    assert not horizon.is_obstructed(180, 30, pts)  # open south


def test_empty_mask_raises(tmp_path):
    with pytest.raises(ValueError):
        horizon.load_mask(_write_mask(tmp_path, "# nothing here\n"))


def test_hrz_space_separated_parses(tmp_path):
    p = tmp_path / "backyard.hrz"
    p.write_text("0 30.0\n90 65.0\n180 17.0\n270 60.0\n360 30.0\n")
    pts = horizon.load_mask(str(p))
    assert [a for a, _ in pts] == [0.0, 90.0, 180.0, 270.0]  # closing 360 wraps onto 0
    assert horizon.horizon_alt(0, pts) == pytest.approx(30.0)
    assert horizon.is_obstructed(90, 50, pts)


def test_hrz_negative_altitudes_kept(tmp_path):
    p = tmp_path / "sea.hrz"
    p.write_text("0 -1.5\n180 -0.5\n")
    pts = horizon.load_mask(str(p))
    assert not horizon.is_obstructed(90, 0.0, pts)  # open horizon below zero


def test_hrz_tolerates_metadata_and_semicolon_comments(tmp_path):
    p = tmp_path / "exported.hrz"
    p.write_text("; exported by some app\nname backyard\n0 12\n180 20\n")
    assert horizon.load_mask(str(p)) == [(0.0, 12.0), (180.0, 20.0)]


def test_duplicate_azimuth_keeps_higher(tmp_path):
    pts = horizon.load_mask(_write_mask(tmp_path, "az,alt\n0,10\n100,5\n100,60\n200,10\n"))
    assert horizon.horizon_alt(100, pts) == pytest.approx(60.0)


# ── glow layer: effective_floor / is_below_floor (new) ───────────────────────

def test_is_obstructed_empty_mask_is_open():
    assert not horizon.is_obstructed(90, 1.0, [])  # no mask → open horizon


def test_effective_floor_takes_the_max_layer(tmp_path):
    physical = horizon.load_mask(_write_mask(tmp_path, "az,alt\n0,10\n180,5\n", "h.csv"))
    glow = horizon.load_mask(_write_mask(tmp_path, "az,alt\n0,8\n180,30\n", "g.csv"))
    # North: physical (10) dominates the low glow (8); South: the city dome (30) dominates.
    assert horizon.effective_floor(0, physical, glow) == pytest.approx(10.0)
    assert horizon.effective_floor(180, physical, glow) == pytest.approx(30.0)


def test_effective_floor_ignores_empty_and_defaults_open():
    assert horizon.effective_floor(123) == pytest.approx(-90.0)        # no masks → open
    pts = [(0.0, 20.0), (180.0, 20.0)]
    assert horizon.effective_floor(90, [], pts) == pytest.approx(20.0)  # empty layer skipped


def test_is_below_floor_demotes_toward_dome_not_away(tmp_path):
    # A southern light dome (Boulder→Denver): high floor in the south, open north.
    glow = horizon.load_mask(_write_mask(tmp_path, "az,alt\n0,5\n180,30\n", "glow.csv"))
    assert horizon.is_below_floor(180, 25, glow)        # low toward the dome → demoted
    assert not horizon.is_below_floor(0, 25, glow)      # same altitude away from it → fine
