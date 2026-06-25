"""Tests for 5c — add arbitrary objects + online (Simbad) enrichment.

Network is always mocked: the success paths monkeypatch `catalog.resolve_object_online`,
and the graceful-degradation path forces the astroquery import to fail. No test ever
makes a real network call.
"""
import sys

import pytest

from m110 import catalog, config


def _store(tmp_path, monkeypatch):
    """A fully seeded temp store (Messier Library + reference + Objects dir)."""
    root = tmp_path / "M110"
    internal = root / config.INTERNAL_DIRNAME
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "INTERNAL_DIR", internal)
    monkeypatch.setattr(config, "LIBRARY_TOML", internal / "library.toml")
    monkeypatch.setattr(config, "GOALS_TOML", internal / "goals.toml")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.ensure_data_root(root)
    return root


# ── Simbad parsing helpers ────────────────────────────────────────────────────

def test_simbad_type_mapping():
    assert catalog._simbad_type("G") == "galaxy"
    assert catalog._simbad_type("GlC") == "globular"
    assert catalog._simbad_type("OpC") == "open_cluster"
    assert catalog._simbad_type("PN") == "planetary"
    assert catalog._simbad_type("SNR") == "emission_snr"
    assert catalog._simbad_type("DNe") == "dark_nebula"
    assert catalog._simbad_type("HII") == "emission"
    assert catalog._simbad_type("???") == "unknown"


def test_simbad_row_to_entry():
    row = {"ra": 314.0, "dec": 31.7, "galdim_majaxis": 60.0,
           "galdim_minaxis": 8.0, "V": 7.04, "otype": "SNR"}
    e = catalog._simbad_row_to_entry(row)
    assert e["ra_deg"] == 314.0 and e["dec_deg"] == 31.7
    assert e["size"] == "60'×8'" and e["magnitude"] == 7.0
    assert e["type"] == "emission_snr"


# ── resolve_new_object ────────────────────────────────────────────────────────

def test_resolve_reference_hit(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    r = catalog.resolve_new_object("M81")
    assert r["slug"] == "m81"
    assert r["entry"]["name"] == "Bode's Galaxy" and r["entry"]["type"] == "galaxy"
    assert r["entry"]["season"] and set(r["source"].values()) == {"reference"}


def test_resolve_by_catalog_designation(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    r = catalog.resolve_new_object("C20")               # Caldwell → reference slug
    assert r["slug"] == "ngc-7000"
    assert r["entry"]["name"] == "North America Nebula"


def test_resolve_unknown_offline_is_minimal(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    r = catalog.resolve_new_object("Barnard 33")
    assert r["slug"] == "barnard-33" and r["entry"]["type"] == "unknown"
    assert "magnitude" not in r["entry"]


def test_resolve_online_folds_in(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    monkeypatch.setattr(catalog, "resolve_object_online",
                        lambda names: {n: {"type": "dark_nebula", "magnitude": 7.3,
                                           "ra_deg": 85.24, "dec_deg": -2.46}
                                       for n in names})
    r = catalog.resolve_new_object("Barnard 33", online=True)
    assert r["entry"]["type"] == "dark_nebula" and r["entry"]["magnitude"] == 7.3
    assert r["entry"]["season"]                          # derived from online coords
    assert r["source"]["magnitude"] == "online"


# ── add_library_entry ─────────────────────────────────────────────────────────

def test_add_library_entry_appends_and_stubs(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    r = catalog.resolve_new_object("Barnard 33")
    catalog.add_library_entry(r["slug"], r["entry"])
    assert "barnard-33" in catalog.load_library()
    assert (config.OBJECTS_DIR / "Barnard 33" / "journal.md").exists()
    with pytest.raises(ValueError):
        catalog.add_library_entry(r["slug"], r["entry"])     # refuses duplicate


# ── online enrichment of existing entries ─────────────────────────────────────

_VEIL_STUB = ('\n[catalog.ngc-6992]\nid = "NGC 6992"\nname = ""\ntype = "unknown"\n'
              'ra_deg = 314.0792\ndec_deg = 31.7433\n')


def test_fill_missing_online_fills_reference_gaps(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    with config.LIBRARY_TOML.open("a") as f:
        f.write(_VEIL_STUB)
    monkeypatch.setattr(catalog, "resolve_object_online",
                        lambda names: {n: {"magnitude": 7.0, "size": "60'×8'"}
                                       for n in names})
    filled = catalog.fill_missing_metadata("ngc-6992", online=True)
    assert filled["name"] == "East Veil Nebula"          # from reference
    assert filled["magnitude"] == 7.0 and filled["size"] == "60'×8'"   # from online


def test_fill_missing_offline_unchanged(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    with config.LIBRARY_TOML.open("a") as f:
        f.write(_VEIL_STUB)
    filled = catalog.fill_missing_metadata("ngc-6992")   # online=False default
    assert "magnitude" not in filled and filled["name"] == "East Veil Nebula"


def test_enrich_online_bulk(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    with config.LIBRARY_TOML.open("a") as f:
        f.write(_VEIL_STUB)
    monkeypatch.setattr(catalog, "resolve_object_online",
                        lambda names: {n: {"magnitude": 7.0} for n in names})
    out = catalog.enrich_online(["ngc-6992"])
    assert out["ngc-6992"]["magnitude"] == 7.0


def test_online_graceful_without_astroquery(monkeypatch):
    # Simulate astroquery not installed → OnlineLookupError, not a crash.
    monkeypatch.setitem(sys.modules, "astroquery.simbad", None)
    with pytest.raises(catalog.OnlineLookupError):
        catalog.resolve_object_online(["NGC 6992"])
