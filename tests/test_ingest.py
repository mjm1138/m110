"""Tests for the staging ingest planner + apply (temp fixtures, never live data).

dest_rel is relative to the data root, so destinations read as
``Images/<target>/lights``, ``Images/<target>/seestar-stacks``, ``Media/<cat>``.
"""
from pathlib import Path

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
    # Deterministic canonicalization/pointing: a Library seeded from the bundled
    # reference, isolated aliases.
    monkeypatch.setattr(config, "INTERNAL_DIR", root / ".m110_internal_data")
    lib = root / ".m110_internal_data" / "library.toml"
    monkeypatch.setattr(config, "LIBRARY_TOML", lib)
    config._seed_library(lib)
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


def test_sub_previews_ignored_by_default(tmp_path, monkeypatch):
    """#25: a `_sub` folder's per-sub .jpg previews are recognized-and-ignored unless
    the preference is on. The _thn thumbnail is always ignored."""
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")   # pref absent → off
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M13_sub"; sub.mkdir()
    (sub / "Light_M13_1.fit").write_text("f")
    (sub / "Light_M13_1.jpg").write_text("j")        # per-sub preview
    (sub / "Light_M13_1_thn.jpg").write_text("t")    # thumbnail
    ops = ingest.scan_staging_plan()
    assert {op.kind for op in ops} == {"light"}      # only the raw sub imported
    assert all(op.src.endswith(".fit") for op in ops)


def test_sub_previews_imported_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    _root, staging = _make_staging(tmp_path, monkeypatch)
    config.save_setting(ingest.IMPORT_SUB_PREVIEWS_KEY, True)
    sub = staging / "M13_sub"; sub.mkdir()
    (sub / "Light_M13_1.fit").write_text("f")
    (sub / "Light_M13_1.jpg").write_text("j")        # imported → previews/
    (sub / "Light_M13_1_thn.jpg").write_text("t")    # thumbnail still ignored
    ops = ingest.scan_staging_plan()
    previews = [op for op in ops if op.kind == "preview"]
    assert len(previews) == 1
    assert previews[0].src.endswith("Light_M13_1.jpg")
    assert "Images/M13/previews" in previews[0].dest_rel
    assert any(op.kind == "light" and op.src.endswith(".fit") for op in ops)   # sub still → lights
    assert not any("_thn." in op.src for op in ops)                            # thumbnail excluded


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


# ── 6a: recursive any-directory scan + content-aware collisions ───────────────

def test_scan_directory_plan_recurses_nested_tree(tmp_path, monkeypatch):
    """Point at an arbitrary tree: Seestar-shaped folders are found at any depth,
    with copy semantics (the source is left untouched)."""
    _root, _staging = _make_staging(tmp_path, monkeypatch)
    src = tmp_path / "external"
    sub = src / "2026-01" / "night1" / "M13_sub"      # nested 3 levels deep
    sub.mkdir(parents=True)
    (sub / "Light_a.fit").write_text("x")
    stk = src / "2026-01" / "M51"                      # a stack dir elsewhere
    stk.mkdir(parents=True)
    (stk / "Stacked_10_M51.fit").write_text("s")
    (stk / "random.jpg").write_text("noise")          # rides along (stack dir)

    ops = ingest.scan_directory_plan(str(src))
    by_kind = {}
    for op in ops:
        by_kind.setdefault(op.kind, []).append(op)
    assert all(op.action == "copy" for op in ops)     # never moves an external src
    assert len(by_kind["light"]) == 1
    assert "Images/M13/lights/" in by_kind["light"][0].dest_rel
    assert any("Images/M51/seestar-stacks/" in o.dest_rel for o in by_kind["stack"])


def test_seestar_plan_recurses_nested_subfolders(tmp_path, monkeypatch):
    """#32 regression: a Seestar MyWorks with an extra nesting level (the device/
    staging plans used to scan only one level deep and silently miss it). Both the
    top-level and the nested target must be found."""
    root, _ = _make_staging(tmp_path, monkeypatch)
    myworks = tmp_path / "Volumes" / "EMMC Images" / "MyWorks"
    top = myworks / "M13_sub"                          # immediate child
    top.mkdir(parents=True)
    (top / "Light_M13_a.fit").write_text("data")
    nested = myworks / "2026-07-Trip" / "M51_sub"      # one level deeper
    nested.mkdir(parents=True)
    (nested / "Light_M51_a.fit").write_text("data")
    monkeypatch.setattr(config, "find_seestar_myworks", lambda: myworks)

    ops = ingest.scan_seestar_plan()
    dests = {o.dest_rel for o in ops}
    assert any("Images/M13/lights/" in d for d in dests)
    assert any("Images/M51/lights/" in d for d in dests)   # the nested one (was missed)


