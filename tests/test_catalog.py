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
    assert mes["name"] == "Messier" and len(mes["members"]) == 110   # complete catalogue
    assert {"m40", "m73"} <= set(mes["members"])          # the two non-deep-sky oddities
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


def test_set_publish_flag_roundtrips(tmp_path, monkeypatch):
    from tests._helpers import add_library, seed_root
    root = seed_root(tmp_path, monkeypatch)
    add_library(root, {"m31": {"id": "M31", "name": "Andromeda", "type": "galaxy"}})
    # exclude → publish = false persisted, other keys intact
    assert catalog.set_publish_flag("m31", False) is True
    lib = catalog.load_library()
    assert lib["m31"]["publish"] is False
    assert lib["m31"]["id"] == "M31" and lib["m31"]["name"] == "Andromeda"
    # include → flag removed (back to default-publish), entry still present
    assert catalog.set_publish_flag("m31", True) is True
    lib = catalog.load_library()
    assert "publish" not in lib["m31"]
    assert lib["m31"]["id"] == "M31"
    # unknown slug → no-op False
    assert catalog.set_publish_flag("nope", False) is False


def test_append_library_entries_never_duplicates(tmp_path, monkeypatch):
    """Defense in depth: appending a slug that's already in the file is a no-op,
    so a (e.g. concurrent) double-append can't write invalid duplicate TOML."""
    from tests._helpers import seed_root
    seed_root(tmp_path, monkeypatch)
    e = {"id": "M42_mosaic", "name": "", "type": "unknown"}
    catalog._append_library_entries({"m42-mosaic": e})
    catalog._append_library_entries({"m42-mosaic": e})   # simulated race / re-run
    txt = config.LIBRARY_TOML.read_text()
    assert txt.count("[catalog.m42-mosaic]") == 1
    assert list(catalog.load_library()) == ["m42-mosaic"]


def test_load_library_self_heals_duplicate_blocks(tmp_path, monkeypatch):
    """A duplicate [catalog.<slug>] file (legacy corruption) self-heals on read
    instead of raising — keeps the first block and rewrites the file."""
    from tests._helpers import seed_root
    seed_root(tmp_path, monkeypatch)
    config.LIBRARY_TOML.write_text(
        '[catalog.m27]\nid = "M27"\ntype = "planetary"\n\n'
        '[catalog.m27]\nid = "M27"\ntype = "planetary"\n')
    lib = catalog.load_library()                     # must not raise
    assert list(lib) == ["m27"]
    assert config.LIBRARY_TOML.read_text().count("[catalog.m27]") == 1


def test_load_library_still_raises_on_real_toml_error(tmp_path, monkeypatch):
    from tests._helpers import seed_root
    seed_root(tmp_path, monkeypatch)
    config.LIBRARY_TOML.write_text('[catalog.m1]\nmagnitude = True\n')  # invalid bool
    import pytest
    with pytest.raises(catalog.LibraryParseError):
        catalog.load_library()


# ── #40c: a capture target is not a catalog object ───────────────────────────

def test_combined_capture_promotes_members_not_a_pseudo_object(tmp_path, monkeypatch):
    """A multi-object capture folder ("M81 M82") must promote **both** catalog
    objects and never itself become an object. Promoting the target created a
    synthetic `m81-m82` (type "unknown") that then shadowed the folder→slug split,
    so the pair's integration never credited M81/M82 (#40c)."""
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)                            # empty Library
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    monkeypatch.setattr(catalog, "_simbad_coords", lambda name: None)

    (config.IMAGES_DIR / "M81 M82" / "lights").mkdir(parents=True)   # combined target
    (config.IMAGES_DIR / "M82" / "lights").mkdir(parents=True)       # solo target too

    added = sorted(catalog.add_captured_objects())
    assert added == ["m81", "m82"]                       # both members promoted…
    c = catalog.load_library()
    assert "m81-m82" not in c                            # …and no pseudo-object
    assert c["m81"]["type"] == "galaxy" and c["m82"]["type"] == "galaxy"


def test_combined_folder_splits_into_member_slugs(tmp_path, monkeypatch):
    """folder_to_slugs resolves a combined folder against Library ∪ reference, so a
    combined capture credits both objects even before they're in the Library."""
    from m110 import scan_sessions
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)                            # empty Library
    slugs = scan_sessions.load_catalog_slugs()
    assert scan_sessions.folder_to_slugs("M81 M82", slugs) == ["m81", "m82"]
    assert scan_sessions.folder_to_slugs("M81", slugs) == ["m81"]


def test_combined_split_is_not_shadowed_by_a_pseudo_object():
    """The 2+-member split must win over the whole-slug match, so a combined
    pseudo-object reintroduced into the Library (hand edit, or a partial restore of
    a pre-v4 backup under a v4 stamp, where migrate won't re-run) can't resurrect
    the under-count. Self-healing rather than order-dependent (#40c)."""
    from m110 import scan_sessions
    ref = set(catalog.load_reference())
    poisoned = ref | {"m81-m82", "m108-m97"}
    assert scan_sessions.folder_to_slugs("M81 M82", poisoned) == ["m81", "m82"]
    assert scan_sessions.folder_to_slugs("M108 M97", poisoned) == ["m108", "m97"]
    # a single object still resolves whole (not split)
    assert scan_sessions.folder_to_slugs("NGC 3628", poisoned) == ["ngc-3628"]


def test_decorated_capture_folder_resolves_to_its_object():
    """A folder named for *how* it was shot is still that object's frames.
    "M42_mosaic" is M42; the decoration describes the capture, not the target."""
    from m110 import scan_sessions
    ref = set(catalog.load_reference())
    assert scan_sessions.folder_to_slugs("M42_mosaic", ref) == ["m42"]
    assert scan_sessions.folder_to_slugs("NGC 7000_mosaic", ref) == ["ngc-7000"]
    assert scan_sessions.folder_to_slugs("M31 panel", ref) == ["m31"]


def test_decoration_strip_beats_a_stale_pseudo_object():
    """The self-sustaining case. Once a stray "m42-mosaic" object exists in the
    Library, the whole-folder match would find it and keep finding it — so the
    folder's frames would be attributed to a coordinate-less stub forever, which
    is exactly how they went missing from the sky map. The strip must win."""
    from m110 import scan_sessions
    poisoned = set(catalog.load_reference()) | {"m42-mosaic", "ngc-7000-mosaic"}
    assert scan_sessions.folder_to_slugs("M42_mosaic", poisoned) == ["m42"]
    assert scan_sessions.folder_to_slugs("NGC 7000_mosaic", poisoned) == ["ngc-7000"]


def test_a_catalog_number_resolves_through_membership():
    """The reference is keyed by an object's primary designation, so "C 6" isn't
    a key — catalog membership is what knows C6 names NGC 6543."""
    from m110 import scan_sessions
    ref = set(catalog.load_reference())
    assert scan_sessions.folder_to_slugs("C 6", ref) == ["ngc-6543"]
    assert scan_sessions.folder_to_slugs("C6", ref) == ["ngc-6543"]
    # A designation that *is* a reference key still resolves to itself.
    assert scan_sessions.folder_to_slugs("M31", ref) == ["m31"]


def test_designation_index_covers_the_bundled_catalogs():
    idx = catalog.designation_index()
    assert idx["c6"] == "ngc-6543"
    assert idx["m31"] == "m31"
    assert catalog._normalize_designation("C 6") == "c6"
