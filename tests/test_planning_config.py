"""Tests for observing-site / device planning profiles (m110/planning_config.py)."""
import pytest

from m110 import config, planning_config as pc


def test_defaults_when_file_missing(tmp_path):
    site = pc.load_site(path=tmp_path / "nope.toml")
    dev = pc.load_device(path=tmp_path / "nope.toml")
    assert site.latitude_deg == pytest.approx(40.015)
    assert site.timezone == "America/Denver"
    assert site.bortle == 0 and site.glow_mask == ""   # glow defaults empty
    assert dev.start_alt_ceiling_deg == pytest.approx(78.0)
    assert dev.max_exposure_s == 30


def test_load_site_from_toml(tmp_path):
    p = tmp_path / "darksite.toml"
    p.write_text(
        '[site]\nname = "Dark Site"\nlatitude_deg = 38.5\nlongitude_deg = -106.0\n'
        'elevation_m = 2800\ntimezone = "America/Denver"\n'
        '[horizon]\nmask = "darksite.hrz"\n'
        '[glow]\nbortle = 2\nsqm_zenith = 21.7\nmask = "glow.hrz"\n'
        'mask_narrowband = "glow_nb.hrz"\n')
    site = pc.load_site(path=p)
    assert site.name == "Dark Site"
    assert site.latitude_deg == pytest.approx(38.5)
    assert site.bortle == 2 and site.sqm_zenith == pytest.approx(21.7)
    # mask filenames resolve against the profile's own directory
    assert site.mask_path() == str(tmp_path / "darksite.hrz")
    assert site.glow_path() == str(tmp_path / "glow.hrz")
    assert site.glow_path(narrowband=True) == str(tmp_path / "glow_nb.hrz")


def test_glow_path_falls_back_to_broadband_when_no_narrowband(tmp_path):
    p = tmp_path / "home.toml"
    p.write_text('[site]\nname = "Home"\n[glow]\nmask = "glow.hrz"\n')
    site = pc.load_site(path=p)
    # no narrowband variant configured → narrowband request uses the broadband floor
    assert site.glow_path(narrowband=True) == str(tmp_path / "glow.hrz")


def test_unset_masks_return_none(tmp_path):
    site = pc.load_site(path=tmp_path / "nope.toml")
    assert site.mask_path() is None and site.glow_path() is None


def test_seeded_default_profile_loads(tmp_path):
    root = tmp_path / "M110"
    config.ensure_data_root(root)
    prof = root / config.INTERNAL_DIRNAME / "profiles" / "default.toml"
    assert prof.is_file()
    site = pc.load_site(path=prof)
    assert site.timezone == "America/Denver"
    assert site.bortle == 0  # glow layer ships empty for the light-dome phase to fill


def test_list_profiles_default_first(tmp_path, monkeypatch):
    d = tmp_path / "profiles"
    d.mkdir()
    for n in ("zeta.toml", "default.toml", "alpha.toml"):
        (d / n).write_text("[site]\n")
    monkeypatch.setattr(config, "PROFILES_DIR", d)
    assert pc.list_profiles() == ["default", "alpha", "zeta"]