def test_staging_plan_recurses_nested_subfolders(tmp_path, monkeypatch):
    """#32 regression for the Inbox/staging plan — also recursive now."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    nested = staging / "batch-a" / "M13_sub"
    nested.mkdir(parents=True)
    (nested / "Light_M13_a.fit").write_text("data")
    ops = ingest.scan_staging_plan()
    assert any("Images/M13/lights/" in o.dest_rel for o in ops)
    assert all(o.action == "move" for o in ops)            # staging = move semantics


def test_scan_summary_counts(tmp_path, monkeypatch):
    _make_staging(tmp_path, monkeypatch)
    src = tmp_path / "external"
    sub = src / "M13_sub"
    sub.mkdir(parents=True)
    (sub / "Light_a.fit").write_text("x")
    (sub / "Light_b.fit").write_text("y")
    junk = src / "Misc"
    junk.mkdir()
    (junk / "notes.fit").write_text("no header")           # → holding
    summ = ingest.scan_summary(ingest.scan_directory_plan(str(src)))
    assert summ["objects"] == 1                             # M13
    assert summ["to_import"] == 2                           # two lights
    assert summ["to_holding"] == 1                          # the unidentifiable fit
    assert summ["total"] == 3
    assert summ["by_kind"]["light"] == 2


def test_unrecognized_loose_files_go_to_holding(tmp_path, monkeypatch):
    """A plain folder of loose content (no `_sub`/`_photo`, no Stacked_* FITS) isn't
    vacuumed up as a stack, but is no longer silently dropped — 6c routes every
    content file to the Inbox/ holding area for manual assign."""
    _make_staging(tmp_path, monkeypatch)
    src = tmp_path / "external"
    loose = src / "Vacation"
    loose.mkdir(parents=True)
    (loose / "beach.jpg").write_text("j")
    (loose / "notes.fit").write_text("f")             # no usable header
    ops = ingest.scan_directory_plan(str(src))
    assert {op.kind for op in ops} == {"unassigned"}
    assert sorted(op.dest_rel for op in ops) == [
        "Inbox/Vacation/beach.jpg", "Inbox/Vacation/notes.fit"]


def test_apply_collision_distinct_gets_suffix(tmp_path, monkeypatch):
    """Two distinct files with the same name landing on one target → the second is
    written under a `_1` suffix (never overwritten, never renamed lossily)."""
    _make_staging(tmp_path, monkeypatch)
    src = tmp_path / "external"
    for folder, content in (("A", "AAA"), ("B", "BBB")):
        d = src / folder / "M13_sub"
        d.mkdir(parents=True)
        (d / "Light_a.fit").write_text(content)        # same name, different bytes
    ops = ingest.scan_directory_plan(str(src))
    res = ingest.apply_ops(ops)
    assert res["moved"] == 2 and res["skipped"] == 0
    names = sorted(p.name for p in config.lights_dir("M13").iterdir())
    assert names == ["Light_a.fit", "Light_a_1.fit"]
    # source untouched (copy)
    assert (src / "A" / "M13_sub" / "Light_a.fit").read_text() == "AAA"


def test_apply_collision_identical_is_skipped(tmp_path, monkeypatch):
    """Byte-identical same-name files are recognised as duplicates → skipped, not
    suffixed."""
    _make_staging(tmp_path, monkeypatch)
    src = tmp_path / "external"
    for folder in ("A", "B"):
        d = src / folder / "M13_sub"
        d.mkdir(parents=True)
        (d / "Light_a.fit").write_text("SAME")         # identical bytes
    ops = ingest.scan_directory_plan(str(src))
    res = ingest.apply_ops(ops)
    assert res["moved"] == 1 and res["skipped"] == 1
    assert [p.name for p in config.lights_dir("M13").iterdir()] == ["Light_a.fit"]


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


# ── 6b: header-based classification + layout registry ─────────────────────────

def _fits_hdr(path, *, object=None, imagetyp=None, filter=None, ra=None, dec=None):
    """Write a tiny FITS frame carrying the headers 6b classifies on."""
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="float32"))
    if object is not None:
        h.header["OBJECT"] = object
    if imagetyp is not None:
        h.header["IMAGETYP"] = imagetyp
    if filter is not None:
        h.header["FILTER"] = filter
    if ra is not None:
        h.header["RA"] = ra
    if dec is not None:
        h.header["DEC"] = dec
    h.writeto(path)


@pytest.mark.parametrize("raw,expected", [
    ("Light", "light"), ("Light Frame", "light"), ("OBJECT", "light"),
    ("Dark", "dark"), ("Master Dark", "dark"),
    ("Flat", "flat"), ("Flat Field", "flat"), ("FLATFIELD", "flat"),
    ("Bias", "bias"), ("Offset", "bias"),
    ("weird", None), (None, None), ("", None),
])
def test_normalize_imagetyp(raw, expected):
    assert ingest._normalize_imagetyp(raw) == expected


def test_frame_info_reads_headers(tmp_path):
    p = tmp_path / "f.fit"
    _fits_hdr(p, object="M 1", imagetyp="Light", filter="LP", ra=84.02, dec=22.06)
    info = ingest.frame_info(str(p))
    assert info["object"] == "M 1"
    assert info["imagetyp"] == "light"
    assert info["filter"] == "LP"
    assert info["ra_deg"] == pytest.approx(84.02)
    # frame_radec still works through the wrapper
    assert ingest.frame_radec(str(p)) == pytest.approx((84.02, 22.06))


def test_m110_store_layout_routes_subdirs(tmp_path, monkeypatch):
    """A precursor store (~/Astronomy/Images shape) sorts lights/darks/flats/stacks/
    finished onto the matching M110 dirs; process/ is skipped."""
    _make_staging(tmp_path, monkeypatch)
    src = tmp_path / "Astro" / "FITS" / "M1"
    _fits_hdr(src / "lights" / "Light_M1_a.fit", imagetyp="Light")
    _fits_hdr(src / "darks" / "Dark_a.fit", imagetyp="Dark")
    _fits_hdr(src / "flats" / "Flat_a.fit", imagetyp="Flat")
    (src / "stacks").mkdir(parents=True)
    (src / "stacks" / "M1_processed.tif").write_text("t")
    (src / "process").mkdir(parents=True)
    (src / "process" / "lights.fit").write_text("p")   # Siril sandbox → skip
    (tmp_path / "Astro" / "Finished Images" / "M1").mkdir(parents=True)
    (tmp_path / "Astro" / "Finished Images" / "M1" / "M1-final.png").write_text("f")

    ops = ingest.scan_directory_plan(tmp_path / "Astro")
    by_kind = {}
    for op in ops:
        by_kind.setdefault(op.kind, []).append(op)
        assert op.layout == "m110-store"
    assert by_kind["light"][0].dest_rel == "Images/M1/lights/Light_M1_a.fit"
    assert by_kind["dark"][0].dest_rel.startswith("Images/M1/darks/")
    assert by_kind["flat"][0].dest_rel.startswith("Images/M1/flats/")
    assert by_kind["siril-stack"][0].dest_rel.startswith("Images/M1/stacks/")
    assert by_kind["finished"][0].dest_rel == "Images/M1/finished/M1-final.png"
    all_srcs = [op.src for ops_ in by_kind.values() for op in ops_]
    assert not any(s.endswith("process/lights.fit") for s in all_srcs)  # sandbox skipped


def test_siril_project_root_imports_lights_calibration_and_root_stack(tmp_path, monkeypatch):
    """#57: point import at a folder of Siril projects. A project *root* (M1/ that
    contains lights/darks/flats/biases) is recognized, and the loose files Siril
    left beside the folders — a stack, a processing product, a finished render —
    route by tier instead of falling to the holding area."""
    _make_staging(tmp_path, monkeypatch)
    proj = tmp_path / "Siril" / "M1"
    _fits_hdr(proj / "lights" / "Light_M1_a.fit", imagetyp="Light")
    _fits_hdr(proj / "darks" / "Dark_a.fit", imagetyp="Dark")
    _fits_hdr(proj / "flats" / "Flat_a.fit", imagetyp="Flat")
    _fits_hdr(proj / "biases" / "Bias_a.fit", imagetyp="Bias")
    (proj / "M1_stacked.fit").write_text("S")        # loose root stack → stacks/
    (proj / "M1_processed.fit").write_text("W")      # loose product .fit → working_files/
    (proj / "M1_final.png").write_text("F")          # loose finished render → finished/
    (proj / "process").mkdir()
    (proj / "process" / "pp_light.fit").write_text("scratch")   # Siril scratch → skipped

    ops = ingest.scan_directory_plan(tmp_path / "Siril")
    dest = {op.kind: op.dest_rel for op in ops}
    assert dest["light"] == "Images/M1/lights/Light_M1_a.fit"
    assert dest["dark"].startswith("Images/M1/darks/")
    assert dest["flat"].startswith("Images/M1/flats/")
    assert dest["bias"].startswith("Images/M1/biases/")
    assert dest["siril-stack"] == "Images/M1/stacks/M1_stacked.fit"
    assert dest["working"] == "Images/M1/working_files/M1_processed.fit"
    assert dest["finished"] == "Images/M1/finished/M1_final.png"
    assert all(op.object == "M1" for op in ops)
    assert not any("pp_light.fit" in op.src for op in ops)     # process/ sandbox skipped
    assert ingest.scan_summary(ops)["to_holding"] == 0         # nothing stranded


def test_sub_folder_project_canonicalizes_object(tmp_path, monkeypatch):
    """#57: a Seestar/Siril `<obj>_sub/lights` project imports under the object's
    real id (M63), not the folder-name-with-suffix (`M63_sub`)."""
    _make_staging(tmp_path, monkeypatch)
    _fits_hdr(tmp_path / "src" / "M63_sub" / "lights" / "Light_M63_a.fit",
              imagetyp="Light")
    ops = ingest.scan_directory_plan(tmp_path / "src")
    assert [op.object for op in ops] == ["M63"]
    assert ops[0].dest_rel == "Images/M63/lights/Light_M63_a.fit"


def test_loose_subs_in_named_folder_route_by_folder_name(tmp_path, monkeypatch):
    """#57: a folder of loose subs with no `lights/` subdir and no usable header
    routes by the folder name — but only when it resolves to a known catalog
    object, so a generic/session-named folder stays in the holding area."""
    _make_staging(tmp_path, monkeypatch)
    # Known object folder, headerless subs (no IMAGETYP, no OBJECT).
    _fits_hdr(tmp_path / "src" / "M64" / "Light_a.fit")
    _fits_hdr(tmp_path / "src" / "M64" / "Light_b.fit")
    # Generic folder, same headerless subs → not a known object → holding.
    _fits_hdr(tmp_path / "src" / "session_07" / "Light_a.fit")

    ops = ingest.scan_directory_plan(tmp_path / "src")
    by = {}
    for op in ops:
        by.setdefault((op.object, op.kind), 0)
        by[(op.object, op.kind)] += 1
    assert by.get(("M64", "light")) == 2               # routed by folder name
    assert by.get(("", "unassigned")) == 1             # generic folder → holding


def test_group_ops_splits_per_object_in_recursive_store(tmp_path, monkeypatch):
    """Regression (#46): a precursor store has a `lights/` folder under *every*
    object, so grouping by the bare folder name collapsed them into one bogus row.
    group_ops must key on the resolved object → one group per object+kind."""
    _make_staging(tmp_path, monkeypatch)
    fits = tmp_path / "Astro" / "FITS"
    _fits_hdr(fits / "M51" / "lights" / "Light_M51_a.fit", imagetyp="Light")
    _fits_hdr(fits / "M51" / "lights" / "Light_M51_b.fit", imagetyp="Light")
    (fits / "M51" / "stacks").mkdir(parents=True)
    (fits / "M51" / "stacks" / "M51_processed.tif").write_text("t")
    _fits_hdr(fits / "M81 M82" / "lights" / "Light_a.fit", imagetyp="Light")
    _fits_hdr(fits / "NGC 7000" / "lights" / "Light_a.fit", imagetyp="Light")

    groups = ingest.group_ops(ingest.scan_directory_plan(fits))
    light = {g.object: g.frames for g in groups if g.kind == "light"}
    assert light == {"M51": 2, "M81 M82": 1, "NGC 7000": 1}   # not one merged "lights"
    assert any(g.kind == "siril-stack" and g.object == "M51" for g in groups)


def test_loose_finished_raster_routes_to_finished(tmp_path, monkeypatch):
    """A loose *_processed/final raster (a Siril export dropped in an object folder)
    is recognized as the object's finished render — not swept to the holding area."""
    _make_staging(tmp_path, monkeypatch)
    src = tmp_path / "export" / "M5"
    src.mkdir(parents=True)
    fn = "M_5_674x10sec_2026-05-11_drizzle-1-5x_processed.png"
    (src / fn).write_text("x" * 64)

    ops = ingest.scan_directory_plan(tmp_path / "export")
    assert len(ops) == 1
    op = ops[0]
    assert op.kind == "finished"
    assert op.object == "M5"
    assert op.layout == "finished-render"
    assert op.dest_rel == f"Images/M5/finished/{fn}"


def test_loose_non_finished_raster_still_held(tmp_path, monkeypatch):
    """A loose raster *without* a finished hint isn't over-claimed — it still goes to
    the holding area for manual assignment."""
    _make_staging(tmp_path, monkeypatch)
    src = tmp_path / "export" / "randoms"
    src.mkdir(parents=True)
    (src / "screenshot.png").write_text("z" * 32)
    ops = ingest.scan_directory_plan(tmp_path / "export")
    assert [o.kind for o in ops] == ["unassigned"]


def test_raw_fits_pile_sorts_by_header(tmp_path, monkeypatch):
    """Loose mixed FITS in one dir sort by IMAGETYP; the object comes from OBJECT."""
    _make_staging(tmp_path, monkeypatch)
    pile = tmp_path / "dump"
    _fits_hdr(pile / "a.fit", object="M51", imagetyp="Light")
    _fits_hdr(pile / "b.fit", object="M51", imagetyp="Dark")
    _fits_hdr(pile / "c.fit", imagetyp="Bias")          # no OBJECT → folder name
    _fits_hdr(pile / "junk.fit")                         # no type/object → holding (6c)

    ops = ingest.scan_directory_plan(tmp_path / "dump")
    by_kind = {op.kind: op for op in ops}
    assert set(by_kind) == {"light", "dark", "bias", "unassigned"}
    assert by_kind["light"].dest_rel.startswith("Images/M51/lights/")
    assert by_kind["dark"].dest_rel.startswith("Images/M51/darks/")
    assert by_kind["bias"].dest_rel.startswith("Images/dump/biases/")  # folder fallback
    assert by_kind["unassigned"].dest_rel == "Inbox/dump/junk.fit"     # 6c holding
    assert by_kind["light"].layout == "raw-fits"


def test_header_wins_over_sub_folder(tmp_path, monkeypatch):
    """A DARK-header frame sitting in an `_sub` lights folder routes to darks/."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M81_sub"
    _fits_hdr(sub / "Light_M81_a.fit", imagetyp="Light")
    _fits_hdr(sub / "Dark_stray.fit", imagetyp="Dark")

    ops = ingest.scan_staging_plan()
    by_kind = {op.kind: op for op in ops}
    assert by_kind["light"].dest_rel.startswith("Images/M81/lights/")
    assert by_kind["dark"].dest_rel.startswith("Images/M81/darks/")


def test_own_content_tree_not_reimported(tmp_path, monkeypatch):
    """Scanning the app's own Images/ tree yields no ops (no re-import into self)."""
    _make_staging(tmp_path, monkeypatch)
    _fits_hdr(config.lights_dir("M1") / "Light_M1_a.fit", imagetyp="Light")
    assert ingest.scan_directory_plan(config.IMAGES_DIR) == []


def test_group_ops_natural_object_sort(tmp_path, monkeypatch):
    """Object rows sort M1, M2, … M10, M100 — not lexically (M1, M10, M100, M2)."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    for obj in ("M100", "M2", "M10", "M1"):
        d = staging / f"{obj}_sub"
        d.mkdir()
        (d / f"Light_{obj}.fit").write_text("x")
    objs = [g.object for g in ingest.group_ops(ingest.scan_staging_plan())]
    assert objs == ["M1", "M2", "M10", "M100"]


def test_layout_registry_labels():
    assert ingest.layout_label("seestar") == "Seestar"
    assert ingest.layout_label("m110-store") == "M110 store"
    assert ingest.LAYOUTS_BY_ID["asiair"].available is False


# ── 6c: holding area + manual assign ──────────────────────────────────────────

def test_sweep_holds_unclaimed_content_skips_junk(tmp_path, monkeypatch):
    """Every unclaimed content file (headerless FITS, stray image) is swept to the
    holding area; non-content + thumbnails + hidden files are never surfaced."""
    _make_staging(tmp_path, monkeypatch)
    d = tmp_path / "src" / "mess"
    d.mkdir(parents=True)
    _fits_hdr(d / "good.fit", object="M31", imagetyp="Light")  # claimed → lights
    _fits_hdr(d / "headerless.fit")                            # → holding
    (d / "render.png").write_text("p")                         # stray image → holding
    (d / "render_thn.png").write_text("t")                     # thumbnail → skip
    (d / "notes.txt").write_text("x")                          # non-content → skip
    (d / ".hidden.jpg").write_text("h")                        # hidden → skip

    ops = ingest.scan_directory_plan(tmp_path / "src")
    held = sorted(Path(o.src).name for o in ops if o.kind == "unassigned")
    assert held == ["headerless.fit", "render.png"]
    assert any(o.kind == "light" for o in ops)                 # good.fit still classified
    assert all(o.dest_rel.startswith("Inbox/mess/")
               for o in ops if o.kind == "unassigned")


def test_nothing_silently_ignored(tmp_path, monkeypatch):
    """Invariant: every content file in a messy tree appears in some op (claimed or
    held) — nothing is dropped."""
    _make_staging(tmp_path, monkeypatch)
    src = tmp_path / "src"
    _fits_hdr(src / "M13_sub" / "Light_a.fit", imagetyp="Light")
    _fits_hdr(src / "loose" / "x.fit")                         # headerless
    (src / "loose" / "pretty.jpg").write_text("j")
    ops = ingest.scan_directory_plan(src)
    seen = {Path(o.src).name for o in ops}
    assert {"Light_a.fit", "x.fit", "pretty.jpg"} <= seen


def test_scan_holding_groups_by_top_folder(tmp_path, monkeypatch):
    """scan_holding lists Inbox content as unassigned ops grouped by top subfolder."""
    root, _ = _make_staging(tmp_path, monkeypatch)
    (config.STAGING_DIR / "M42").mkdir(parents=True)
    (config.STAGING_DIR / "M42" / "a.fit").write_text("a")
    (config.STAGING_DIR / "M42" / "b.png").write_text("b")
    (config.STAGING_DIR / "loner.jpg").write_text("l")        # directly in Inbox
    (config.STAGING_DIR / "skip.txt").write_text("x")         # non-content

    groups = ingest.group_ops(ingest.scan_holding())
    by_group = {g.group: g for g in groups}
    assert by_group["M42"].frames == 2
    assert all(g.kind == "unassigned" for g in groups)
    assert "(loose)" in by_group              # loner.jpg
    assert ingest.holding_count() == 3


def _held_fits(folder, name, **headers):
    import numpy as np
    folder.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="float32"))
    for k, v in headers.items():
        h.header[k] = v
    h.writeto(folder / name)


def test_identify_holding_from_object_header(tmp_path, monkeypatch):
    """#26: a held FITS whose OBJECT header names a catalog object suggests it
    (folding Seestar spacing 'M 10' → 'M10') + a kind from IMAGETYP."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    _held_fits(staging / "mystery", "a.fit", OBJECT="M 10", IMAGETYP="Light")
    info = ingest.annotate_holding(ingest.group_ops(ingest.scan_holding()))
    assert len(info) == 1
    assert info[0]["suggested_slug"] == "m10"
    assert info[0]["suggested_id"] == "M10"
    assert "OBJECT" in (info[0]["reason"] or "")
    assert info[0]["suggested_kind"] == "light"
    assert info[0]["header"]["object"] == "M 10"


def test_identify_holding_from_nearest_radec(tmp_path, monkeypatch):
    """#26: no usable OBJECT header → suggest the nearest catalog object by RA/Dec."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    ra, dec = catalog.load_coords()["m10"]
    _held_fits(staging / "blob", "x.fit", OBJECT="Unknown", RA=ra, DEC=dec)
    info = ingest.annotate_holding(ingest.group_ops(ingest.scan_holding()))
    assert info[0]["suggested_slug"] == "m10"
    assert "from M10" in (info[0]["reason"] or "")


def test_identify_holding_kind_only_from_calibration(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    _held_fits(staging / "cal", "d.fit", IMAGETYP="Dark")
    info = ingest.annotate_holding(ingest.group_ops(ingest.scan_holding()))
    assert info[0]["suggested_kind"] == "dark"
    assert info[0]["suggested_id"] is None      # no object / coords → no id


def test_identify_holding_non_fits_degrades(tmp_path, monkeypatch):
    _root, staging = _make_staging(tmp_path, monkeypatch)
    (staging / "misc").mkdir()
    (staging / "misc" / "note.jpg").write_bytes(b"not a real jpg")
    info = ingest.annotate_holding(ingest.group_ops(ingest.scan_holding()))
    assert info[0]["header"] is None
    assert info[0]["suggested_id"] is None
    assert info[0]["sample"].endswith("note.jpg")


def test_discard_holding_deletes_and_prunes(tmp_path, monkeypatch):
    """discard_holding removes a held group's files and prunes the emptied folder,
    leaving other held groups untouched."""
    root, _ = _make_staging(tmp_path, monkeypatch)
    (config.STAGING_DIR / "junk").mkdir(parents=True)
    (config.STAGING_DIR / "junk" / "a.fit").write_text("a")
    (config.STAGING_DIR / "junk" / "b.png").write_text("b")
    (config.STAGING_DIR / "keep.jpg").write_text("k")            # loose, unrelated

    groups = ingest.group_ops(ingest.scan_holding())
    g = next(g for g in groups if g.group == "junk")
    res = ingest.discard_holding(g)

    assert res["deleted"] == 2
    assert not (config.STAGING_DIR / "junk").exists()            # emptied dir pruned
    assert (config.STAGING_DIR / "keep.jpg").exists()            # other group intact
    assert ingest.holding_count() == 1


def test_discard_holding_refuses_paths_outside_inbox(tmp_path, monkeypatch):
    """Safety: an op whose src escapes Inbox/ is skipped, never deleted."""
    root, _ = _make_staging(tmp_path, monkeypatch)
    outside = config.DATA_ROOT / "Images" / "precious.fit"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("do not delete")
    g = ingest.IngestGroup(
        group="spoof", object="", kind="unassigned", frames=1, size_bytes=0,
        dest_dir="", new_object=False, action="move",
        ops=[ingest.IngestOp(str(outside), str(outside), "unassigned", "spoof",
                             "", False, "move", 0, "holding", "")])
    res = ingest.discard_holding(g)

    assert res["deleted"] == 0
    assert outside.exists()                                      # untouched


def test_safe_segment_neutralizes_traversal():
    """SECURITY F1: a destination folder name can't contain separators, parent refs,
    or control chars — an attacker-controlled FITS OBJECT header / folder name is
    reduced to a single safe path segment; ordinary names pass through."""
    assert ingest._safe_segment("M81 M82") == "M81 M82"          # ordinary, verbatim
    assert ingest._safe_segment("NGC 7000") == "NGC 7000"
    assert "/" not in ingest._safe_segment("../../etc/cron.d/x")
    assert ".." not in ingest._safe_segment("../../etc/cron.d/x")
    assert "\\" not in ingest._safe_segment(r"..\..\Windows\System32")
    assert ingest._safe_segment("") == "unknown"                 # never empty
    assert ingest._safe_segment("...") == "unknown"
    assert ingest._safe_segment("a\x00b/c") == "ab c"            # null removed, sep→space


def test_canonical_target_cannot_escape_the_store(tmp_path, monkeypatch):
    """A crafted OBJECT header / device folder name resolves to a contained folder,
    so canonical_target never yields a traversal segment."""
    _make_staging(tmp_path, monkeypatch)
    seg = ingest.canonical_target("../../../.config/autostart")
    assert "/" not in seg and ".." not in seg


def test_apply_ops_refuses_writes_outside_the_store(tmp_path, monkeypatch):
    """SECURITY F1 hard guard: the only writer rejects any op whose destination
    resolves outside the data root, whatever built it — nothing is written."""
    root, _ = _make_staging(tmp_path, monkeypatch)
    (config.STAGING_DIR / "src").mkdir(parents=True)
    src = config.STAGING_DIR / "src" / "f.fit"
    src.write_text("payload")
    escaped = tmp_path / "outside" / "pwned.fit"           # sibling of the data root
    op = ingest.IngestOp(str(src), str(escaped), "light", "src",
                         "../outside/pwned.fit", True, "move", 7, "seestar", "x")

    with pytest.raises(ValueError, match="outside the data store"):
        ingest.apply_ops([op])
    assert not escaped.exists()                             # nothing written
    assert src.exists()                                    # source untouched


def test_assign_moves_held_files_into_target(tmp_path, monkeypatch):
    """assign() rebuilds a held group to move its files into Images/<obj>/<kind>;
    apply_ops actually moves them out of the holding area."""
    root, _ = _make_staging(tmp_path, monkeypatch)
    (config.STAGING_DIR / "blob").mkdir(parents=True)
    (config.STAGING_DIR / "blob" / "f1.fit").write_text("1")
    (config.STAGING_DIR / "blob" / "f2.fit").write_text("2")

    groups = ingest.group_ops(ingest.scan_holding())
    g = next(g for g in groups if g.group == "blob")
    assigned = ingest.assign(g, "M27", "light")
    assert assigned.kind == "light"
    assert all(o.action == "move" and o.kind == "light" for o in assigned.ops)
    res = ingest.apply_ops(assigned.ops)
    assert res["moved"] == 2
    assert sorted(p.name for p in config.lights_dir("M27").iterdir()) == ["f1.fit", "f2.fit"]
    assert not (config.STAGING_DIR / "blob" / "f1.fit").exists()   # moved out of Inbox


def test_canonical_folds_onto_spaced_folder(tmp_path, monkeypatch):
    """Dedup regression: a device 'M 10_sub' must fold onto an existing 'M 10/'
    folder (space spelling) — not resolve to 'M10' and re-import already-present
    frames into a different dir."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    fn = "Light_M 10_20.0s_IRCUT_20260619-003957.fit"
    (config.lights_dir("M 10")).mkdir(parents=True)       # store uses the spaced spelling
    (config.lights_dir("M 10") / fn).write_text("x")
    sub = staging / "M 10_sub"
    sub.mkdir()
    (sub / fn).write_text("x")                            # same file, already imported
    assert ingest.canonical_target("M 10") == "M 10"
    assert ingest.scan_staging_plan() == []              # deduped, nothing held


def test_sub_per_frame_jpg_previews_not_held(tmp_path, monkeypatch):
    """Regression: a Seestar `_sub` folder saves a full-size `.jpg` preview beside
    every `.fit` sub. The `.fit` are lights; the per-sub JPGs are recognized sidecars
    that must NOT be swept into the holding area (and `_thn.jpg` is skipped)."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M109_sub"
    sub.mkdir()
    for i in range(3):
        stem = f"Light_M109_20s_IRCUT_2026061{i}"
        _fits_hdr(sub / f"{stem}.fit", object="M109", imagetyp="Light")
        (sub / f"{stem}.jpg").write_text("preview")          # per-sub full preview
        (sub / f"{stem}_thn.jpg").write_text("thumb")        # per-sub thumbnail
    ops = ingest.scan_staging_plan()
    kinds = {o.kind for o in ops}
    assert "unassigned" not in kinds                          # no JPG sweep to holding
    assert kinds == {"light"} and len(ops) == 3              # only the 3 .fit lights


def test_already_imported_sub_not_swept_to_holding(tmp_path, monkeypatch):
    """Regression: a Seestar `_sub` folder whose lights are already in the library
    must produce NO ops — not get swept into the holding area as 'unassigned'."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M109_sub"
    for nm in ("Light_M109_a.fit", "Light_M109_b.fit"):
        _fits_hdr(sub / nm, object="M109", imagetyp="Light")
        (config.lights_dir("M109") / nm).parent.mkdir(parents=True, exist_ok=True)
        _fits_hdr(config.lights_dir("M109") / nm, object="M109", imagetyp="Light")
    ops = ingest.scan_staging_plan()
    assert ops == []                      # nothing new, nothing held


def test_sub_lights_skip_per_frame_header_read(tmp_path, monkeypatch):
    """Perf: classifying a `_sub` folder of `Light_*` frames must NOT open a header
    per frame (prohibitive over SMB). frame_info is only consulted for odd names."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M27_sub"
    for i in range(5):
        _fits_hdr(sub / f"Light_M27_{i}.fit", object="M27", imagetyp="Light")
    calls = []
    monkeypatch.setattr(ingest, "frame_info",
                        lambda p: calls.append(p) or {"object": None, "imagetyp": None,
                                                       "filter": None, "ra_deg": None, "dec_deg": None})
    ops = ingest.scan_staging_plan()
    assert len(ops) == 5 and all(o.kind == "light" for o in ops)
    assert calls == []                    # no per-frame header reads for Light_* files


def test_sub_emit_is_batched_not_per_file(tmp_path, monkeypatch):
    """Perf: a `_sub` folder of N lights must emit in ONE batch, not N calls — each
    `_emit_files` call lists the destination, so per-file is O(N × dest)."""
    _root, staging = _make_staging(tmp_path, monkeypatch)
    sub = staging / "M27_sub"
    for i in range(30):
        _fits_hdr(sub / f"Light_M27_{i}.fit", object="M27", imagetyp="Light")
    calls = []
    real = ingest._emit_files
    monkeypatch.setattr(ingest, "_emit_files",
                        lambda *a, **k: calls.append(a[2]) or real(*a, **k))  # a[2]=kind
    ops = ingest.scan_staging_plan()
    assert len(ops) == 30
    assert calls == ["light"]              # exactly one batched emit, not 30


def test_assign_media_routes_to_media_dir(tmp_path, monkeypatch):
    root, _ = _make_staging(tmp_path, monkeypatch)
    (config.STAGING_DIR / "clips").mkdir(parents=True)
    (config.STAGING_DIR / "clips" / "moon.jpg").write_text("m")
    g = next(g for g in ingest.group_ops(ingest.scan_holding()) if g.group == "clips")
    assigned = ingest.assign(g, "Lunar_photo", "media")
    assert assigned.ops[0].dest_rel == "Media/Lunar_photo/moon.jpg"
