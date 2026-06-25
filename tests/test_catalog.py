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
    # starts with M but must NOT sort as a Messier number ("other" bucket)
    assert catalog_sort_key("Markarian's Chain")[0] == 4
    assert catalog_sort_key("M81")[0] == 0


def test_catalog_sort_key_ranks_caldwell_and_ic():
    assert catalog_sort_key("M31")[0] == 0
    assert catalog_sort_key("C20")[0] == 1
    assert catalog_sort_key("NGC 7000")[0] == 2
    assert catalog_sort_key("IC 342")[0] == 3
    assert catalog_sort_key("Markarian's Chain")[0] == 4
    # numeric within a class
    assert sorted(["C100", "C9", "C20"], key=catalog_sort_key) == ["C9", "C20", "C100"]


def test_object_identifiers_hierarchy_and_context():
    # Messier: id == designation → no dup
    assert catalog.object_identifiers("m31", {"id": "M31"}) == ["M31"]
    # Caldwell object: C# first by hierarchy, intrinsic NGC after
    assert catalog.object_identifiers("ngc-7000", {"id": "NGC 7000"}) == ["C20", "NGC 7000"]
    # primary_catalog override still puts that catalog first (same here)
    assert catalog.object_identifiers(
        "ngc-7000", {"id": "NGC 7000"}, primary_catalog="caldwell")[0] == "C20"
    # not in any bundled catalog → just its id
    assert catalog.object_identifiers("ngc-2903", {"id": "NGC 2903"}) == ["NGC 2903"]
    # label formatting
    assert catalog.object_label(["C20", "NGC 7000"]) == "C20 (NGC 7000)"
    assert catalog.object_label(["M31"]) == "M31"


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
    config._seed_library(lib)                            # 5d: empty Library
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    monkeypatch.setattr(catalog, "_simbad_coords", lambda name: (314.08, 31.74))

    (config.IMAGES_DIR / "M101" / "lights").mkdir(parents=True)       # known (Messier)
    (config.IMAGES_DIR / "NGC 1234" / "lights").mkdir(parents=True)   # NEW, off-catalog
    (config.IMAGES_DIR / "NoCaptures").mkdir()                        # ignored

    # 5d: the Library starts empty, so capturing a known catalog object also
    # promotes it — pulling its full bundled-reference metadata, not "unknown".
    assert sorted(catalog.add_captured_objects()) == ["m101", "ngc-1234"]
    c = catalog.load_library()
    assert c["m101"]["id"] == "M101" and c["m101"]["type"] != "unknown"
    assert "ra_deg" in c["m101"]                         # reference coords, not Simbad
    # an off-catalog target falls back to a minimal entry + Simbad coords
    assert c["ngc-1234"]["type"] == "unknown"
    assert catalog.load_coords()["ngc-1234"] == (314.08, 31.74)
    # idempotent — second pass adds nothing
    assert catalog.add_captured_objects() == []


def test_add_captured_objects_minimal_when_offline(tmp_path, monkeypatch):
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    monkeypatch.setattr(catalog, "_simbad_coords", lambda name: None)  # offline
    # a target not in any bundled catalog/reference (NGC 7000 is now Caldwell C20)
    (config.IMAGES_DIR / "NGC 1234" / "seestar-stacks").mkdir(parents=True)
    assert catalog.add_captured_objects() == ["ngc-1234"]
    assert "ngc-1234" not in catalog.load_coords()       # no coords, still added
    assert catalog.load_library()["ngc-1234"]["id"] == "NGC 1234"


def test_season_sort_by_first_month_year_round_last():
    assert season_sort_key("Jan–Mar")[0] == 1
    assert season_sort_key("Mar–May")[0] == 3
    assert season_sort_key("Dec–Feb")[0] == 12      # by first month, not wrap
    assert season_sort_key("Year-round")[0] == 99    # bottom
    assert season_sort_key("")[0] == 99
    seasons = ["Year-round", "Mar–May", "Jan–Mar", "Dec–Feb", "Jun–Aug"]
    assert sorted(seasons, key=season_sort_key) == [
        "Jan–Mar", "Mar–May", "Jun–Aug", "Dec–Feb", "Year-round"]
