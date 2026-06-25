"""Tests for reference-based metadata backfill (season_from_ra + fill_missing_*)
and the regenerated Caldwell reference (every member now carries a season)."""
import tomllib

from m110 import catalog, config


# ── season_from_ra ────────────────────────────────────────────────────────────

def test_season_from_ra_matches_curated_sample():
    # Calibrated against the bundled Messier seasons (see seed/objects.toml).
    assert catalog.season_from_ra(10.6847) == "Sep–Nov"      # M31, ~0.7h
    assert catalog.season_from_ra(83.63) == "Dec–Feb"        # M1, ~5.6h
    # wraps cleanly and rejects junk
    assert catalog.season_from_ra(0.0) == catalog.season_from_ra(360.0)
    assert catalog.season_from_ra(None) == ""
    assert catalog.season_from_ra("nope") == ""


def test_season_from_ra_reproduces_most_curated_seasons():
    ref = catalog.load_reference()
    pairs = [(e["ra_deg"], e["season"]) for e in ref.values()
             if e.get("ra_deg") is not None and e.get("season")
             and "–" in e["season"] and "Year" not in e["season"]]
    exact = sum(1 for ra, se in pairs if catalog.season_from_ra(ra) == se)
    assert exact / len(pairs) > 0.9                          # ≈98% on the bundled data


# ── fill_missing_metadata ─────────────────────────────────────────────────────

def _seed_lib(tmp_path, monkeypatch, extra=""):
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)
    if extra:
        with lib.open("a") as f:
            f.write(extra)
    return lib


_STALE_STUB = (
    '\n[catalog.ngc-6992]\nid = "NGC 6992"\nname = ""\ntype = "unknown"\n'
    'ra_deg = 314.0792\ndec_deg = 31.7433\n')


def test_fill_missing_from_reference(tmp_path, monkeypatch):
    _seed_lib(tmp_path, monkeypatch, extra=_STALE_STUB)
    filled = catalog.fill_missing_metadata("ngc-6992")
    assert filled["name"] == "East Veil Nebula"
    assert filled["type"] == "emission_snr"
    assert filled["season"]                                  # derived from RA
    e = catalog.load_library()["ngc-6992"]
    assert e["name"] == "East Veil Nebula" and e["type"] == "emission_snr"
    assert e["ra_deg"] == 314.0792                           # user/stub coord preserved
    assert catalog.fill_missing_metadata("ngc-6992") == {}   # idempotent


def test_fill_preserves_user_values(tmp_path, monkeypatch):
    stub = ('\n[catalog.ngc-6992]\nid = "NGC 6992"\nname = "My Veil"\n'
            'type = "galaxy"\nra_deg = 314.0792\ndec_deg = 31.7433\n')
    _seed_lib(tmp_path, monkeypatch, extra=stub)
    filled = catalog.fill_missing_metadata("ngc-6992")
    assert "name" not in filled and "type" not in filled     # real values untouched
    e = catalog.load_library()["ngc-6992"]
    assert e["name"] == "My Veil" and e["type"] == "galaxy"


def test_write_library_preserves_unknown_keys(tmp_path, monkeypatch):
    stub = ('\n[catalog.ngc-6992]\nid = "NGC 6992"\nname = ""\ntype = "unknown"\n'
            'ra_deg = 314.0792\ndec_deg = 31.7433\ncustom_field = "keep me"\n')
    _seed_lib(tmp_path, monkeypatch, extra=stub)
    catalog.fill_missing_metadata("ngc-6992")                # triggers a rewrite
    e = catalog.load_library()["ngc-6992"]
    assert e["custom_field"] == "keep me"                    # extra key survived


def test_write_library_roundtrips_boolean(tmp_path, monkeypatch):
    # A hand-added boolean must round-trip as valid TOML (lowercase true/false),
    # not Python's True/False (bool is an int subclass — easy to mis-serialize).
    stub = ('\n[catalog.ngc-6992]\nid = "NGC 6992"\nname = ""\ntype = "unknown"\n'
            'ra_deg = 314.0792\ndec_deg = 31.7433\nobstructed = true\n')
    _seed_lib(tmp_path, monkeypatch, extra=stub)
    catalog.fill_missing_metadata("ngc-6992")                # rewrite
    text = config.LIBRARY_TOML.read_text()
    assert "obstructed = true" in text and "obstructed = True" not in text
    assert catalog.load_library()["ngc-6992"]["obstructed"] is True   # re-parses


def test_fill_all_missing(tmp_path, monkeypatch):
    extra = _STALE_STUB + (
        '\n[catalog.ngc-6960]\nid = "NGC 6960"\nname = ""\ntype = "unknown"\n'
        'ra_deg = 311.4083\ndec_deg = 30.7083\n')
    _seed_lib(tmp_path, monkeypatch, extra=extra)
    out = catalog.fill_all_missing_metadata()
    assert {"ngc-6992", "ngc-6960"} <= set(out)
    assert catalog.fill_all_missing_metadata() == {}         # idempotent


def test_load_library_reports_bad_toml(tmp_path, monkeypatch):
    import pytest
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    lib.write_text('[catalog.m104]\nobstructed = True\n')   # Python bool → invalid TOML
    with pytest.raises(catalog.LibraryParseError) as ei:
        catalog.load_library()
    assert str(lib) in str(ei.value) and "true" in str(ei.value)   # names file + hint


# ── regenerated Caldwell reference ────────────────────────────────────────────

def test_caldwell_reference_has_season():
    ref = catalog.load_reference()
    assert ref["ngc-6992"]["name"] == "East Veil Nebula"
    assert ref["ngc-6992"].get("season")                     # regenerated with season
    members = catalog.load_bundled_catalog("caldwell")["members"]
    missing = [s for s in members if not ref.get(s, {}).get("season")]
    assert missing == []                                     # every Caldwell member has one
