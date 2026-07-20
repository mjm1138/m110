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


def test_astroquery_missing_message_is_build_aware(monkeypatch):
    """A frozen app has no pip, so the 'astroquery missing' message must NOT tell the
    user to `pip install` there (issue #64) — packaged builds bundle it, so its absence
    is a report-worthy build defect. From source, the extra is the real fix."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    frozen_msg = catalog._astroquery_missing_message()
    assert "pip install" not in frozen_msg
    assert "report" in frozen_msg.lower()

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    source_msg = catalog._astroquery_missing_message()
    assert "pip install 'm110[online]'" in source_msg


def test_online_error_message_follows_frozen_state(monkeypatch):
    """The raised OnlineLookupError carries the build-aware message end-to-end."""
    monkeypatch.setitem(sys.modules, "astroquery.simbad", None)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(catalog.OnlineLookupError) as ei:
        catalog.resolve_object_online(["NGC 6992"])
    assert "pip install" not in str(ei.value)


def test_online_import_failure_is_logged(monkeypatch, caplog):
    """The underlying astroquery import error is logged (with traceback) before the
    generic OnlineLookupError — so a packaged-build failure (e.g. #74's KeyError from
    a missing astropy metadata) is diagnosable from the log, not just the user-facing
    'not available' message. The m110 logger may not propagate once logsetup has run,
    so attach caplog's handler directly."""
    import logging
    monkeypatch.setitem(sys.modules, "astroquery.simbad", None)   # force import failure
    log = logging.getLogger("m110")
    log.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="m110")
    try:
        with pytest.raises(catalog.OnlineLookupError):
            catalog.resolve_object_online(["NGC 6992"])
    finally:
        log.removeHandler(caplog.handler)
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "astroquery" in msg and "could not be imported" in msg


class _FakeTable:
    """Minimal astropy-Table stand-in: len() + row indexing."""
    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    def __getitem__(self, i):
        return self._rows[i]


def _install_fake_simbad(monkeypatch, simbad_cls):
    import types
    mod = types.ModuleType("astroquery.simbad")
    mod.Simbad = simbad_cls
    monkeypatch.setitem(sys.modules, "astroquery.simbad", mod)


def test_resolve_online_queries_per_name_not_batch(monkeypatch):
    """resolve_object_online must query one name at a time (query_object), NOT the batch
    query_objects: the batch injects Simbad's int64 `object_number_id`, which overflows
    astropy's VOTable parser on Windows (32-bit C long) — the C34/NGC 6960 report. The
    result is keyed by the input name."""
    seen = {"batch": 0, "names": []}

    class FakeSimbad:
        def add_votable_fields(self, *a):
            pass

        def query_objects(self, names):
            seen["batch"] += 1
            raise AssertionError("must not use the batch query_objects (Windows overflow)")

        def query_object(self, name):
            seen["names"].append(name)
            return _FakeTable([{"ra": 250.0, "dec": 36.5, "galdim_majaxis": 70.0,
                                "galdim_minaxis": 6.0, "V": 7.0, "otype": "SNR"}])

    _install_fake_simbad(monkeypatch, FakeSimbad)
    out = catalog.resolve_object_online(["NGC 6960"])
    assert seen["batch"] == 0                       # never the overflowing batch path
    assert seen["names"] == ["NGC 6960"]
    assert "NGC 6960" in out                        # keyed by the input name
    assert out["NGC 6960"]["type"] == "emission_snr"


def test_resolve_online_partial_and_all_fail(monkeypatch):
    """A per-name error is tolerated when others resolve (partial result); if EVERY name
    errors, that surfaces as OnlineLookupError (Simbad/network down)."""
    class PartialSimbad:
        def add_votable_fields(self, *a):
            pass

        def query_object(self, name):
            if name == "bad":
                raise RuntimeError("Simbad hiccup")
            return _FakeTable([{"ra": 10.0, "dec": 41.0, "otype": "G"}])

    _install_fake_simbad(monkeypatch, PartialSimbad)
    out = catalog.resolve_object_online(["M31", "bad"])
    assert set(out) == {"M31"}                       # partial: the good one resolves

    class DeadSimbad:
        def add_votable_fields(self, *a):
            pass

        def query_object(self, name):
            raise RuntimeError("Simbad down")

    _install_fake_simbad(monkeypatch, DeadSimbad)
    with pytest.raises(catalog.OnlineLookupError):
        catalog.resolve_object_online(["M31"])


def test_resolve_online_no_match_is_quiet(monkeypatch):
    """A name Simbad doesn't resolve (empty table) is skipped, not an error → {}."""
    class EmptySimbad:
        def add_votable_fields(self, *a):
            pass

        def query_object(self, name):
            return _FakeTable([])

    _install_fake_simbad(monkeypatch, EmptySimbad)
    assert catalog.resolve_object_online(["Nonexistent"]) == {}


def test_filter_is_not_an_enrichable_gap():
    """`filter` is a per-capture setting no catalog/Simbad provides, so an object missing
    only `filter` must NOT count as having gaps — otherwise it offers "Enrich online" and
    then finds nothing (the NGC 6960 confusion). A real missing field still counts."""
    complete = {"id": "M13", "name": "Hercules", "type": "globular", "magnitude": 5.8,
                "size": "20", "season": "summer", "ra_deg": 250.0, "dec_deg": 36.0}
    assert "filter" not in catalog._FILLABLE
    assert catalog._has_gaps(complete) is False                    # no `filter` → still no gap
    assert catalog._has_gaps({**complete, "filter": None}) is False
    missing_mag = {k: v for k, v in complete.items() if k != "magnitude"}
    assert catalog._has_gaps(missing_mag) is True                  # a real fillable gap still counts
