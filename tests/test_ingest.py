"""Tests for the staging ingest planner + apply (temp fixtures, never live data).

dest_rel is relative to the data root, so destinations read as
``Images/<target>/lights``, ``Images/<target>/seestar-stacks``, ``Media/<cat>``.
"""
import numpy as np
import pytest
from astropy.io import fits

from m110 import catalog, config, ingest


def _fits_at(path, ra, dec):
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="float32"))
    h.header["RA"] = ra
    h.header["DEC"] = dec
    h.writeto(path)


def _make_staging(tmp_path, monkeypatch):
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "MEDIA_DIR", root / "Media")
    monkeypatch.setattr(config, "STAGING_DIR", root / "Inbox")
    # Deterministic canonicalization/pointing: real seed catalog, isolated aliases.
    monkeypatch.setattr(config, "INTERNAL_DIR", root / ".m110_internal_data")
    monkeypatch.setattr(config, "CATALOG_TOML", config.SEED_DIR / "catalog.toml")
    staging = root / "Inbox"
    staging.mkdir(parents=True)
    return root, staging


def test_ops_carry_source_size(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M13_sub"
    sub.mkdir()
    (sub / "Light_a.fit").write_text("x" * 123)
    ops = ingest.scan_staging_plan()
    assert ops and ops[0].size_bytes == 123


def test_group_ops_aggregates_by_source_folder(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    for obj, n in [("M101", 3), ("M51", 2)]:
        d = staging / f"{obj}_sub"
        d.mkdir()
        for i in range(n):
            (d / f"Light_{obj}_{i}.fit").write_text("x" * 100)
    stk = staging / "M101"
    stk.mkdir()
    (stk / "Stacked_10_M101.fit").write_text("s" * 50)
    med = staging / "Lunar_photo"
    med.mkdir()
    (med / "moon.jpg").write_text("j" * 10)

    groups = ingest.group_ops(ingest.scan_staging_plan())
    by_key = {(g.object, g.kind): g for g in groups}
    assert (by_key[("M101", "light")].frames, by_key[("M101", "light")].size_bytes) == (3, 300)
    assert by_key[("M101", "light")].dest_dir == "Images/M101/lights"
    assert by_key[("M101", "light")].new_object is True
    assert by_key[("M101", "stack")].frames == 1            # lights vs stack split
    assert by_key[("Lunar_photo", "media")].kind == "media"
    assert groups[-1].kind == "media"                       # media sorts last


def test_apply_selected_subset_only(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    for obj in ("M101", "M51"):
        d = staging / f"{obj}_sub"
        d.mkdir()
        (d / f"Light_{obj}.fit").write_text("x")
    groups = ingest.group_ops(ingest.scan_staging_plan())
    keep = [g for g in groups if g.object == "M101"]
    ops = [o for g in keep for o in g.ops]

    ingest.apply_ops(ops)
    assert config.lights_dir("M101").is_dir()              # selected → imported
    assert not config.target_dir("M51").exists()          # unselected → untouched
    assert (staging / "M51_sub" / "Light_M51.fit").exists()


# ── #12: canonicalization, aliases, pointing ─────────────────────────────────

def test_canonical_target_case_alias_catalog(tmp_path, monkeypatch):
    root, _staging = _make_staging(tmp_path, monkeypatch)
    assert ingest.canonical_target("m82") == "M82"        # catalog id casing
    assert ingest.canonical_target("M 13") == "M13"       # device-quirk normalize
    (config.IMAGES_DIR / "M82").mkdir(parents=True)        # existing-folder casing
    assert ingest.canonical_target("M82") == "M82"
    ingest.add_alias("Bode", "M81")                        # alias wins
    assert ingest.canonical_target("Bode") == "M81"
    assert ingest.canonical_target("Weird Thing") == "Weird Thing"   # fallback


def test_alias_roundtrip(tmp_path, monkeypatch):
    _make_staging(tmp_path, monkeypatch)
    assert ingest.load_aliases() == {}
    ingest.add_alias("foo", "M99")
    assert ingest.load_aliases()["foo"] == "M99"


def test_separation_and_frame_radec(tmp_path):
    assert ingest._separation_deg(10, 20, 10, 20) == 0
    assert 0.5 < ingest._separation_deg(148.888, 69.065, 148.969, 69.680) < 0.75
    p = tmp_path / "f.fit"
    _fits_at(p, 148.9, 69.6)
    assert ingest.frame_radec(str(p)) == (148.9, 69.6)
    assert ingest.frame_radec(str(tmp_path / "nope.fit")) is None


def test_canonical_folds_case_variant_at_scan(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "m82_sub"          # lowercase variant from SSC
    sub.mkdir()
    (sub / "Light_m82_a.fit").write_text("x")
    op = ingest.scan_staging_plan()[0]
    assert op.dest_rel.startswith("Images/M82/lights/")   # routed to canonical M82


def test_annotate_pointing_flags_and_suggests(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    ra82, dec82 = catalog.load_coords()["m82"]
    sub = staging / "M81_sub"          # named M81 but frames point at M82
    sub.mkdir()
    _fits_at(sub / "Light_M81_a.fit", ra82, dec82)
    groups = ingest.group_ops(ingest.scan_staging_plan())
    ingest.annotate_pointing(groups)
    g = groups[0]
    assert g.object == "M81" and g.suggested == "m82" and "M82" in g.pointing


def test_annotate_pointing_clean_when_matches(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    ra81, dec81 = catalog.load_coords()["m81"]
    sub = staging / "M81_sub"
    sub.mkdir()
    _fits_at(sub / "Light_M81_a.fit", ra81, dec81)
    groups = ingest.group_ops(ingest.scan_staging_plan())
    ingest.annotate_pointing(groups)
    assert groups[0].pointing is None and groups[0].suggested is None


def test_annotate_pointing_degrades_without_radec(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M81_sub"
    sub.mkdir()
    (sub / "Light_M81_a.fit").write_text("x")   # not a real FITS → no RA/DEC
    groups = ingest.group_ops(ingest.scan_staging_plan())
    ingest.annotate_pointing(groups)
    assert groups[0].pointing is None            # unverified, not a false alarm


def test_retarget_rewrites_dests(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M81_sub"
    sub.mkdir()
    (sub / "Light_a.fit").write_text("x")
    g = ingest.group_ops(ingest.scan_staging_plan())[0]
    ng = ingest.retarget(g, "M82")
    assert ng.object == "M82" and ng.dest_dir == "Images/M82/lights"
    assert all("/M82/lights/" in o.dest_rel for o in ng.ops)


def test_plan_classifies_subs_stacks_media(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)

    # raw subframes for a NEW object "M 13" → Images/M13/lights/
    sub = staging / "M 13_sub"
    sub.mkdir()
    (sub / "Light_M13_20s_IRCUT_20260101-000000.fit").touch()
    (sub / "Light_M13_20s_IRCUT_20260101-000020.fit").touch()
    # in-app stacks dir
    stk = staging / "M13"
    stk.mkdir()
    (stk / "Stacked_10_M13.fit").touch()
    (stk / "not_a_stack.fit").touch()          # not a stack prefix → ignored
    # media dir
    med = staging / "Lunar_photo"
    med.mkdir()
    (med / "2026-01-01-000000-Lunar.jpg").touch()

    ops = ingest.scan_staging_plan()
    by_kind = {}
    for op in ops:
        by_kind.setdefault(op.kind, []).append(op)

    assert len(by_kind["light"]) == 2
    assert all(op.new_object for op in by_kind["light"])  # M13 target doesn't exist
    assert "Images/M13/lights/" in by_kind["light"][0].dest_rel
    assert len(by_kind["stack"]) == 1                     # only the Stacked_ one
    assert by_kind["stack"][0].dest_rel.startswith("Images/M13/seestar-stacks/")
    assert len(by_kind["media"]) == 1
    assert by_kind["media"][0].dest_rel.startswith("Media/Lunar_photo/")


def test_existing_files_excluded(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M5_sub"
    sub.mkdir()
    (sub / "Light_a.fit").touch()
    (sub / "Light_b.fit").touch()
    # one already present in the destination → only the other is "new"
    dest = config.lights_dir("M5")
    dest.mkdir(parents=True)
    (dest / "Light_a.fit").touch()

    ops = ingest.scan_staging_plan()
    names = sorted(op.src.rsplit("/", 1)[-1] for op in ops)
    assert names == ["Light_b.fit"]
    assert ops[0].new_object is False  # Images/M5 already exists


def test_apply_moves_and_creates_dirs(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M81 M82_sub"
    sub.mkdir()
    (sub / "Light_x.fit").write_text("data")

    ops = ingest.scan_staging_plan()
    result = ingest.apply_ops(ops)
    assert result == {"moved": 1, "skipped": 0, "cancelled": False}

    moved_to = config.lights_dir("M81 M82") / "Light_x.fit"
    assert moved_to.is_file()
    assert moved_to.read_text() == "data"
    assert not (sub / "Light_x.fit").exists()   # moved, not copied
    # re-scan now shows nothing new
    assert ingest.scan_staging_plan() == []


def test_scan_cancellation_raises(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M5_sub"
    sub.mkdir()
    (sub / "Light_a.fit").touch()
    import pytest
    with pytest.raises(ingest.IngestCancelled):
        ingest.scan_staging_plan(should_cancel=lambda: True)


def test_apply_cancellation_stops_cleanly(tmp_path, monkeypatch):
    root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M5_sub"
    sub.mkdir()
    (sub / "a.fit").write_text("1")
    (sub / "b.fit").write_text("2")
    ops = ingest.scan_staging_plan()
    # cancel before any op runs
    result = ingest.apply_ops(ops, should_cancel=lambda: True)
    assert result["cancelled"] is True
    assert result["moved"] == 0


def test_no_staging_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STAGING_DIR", tmp_path / "Inbox")  # not created
    assert ingest.staging_available() is False
    assert ingest.scan_staging_plan() == []


def test_seestar_plan_uses_copy_and_leaves_device(tmp_path, monkeypatch):
    root, _ = _make_staging(tmp_path, monkeypatch)
    # fake mounted device MyWorks with the staging layout
    myworks = tmp_path / "Volumes" / "EMMC Images" / "MyWorks"
    sub = myworks / "M 13_sub"
    sub.mkdir(parents=True)
    (sub / "Light_M13_a.fit").write_text("data")
    monkeypatch.setattr(config, "find_seestar_myworks", lambda: myworks)

    ops = ingest.scan_seestar_plan()
    assert len(ops) == 1
    assert ops[0].action == "copy"
    assert "Images/M13/lights/" in ops[0].dest_rel

    result = ingest.apply_ops(ops)
    assert result == {"moved": 1, "skipped": 0, "cancelled": False}
    # copied into collection AND still present on the "device"
    assert (config.lights_dir("M13") / "Light_M13_a.fit").is_file()
    assert (sub / "Light_M13_a.fit").is_file()


def test_seestar_copies_stack_previews(tmp_path, monkeypatch):
    """Stack folders' preview .jpg/.png are copied too (so the gallery has
    ready-made images); the device's *_thn.* sidecars are skipped."""
    root, _ = _make_staging(tmp_path, monkeypatch)
    myworks = tmp_path / "Volumes" / "EMMC Images" / "MyWorks"
    stk = myworks / "M13"
    stk.mkdir(parents=True)
    (stk / "Stacked_10_M13.fit").write_text("f")
    (stk / "M13.jpg").write_text("j")          # device preview render
    (stk / "M13_thn.jpg").write_text("t")      # device thumbnail sidecar (skip)
    monkeypatch.setattr(config, "find_seestar_myworks", lambda: myworks)

    names = sorted(op.src.rsplit("/", 1)[-1] for op in ingest.scan_seestar_plan())
    assert "Stacked_10_M13.fit" in names
    assert "M13.jpg" in names
    assert "M13_thn.jpg" not in names
