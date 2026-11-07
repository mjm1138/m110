"""N.I.N.A. / PINS import (#203): routed by header, never by folder layout.

The frames are tiny FITS carrying the cards a real PINS S50 night writes
(`tests._helpers.nina_frame`). N.I.N.A.'s file pattern is a user setting, so the
same night is imported from two layouts: stock (`<date>/LIGHT/`, every target in
one folder) and target-first (`<date>/<target>/LIGHT/`, what PINS wrote).
"""
import pytest

from m110 import calibration, config, ingest, scan_sessions
from tests._helpers import nina_frame, seed_root

NIGHT = [  # (target-first folder, OBJECT, exposure, filter)
    ("M 110", "M 110", 30.0, "IR"),
    ("M 45 Panel 1", "M 45 Panel 1", 10.0, "IR"),
    ("M 45 Panel 2", "M 45 Panel 2", 10.0, "IR"),
    ("NGC 2024 IC 434", "NGC 2024 IC 434", 20.0, "LP"),
]


def _night(src, layout):
    for i, (folder, obj, exp, filt) in enumerate(NIGHT):
        for n in range(2):
            name = f"2026-11-06_2{i}-0{n}-00_{filt}_8.00_{exp:.2f}s_000{n}.fits"
            d = (src / "2026-11-06" / folder / "LIGHT" if layout == "target-first"
                 else src / "2026-11-06" / "LIGHT")
            nina_frame(d / name, obj=obj, exp=exp, filt=filt,
                       date_loc=f"2026-11-06T2{i}:0{n}:00.0")
    for n, exp in enumerate((10.0, 20.0, 30.0)):
        nina_frame(src / "2026-11-06" / "DARK" / f"2026-11-07_05-0{n}-00_5.50_{exp:.2f}s_0000.fits",
                   imagetyp="DARK", obj=None, exp=exp, temp=5.5, filt="Dark",
                   date_loc=f"2026-11-07T05:0{n}:00.0")


def _groups(ops):
    return {(g.kind, g.object): g for g in ingest.group_ops(ops)}


@pytest.mark.parametrize("layout", ["target-first", "stock"])
def test_a_nina_night_routes_by_header_whatever_the_folders(tmp_path, monkeypatch, layout):
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "PINS"
    _night(src, layout)
    ops = ingest.scan_source_plan(src)
    groups = _groups(ops)
    assert set(groups) == {
        ("light", "M110"), ("light", "M45_mosaic"), ("light", "NGC 2024 IC 434"),
        ("cal-dark", "S50_15e7e390"),
    }
    # the two panels are one mosaic dataset (#70 rule), not one object per panel
    assert groups[("light", "M45_mosaic")].frames == 4
    assert groups[("light", "M45_mosaic")].dest_dir == "Images/M45_mosaic/lights"
    # darks with no OBJECT → the device library, keyed on the serial in INSTRUME
    dark = groups[("cal-dark", "S50_15e7e390")]
    assert dark.frames == 3 and dark.dest_dir == "Calibration/S50_15e7e390/darks"
    assert not dark.new_object
    assert {g.layout for g in groups.values()} == {"nina"}
    assert ingest.layout_label("nina") == "N.I.N.A."
    # nothing became an object named after a folder
    assert not any(o.object in ("DARK", "LIGHT", "S50 Prime") for o in ops)
    assert not any(o.kind == "unassigned" for o in ops)


def test_the_alias_key_is_the_header_name_not_the_folder(tmp_path, monkeypatch):
    """Stock N.I.N.A. puts every target in `LIGHT/`: an alias keyed on the folder
    would send every later light to one object. It keys on the source name."""
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "PINS"
    _night(src, "stock")
    groups = _groups(ingest.scan_source_plan(src))
    field = groups[("light", "NGC 2024 IC 434")]
    assert field.group == "LIGHT"
    assert field.alias_key == "NGC 2024 IC 434"
    assert groups[("light", "M45_mosaic")].alias_key == "M 45_mosaic"

    # remembering a retarget routes the next import of that name, and only it
    ingest.add_alias(field.alias_key, "IC 434")
    again = _groups(ingest.scan_source_plan(src))
    assert ("light", "IC 434") in again and ("light", "NGC 2024 IC 434") not in again
    assert ("light", "M110") in again


