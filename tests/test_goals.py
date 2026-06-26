"""Tests for goals (active catalogs + custom lists) + per-goal progress + the
5d Library-=-collection reframe (no bulk seed; goal-deselect / manual removal)."""
import pytest

from m110 import catalog, config, goals, build_derived, objects


# ── bundled data (Caldwell) ──────────────────────────────────────────────────

def test_caldwell_bundle_is_complete_and_disjoint_from_messier():
    cw = catalog.load_bundled_catalog("caldwell")
    mes = catalog.load_bundled_catalog("messier")
    ref = catalog.load_reference()
    assert cw["name"] == "Caldwell" and len(cw["members"]) == 109
    assert all(s in ref for s in cw["members"])               # all in reference
    assert all(ref[s].get("ra_deg") is not None for s in cw["members"])  # coords
    assert not (set(cw["members"]) & set(mes["members"]))      # no Messier overlap


def test_list_and_membership():
    ids = {c["id"] for c in catalog.list_bundled_catalogs()}
    assert {"messier", "caldwell"} <= ids
    assert ("Messier", "M31") in catalog.catalogs_for_slug("m31")
    assert ("Caldwell", "C20") in catalog.catalogs_for_slug("ngc-7000")
    assert catalog.catalogs_for_slug("not-a-real-slug") == []


def test_additional_bundled_catalogs():
    cats = {c["id"]: c for c in catalog.list_bundled_catalogs()}
    sizes = {"rasc-finest": 111, "sharpless-best": 30, "bennett": 152, "lacaille": 29}
    for cid, n in sizes.items():
        assert cid in cats and len(cats[cid]["members"]) == n
    ref = catalog.load_reference()
    # every member resolves to a reference object with coords + a type
    for cid in sizes:
        for slug in cats[cid]["members"]:
            assert slug in ref, f"{cid}:{slug} missing from reference"
            assert ref[slug].get("type"), f"{cid}:{slug} no type"
            assert ref[slug].get("ra_deg") is not None, f"{cid}:{slug} no coords"
    # authoritative ASSA Bennett numbering (Ben 87 = NGC 6284, not Cr 259)
    assert cats["bennett"]["members"]["ngc-6284"] == "Ben 87"
    assert "ngc-1291" in cats["bennett"]["members"]      # not the 1269 typo
    # an object in many catalogs renders them in priority order (47 Tuc = NGC 104)
    ids = catalog.object_identifiers("ngc-104", ref.get("ngc-104"))
    assert ids[0] == "C106" and "Ben 2" in ids and "Lac I.1" in ids


# ── add_goal_members_to_library (still used by the add/captured paths) ────────

def test_add_goal_members_additive_idempotent(tmp_path, monkeypatch):
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)                                 # empty (5d)
    before = set(catalog.load_library())
    assert "ngc-7000" not in before

    added = catalog.add_goal_members_to_library("caldwell")
    assert len(added) == 109 and "ngc-7000" in added
    after = catalog.load_library()
    assert "ngc-7000" in after and after["ngc-7000"]["id"] == "NGC 7000"
    assert before <= set(after)                               # additive
    assert catalog.add_goal_members_to_library("caldwell") == []  # idempotent


# ── goals module: active set, no bulk seed ────────────────────────────────────

def test_seed_library_is_empty(tmp_path, monkeypatch):
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)
    assert catalog.load_library() == {}                       # 5d: collection, not catalog


def test_active_goals_default_and_set_no_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GOALS_TOML", tmp_path / "goals.toml")
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)
    assert goals.active_goal_ids() == ["messier"]            # default (no file)

    result = goals.set_active_goals(["messier", "caldwell"])
    assert result == {"removed": []}                          # 5d: no longer seeds
    assert catalog.load_library() == {}                       # Library stays empty
    assert (tmp_path / "goals.toml").is_file()                # persisted per-store
    assert set(goals.active_goal_ids()) == {"messier", "caldwell"}


def test_active_goals_are_per_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GOALS_TOML", tmp_path / "a" / "goals.toml")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "a" / "library.toml")
    config._seed_library(config.LIBRARY_TOML)
    goals.set_active_goals(["messier", "caldwell"])
    monkeypatch.setattr(config, "GOALS_TOML", tmp_path / "b" / "goals.toml")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "b" / "library.toml")
    assert goals.active_goal_ids() == ["messier"]            # not leaked from store a


# ── custom goals (CRUD + round-trip) ──────────────────────────────────────────

