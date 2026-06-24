"""Tests for catalog ordering (mirrors the site's _catalog_sort_key)."""
import shutil

from m110 import catalog, config
from m110.catalog import catalog_sort_key, season_sort_key


def test_messier_numeric_not_lexical():
    ids = ["M10", "M1", "M100", "M2", "M9"]
    assert sorted(ids, key=catalog_sort_key) == ["M1", "M2", "M9", "M10", "M100"]


def test_messier_then_ngc_then_other():
    ids = ["NGC 3628", "M81", "Markarian's Chain"]
    assert sorted(ids, key=catalog_sort_key) == ["M81", "NGC 3628", "Markarian's Chain"]


def test_ngc_numeric():
    assert sorted(["NGC 3628", "NGC 891", "NGC 2903"], key=catalog_sort_key) == [
        "NGC 891", "NGC 2903", "NGC 3628"]


def test_markarians_not_parsed_as_messier():
    # starts with M but must NOT sort as a Messier number
    assert catalog_sort_key("Markarian's Chain")[0] == 2
    assert catalog_sort_key("M81")[0] == 0


def test_bundled_reference_and_catalog():
    ref = catalog.load_reference()
    assert len(ref) >= 110                               # all reference objects
    assert ref["m31"]["id"] == "M31" and ref["m31"]["ra_deg"]   # coords folded in
    mes = catalog.load_bundled_catalog("messier")
    assert mes["name"] == "Messier" and len(mes["members"]) == 108
    assert "m31" in mes["members"]
    assert catalog.load_bundled_catalog("nope") == {}


def test_add_captured_objects(tmp_path, monkeypatch):
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)                            # seed from bundled reference
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    monkeypatch.setattr(catalog, "_simbad_coords", lambda name: (314.08, 31.74))

    (config.IMAGES_DIR / "M101" / "lights").mkdir(parents=True)       # cataloged
    (config.IMAGES_DIR / "NGC 6992" / "lights").mkdir(parents=True)   # NEW
    (config.IMAGES_DIR / "NoCaptures").mkdir()                        # ignored

    assert catalog.add_captured_objects() == ["ngc-6992"]
    c = catalog.load_library()
    assert c["ngc-6992"]["id"] == "NGC 6992" and c["ngc-6992"]["type"] == "unknown"
    assert "m101" in c                                   # existing entries untouched
    # Simbad coords are written + merged into load_coords (→ pointing support)
    assert catalog.load_coords()["ngc-6992"] == (314.08, 31.74)
    # idempotent — second pass adds nothing
    assert catalog.add_captured_objects() == []


def test_add_captured_objects_minimal_when_offline(tmp_path, monkeypatch):
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    monkeypatch.setattr(catalog, "_simbad_coords", lambda name: None)  # offline
    (config.IMAGES_DIR / "NGC 7000" / "seestar-stacks").mkdir(parents=True)
    assert catalog.add_captured_objects() == ["ngc-7000"]
    assert "ngc-7000" not in catalog.load_coords()       # no coords, still added
    assert catalog.load_library()["ngc-7000"]["id"] == "NGC 7000"


def test_season_sort_by_first_month_year_round_last():
    assert season_sort_key("Jan–Mar")[0] == 1
    assert season_sort_key("Mar–May")[0] == 3
    assert season_sort_key("Dec–Feb")[0] == 12      # by first month, not wrap
    assert season_sort_key("Year-round")[0] == 99    # bottom
    assert season_sort_key("")[0] == 99
    seasons = ["Year-round", "Mar–May", "Jan–Mar", "Dec–Feb", "Jun–Aug"]
    assert sorted(seasons, key=season_sort_key) == [
        "Jan–Mar", "Mar–May", "Jun–Aug", "Dec–Feb", "Year-round"]