def test_an_off_catalog_field_name_offers_its_catalog_members(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "PINS"
    _night(src, "target-first")
    groups = ingest.annotate_pointing(ingest.group_ops(ingest.scan_source_plan(src)))
    by = {(g.kind, g.object): g for g in groups}
    assert by[("light", "NGC 2024 IC 434")].candidates[:2] == ["NGC 2024", "IC 434"]
    assert by[("light", "M45_mosaic")].candidates[:1] == ["M45"]
    assert by[("light", "M110")].candidates == []          # a catalog object: none
    # retargeting clears them (the row is now that object)
    rt = ingest.retarget(by[("light", "NGC 2024 IC 434")], "IC 434")
    assert rt.candidates == [] and rt.alias_key == "NGC 2024 IC 434"


def test_a_nameless_dark_from_an_unidentified_camera_is_held(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "DARK"
    nina_frame(src / "d.fits", imagetyp="DARK", obj=None, telescop="")
    from astropy.io import fits
    with fits.open(src / "d.fits", mode="update") as f:
        del f[0].header["INSTRUME"]
    ops = ingest.scan_source_plan(src)
    assert [o.kind for o in ops] == ["unassigned"]


def test_imported_nina_darks_are_a_raw_set_in_the_library(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "PINS"
    for n in range(4):
        nina_frame(src / "DARK" / f"d{n}.fits", imagetyp="DARK", obj=None, exp=30.0,
                   temp=5.7, date_loc="2026-11-07T05:00:00.0")
    ingest.apply_ops(ingest.scan_source_plan(src))
    lib = calibration.library("S50_15e7e390")["darks"]
    assert len(lib) == 4 and all(m.raw for m in lib)
    assert {m.night for m in lib} == {"2026-11-06"}           # the evening it began
    (st,) = calibration.raw_sets(lib)
    assert len(st.frames) == 4


def test_nina_sessions_are_the_app_device_and_not_dark_subtracted(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "PINS"
    _night(src, "target-first")
    ingest.apply_ops(ingest.scan_source_plan(src))
    rows = {r["object_dir"]: r for r in scan_sessions.scan()}
    m110 = rows["M110"]
    assert m110["device"] == "S50_15e7e390" and m110["capture"] == "nina"
    assert m110["date"] == "2026-11-06"                 # DATE-LOC, the local night
    assert m110["dark_ref"] is None                     # no on-device dark to infer
    assert rows["NGC 2024 IC 434"]["slugs"] == ["ngc-2024", "ic-434"]


def test_the_devices_rollup_lists_a_raw_set_once_and_the_capture_paths(tmp_path, monkeypatch):
    """60 N.I.N.A. darks are three library rows (one per set), not 60 'masters';
    the S50 shows one device whose frames came through both its app and N.I.N.A."""
    from m110 import build_derived, derived
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "PINS"
    _night(src, "target-first")
    for n in range(3):                                   # a second 30 s dark
        nina_frame(src / "DARK2" / f"x{n}.fits", imagetyp="DARK", obj=None, exp=30.0,
                   temp=5.5, filt="Dark", date_loc="2026-11-07T05:10:00.0")
    ingest.apply_ops(ingest.scan_source_plan(src))
    scan_sessions.write_jsonl(scan_sessions.scan())
    build_derived.main()
    (dev,) = derived.load_devices()
    assert dev["device"] == "S50_15e7e390"
    assert dev["captured_via"] == ["nina"]
    rows = sorted((m["exptime"], m["frames"], m["raw"]) for m in dev["masters"])
    assert rows == [(10.0, 1, True), (20.0, 1, True), (30.0, 4, True)]
    thirty = next(m for m in dev["masters"] if m["exptime"] == 30.0)
    assert thirty["label"].startswith("4 raw frames · 2026-11-06")
    assert len(thirty["members"]) == 4


def test_a_header_cache_from_before_capture_profiles_heals(tmp_path, monkeypatch):
    """`session_headers.json` entries written before #203 have no device/capture;
    they are re-read once rather than trusted (else a N.I.N.A. sub would keep
    reading as the app's, dark-subtracted)."""
    import json
    seed_root(tmp_path, monkeypatch)
    sub = nina_frame(config.lights_dir("M110") / "a.fits")
    cache_file = config.DERIVED_DIR / "session_headers.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"M110/a.fits": {
        "size": sub.stat().st_size, "telescop": "S50 Prime", "gain": 80,
        "binning": 1, "temp_c": 12.0}}))
    (row,) = scan_sessions.scan()
    assert row["device"] == "S50_15e7e390" and row["capture"] == "nina"
    assert json.loads(cache_file.read_text())["M110/a.fits"]["capture"] == "nina"
