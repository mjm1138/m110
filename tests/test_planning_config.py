"""Tests for observing-site / device planning profiles (m110/planning_config.py)."""
import pytest

from m110 import config, planning_config as pc


def test_defaults_when_file_missing(tmp_path):
    site = pc.load_site(path=tmp_path / "nope.toml")
    dev = pc.load_device(path=tmp_path / "nope.toml")
    assert site.latitude_deg == pytest.approx(40.014)
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


# ── writers ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    d = tmp_path / "profiles"
    d.mkdir()
    monkeypatch.setattr(config, "PROFILES_DIR", d)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    return d


def test_save_site_roundtrip(profiles_dir):
    s = pc.Site(name="Dark Site A", latitude_deg=38.5, longitude_deg=-105.9,
                elevation_m=2600, timezone="America/Denver", bortle=3,
                sqm_zenith=21.6, horizon_mask="skyline.hrz")
    pc.save_site(s, "dark-site-a")
    back = pc.load_site("dark-site-a")
    assert back.name == "Dark Site A"
    assert back.latitude_deg == pytest.approx(38.5)
    assert back.longitude_deg == pytest.approx(-105.9)
    assert back.elevation_m == pytest.approx(2600)
    assert back.bortle == 3 and back.sqm_zenith == pytest.approx(21.6)
    assert back.horizon_mask == "skyline.hrz"


def test_format_site_toml_parses_back(profiles_dir):
    import tomllib
    s = pc.Site(name='Weird "quoted" name', latitude_deg=0.0, longitude_deg=0.0)
    text = pc.format_site_toml(s)
    parsed = tomllib.loads(text)                    # valid TOML, quotes escaped
    assert parsed["site"]["name"] == 'Weird "quoted" name'


def test_delete_profile_protects_default(profiles_dir):
    with pytest.raises(ValueError):
        pc.delete_profile(pc.DEFAULT_PROFILE)


def test_delete_profile_resets_active(profiles_dir):
    pc.save_site(pc.Site(name="Trip"), "trip")
    pc.set_active_profile("trip")
    assert pc.active_profile() == "trip"
    pc.delete_profile("trip")
    assert "trip" not in pc.list_profiles()
    assert pc.active_profile() == pc.DEFAULT_PROFILE   # fell back


def test_active_profile_falls_back_to_first_available(profiles_dir):
    # No saved active + no profiles yet → DEFAULT_PROFILE.
    assert pc.active_profile() == pc.DEFAULT_PROFILE
    pc.save_site(pc.Site(name="Home"), "default")
    pc.save_site(pc.Site(name="Trip"), "trip")
    # A stale/removed active selection is ignored.
    pc.set_active_profile("gone")
    assert pc.active_profile() == "default"            # first available


def test_import_horizon_mask_validates_and_copies(profiles_dir, tmp_path):
    src = tmp_path / "theo.hrz"
    src.write_text("# skyline\n0 12\n90 8\n180 20\n270 6\n")
    fname = pc.import_horizon_mask(src, "home")
    assert (profiles_dir / fname).is_file()
    assert fname.endswith(".hrz")


def test_import_horizon_mask_rejects_garbage(profiles_dir, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("just some prose, no az/alt pairs\n")
    with pytest.raises(ValueError):
        pc.import_horizon_mask(bad, "home")


# ── geocode (online, but fetch is injected) ─────────────────────────────────────

def test_geocode_parses_top_result():
    def fake(url):
        return [{"lat": "40.015", "lon": "-105.27", "display_name": "Boulder, CO, USA"}]
    lat, lon, name = pc.geocode("Boulder", fetch=fake)
    assert lat == pytest.approx(40.015) and lon == pytest.approx(-105.27)
    assert "Boulder" in name


def test_geocode_degrades_on_error():
    def boom(url):
        raise OSError("offline")
    assert pc.geocode("anywhere", fetch=boom) is None


def test_geocode_empty_query():
    assert pc.geocode("   ", fetch=lambda url: [{"lat": "1", "lon": "2"}]) is None


def test_geocode_no_match():
    assert pc.geocode("zzz", fetch=lambda url: []) is None
