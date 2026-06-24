"""Tests for goals (active catalogs) + per-goal progress + bundled Caldwell."""
from m110 import catalog, config, goals, build_derived


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


# ── add_goal_members_to_library ───────────────────────────────────────────────

def test_add_goal_members_additive_idempotent(tmp_path, monkeypatch):
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)                                 # Messier only
    before = set(catalog.load_library())
    assert "ngc-7000" not in before                           # Caldwell not seeded

    added = catalog.add_goal_members_to_library("caldwell")
    assert len(added) == 109 and "ngc-7000" in added
    after = catalog.load_library()
    assert "ngc-7000" in after and after["ngc-7000"]["id"] == "NGC 7000"
    assert before <= set(after)                               # additive (Messier kept)
    assert catalog.add_goal_members_to_library("caldwell") == []  # idempotent


# ── goals module ──────────────────────────────────────────────────────────────

def test_active_goals_default_and_set(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GOALS_TOML", tmp_path / "goals.toml")
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)
    assert goals.active_goal_ids() == ["messier"]            # default (no file)

    added = goals.set_active_goals(["messier", "caldwell"])
    assert len(added) == 109                                  # Caldwell added to Library
    assert (tmp_path / "goals.toml").is_file()                # persisted per-store
    assert set(goals.active_goal_ids()) == {"messier", "caldwell"}


def test_active_goals_are_per_store(tmp_path, monkeypatch):
    # A fresh store defaults to Messier regardless of any other store's goals.
    monkeypatch.setattr(config, "GOALS_TOML", tmp_path / "a" / "goals.toml")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "a" / "library.toml")
    config._seed_library(config.LIBRARY_TOML)
    goals.set_active_goals(["messier", "caldwell"])
    # switch to a different store
    monkeypatch.setattr(config, "GOALS_TOML", tmp_path / "b" / "goals.toml")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "b" / "library.toml")
    assert goals.active_goal_ids() == ["messier"]            # not leaked from store a


# ── build_goals progress ──────────────────────────────────────────────────────

def test_build_goals_progress():
    totals = {"by_slug": {
        "m31": {"status": "deep_stack"}, "m51": {"status": "initial"}}}
    out = {g["id"]: g for g in build_derived.build_goals(totals, ["messier"])}
    m = out["messier"]
    assert m["name"] == "Messier" and m["total"] == 108
    assert m["captured"] == 2 and m["deep"] == 1
    assert m["percent"] == round(100 * 2 / 108, 1)


def test_seed_library_is_messier_only(tmp_path, monkeypatch):
    lib = tmp_path / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)
    libd = catalog.load_library()
    assert len(libd) == 108                                   # Messier, not all 220
    assert "m31" in libd and "ngc-7000" not in libd