def test_custom_goal_crud_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GOALS_TOML", tmp_path / "goals.toml")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "library.toml")
    config._seed_library(config.LIBRARY_TOML)

    gid = goals.create_custom_goal("Veil Project", ["ngc-6960", "ngc-6992"])
    assert gid == "veil-project"
    assert gid in goals.active_goal_ids()                     # activated by default
    assert goals.goal_members(gid) == {"ngc-6960": "ngc-6960", "ngc-6992": "ngc-6992"}
    assert goals.goal_name(gid) == "Veil Project"
    # appears in list_goals as a custom entry
    listed = {g["id"]: g for g in goals.list_goals()}
    assert listed[gid]["kind"] == "custom" and listed[gid]["active"]
    assert listed["messier"]["kind"] == "bundled"

    # edit
    goals.edit_custom_goal(gid, name="Veil", members=["ngc-6960"])
    assert goals.goal_name(gid) == "Veil"
    assert set(goals.goal_members(gid)) == {"ngc-6960"}

    # auto-uniquified id on a slug clash (gid is still "veil-project")
    gid2 = goals.create_custom_goal("Veil Project", ["m1"])
    assert gid2 == "veil-project-2"

    # delete
    goals.delete_custom_goal(gid)
    assert gid not in {g["id"] for g in goals.list_goals()}
    assert gid not in goals.active_goal_ids()


# ── goal de-select removal guard ──────────────────────────────────────────────

def _setup_store(tmp_path, monkeypatch):
    root = tmp_path / "M110"
    internal = root / config.INTERNAL_DIRNAME
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "LIBRARY_TOML", internal / "library.toml")
    monkeypatch.setattr(config, "GOALS_TOML", internal / "goals.toml")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "DERIVED_DIR", internal / "derived")
    config.ensure_data_root(root)
    return root, internal


def test_goal_deselect_removal_guard(tmp_path, monkeypatch):
    root, internal = _setup_store(tmp_path, monkeypatch)
    # Populate the Library with four Caldwell objects (as if added by a goal).
    catalog.add_goal_members_to_library("caldwell")
    lib = catalog.load_library()
    plain, captured, noted, shared = "ngc-7000", "ngc-6992", "ngc-6960", "ngc-7023"
    assert all(s in lib for s in (plain, captured, noted, shared))

    # captured → present in derived totals
    (config.DERIVED_DIR).mkdir(parents=True, exist_ok=True)
    import json
    (config.DERIVED_DIR / "totals.json").write_text(
        json.dumps({"by_slug": {captured: {"status": "initial"}}}))
    # noted → real prose in the journal body
    objects.write_journal(noted, '---\nname: "x"\n---\n\nReal observing notes here.\n')
    # shared → also a member of an active custom goal
    goals.set_active_goals(["caldwell"])
    goals.create_custom_goal("Keep", [shared])

    removed = catalog.remove_goal_members_from_library("caldwell")
    after = catalog.load_library()
    assert plain in removed and plain not in after            # uncaptured/un-noted → gone
    assert captured in after and captured not in removed      # captured → kept
    assert noted in after and noted not in removed            # annotated → kept
    assert shared in after and shared not in removed          # in another goal → kept


def test_remove_library_entry(tmp_path, monkeypatch):
    root, internal = _setup_store(tmp_path, monkeypatch)
    catalog.add_goal_members_to_library("messier")
    assert "m31" in catalog.load_library()
    assert catalog.remove_library_entry("m31") is True
    assert "m31" not in catalog.load_library()
    assert catalog.remove_library_entry("m31") is False       # already gone
    # non-destructive: journal folder untouched (if any) — nothing to assert beyond
    # that the entry is gone and the call is idempotent.


# ── build_goals progress + in_progress ────────────────────────────────────────

def test_build_goals_progress_and_in_progress():
    totals = {"by_slug": {
        "m31": {"status": "deep_stack"}, "m51": {"status": "initial"}}}
    out = {g["id"]: g for g in build_derived.build_goals(totals, ["messier"])}
    m = out["messier"]
    assert m["name"] == "Messier" and m["total"] == 110
    assert m["captured"] == 2 and m["deep"] == 1
    assert m["percent"] == round(100 * 2 / 110, 1)
    # in_progress = captured but below the deep-stack target
    ip = {x["slug"] for x in m["in_progress"]}
    assert ip == {"m51"}


def test_build_goals_custom(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GOALS_TOML", tmp_path / "goals.toml")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "library.toml")
    config._seed_library(config.LIBRARY_TOML)
    gid = goals.create_custom_goal("My List", ["m31", "m51"])
    totals = {"by_slug": {"m31": {"status": "deep_stack"}}}
    out = {g["id"]: g for g in build_derived.build_goals(totals, [gid])}
    g = out[gid]
    assert g["name"] == "My List" and g["total"] == 2 and g["captured"] == 1
