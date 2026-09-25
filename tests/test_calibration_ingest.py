"""Importing a device-level calibration library (DwarfLab ``CALI_FRAME/``).

The Draco (2026-09 pre-release sample) ships master darks/flats/biases under
``CALI_FRAME/{dark,flat,bias}/cam_<n>/`` with EMPTY headers — every fact is in
the filename. They import into ``Calibration/<device>/{darks,flats,biases}/``
(the device inferred from a sibling session folder) and, as a temporary shim,
ingest stamps the parsed facts into M110's copy so everything downstream stays
header-driven. Temp fixtures only, never live data.
"""
import hashlib
from pathlib import Path

import numpy as np
from astropy.io import fits

from m110 import config, ingest
from tests._helpers import seed_root
from tests.test_ingest_dwarf import _draco_session

DARK_13 = "dark_exp_300.000000_gain_60_bin_1_13C_stack_10.fits"
DARK_26 = "dark_exp_300.000000_gain_60_bin_1_26C_stack_1.fits"
DARK_B2 = "dark_exp_300.000000_gain_0_bin_2_40C_stack_4.fits"
FLAT_1, FLAT_2 = "flat_gain_2_bin_1_ir_1.fits", "flat_gain_2_bin_1_ir_2.fits"
BIAS = "bias_gain_2_bin_1.fits"


def _headerless_master(path: Path, imagetyp: str | None = None):
    """A DwarfLab master exactly as the sample writes it: uint16 (BZERO int16),
    BAYERPAT, nothing else. `imagetyp` fakes a future production unit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.full((2, 2), 64, dtype="uint16"))
    h.header["BAYERPAT"] = "BGGR"
    if imagetyp:
        h.header["IMAGETYP"] = imagetyp
        h.header["EXPTIME"] = 300.0
    h.writeto(path)
    return path


def _cali_frame(where: Path, darks=(DARK_13, DARK_26, DARK_B2), flats=(FLAT_1, FLAT_2),
                biases=(BIAS,), cam="cam_0"):
    root = where / "CALI_FRAME"
    for n in darks:
        _headerless_master(root / "dark" / cam / n)
    for n in flats:
        _headerless_master(root / "flat" / cam / n)
    for n in biases:
        _headerless_master(root / "bias" / cam / n)
    (root / "dark" / "cam_2").mkdir()          # the sample's empty wide-camera dir
    return root


def _sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ── the filename parser (shim) ────────────────────────────────────────────────

def test_parse_dwarflab_master_name_all_three_vocabularies():
    assert ingest.parse_dwarflab_master_name(DARK_13) == {
        "tier": "darks", "exptime": 300.0, "gain": 60, "binning": 1,
        "temp_c": 13, "ncombine": 10}
    assert ingest.parse_dwarflab_master_name("DARK_EXP_10.000000_gain_80_bin_1_-5C_stack_2.fits") == {
        "tier": "darks", "exptime": 10.0, "gain": 80, "binning": 1,
        "temp_c": -5, "ncombine": 2}
    assert ingest.parse_dwarflab_master_name(FLAT_2) == {
        "tier": "flats", "gain": 2, "binning": 1, "filter_index": 2}
    assert ingest.parse_dwarflab_master_name(BIAS) == {
        "tier": "biases", "gain": 2, "binning": 1}
    for bad in ("Unknown_300s60_Duo-Band_20260919-220535997_13C.fits",
                "dark_exp_300_stack_1.fits", "master_dark.fit", "stacked-16_x.fits"):
        assert ingest.parse_dwarflab_master_name(bad) is None, bad


# ── recognizer + routing ──────────────────────────────────────────────────────

def test_cali_frame_routes_into_the_device_library(tmp_path, monkeypatch):
    """CALI_FRAME/ beside a Draco session → Calibration/Draco/<tier>/, the device
    read from the session's subs even though the walk visits CALI_FRAME first."""
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "Veil_nebula"
    _cali_frame(src)
    _draco_session(src, "Draco_RAW_TELE_Unknown_EXP_300_GAIN_60_2026-09-19-21-59-48-480")
    ops = ingest.scan_directory_plan(str(src))
    cal = [o for o in ops if o.kind.startswith("cal-")]
    assert not [o for o in ops if o.kind == "unassigned"]
    assert {o.kind for o in cal} == {"cal-dark", "cal-flat", "cal-bias"}
    dests = sorted(o.dest_rel for o in cal)
    assert dests == sorted([
        f"Calibration/Draco/darks/{DARK_13}", f"Calibration/Draco/darks/{DARK_26}",
        f"Calibration/Draco/darks/{DARK_B2}", f"Calibration/Draco/flats/{FLAT_1}",
        f"Calibration/Draco/flats/{FLAT_2}", f"Calibration/Draco/biases/{BIAS}"])
    for o in cal:
        assert o.layout == "calibration"
        assert o.object == "Draco"
        assert o.new_object is False              # a device is not a capture target
        assert o.group == "Draco calibration masters"
        assert o.stamp and o.stamp["IMAGETYP"][0].startswith("Master ")
        assert o.stamp["M110STMP"][0] == "filename"
    summ = ingest.scan_summary(ops)
    assert summ["objects"] == 1                   # NGC 6992 (by pointing), not Draco
    assert summ["to_holding"] == 0
    groups = ingest.group_ops(ops)
    cal_groups = [g for g in groups if g.kind.startswith("cal-")]
    assert {g.object for g in cal_groups} == {"Draco"}
    assert all(g.pointing is None for g in cal_groups)
    ingest.annotate_pointing(groups)               # must not try to point-check a master
    assert all(g.pointing is None for g in cal_groups)


def test_device_inferred_from_a_session_under_the_scan_root(tmp_path, monkeypatch):
    """CALI_FRAME/ nested one level deeper than the session: the holder dir has no
    session, the scan root does."""
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "dump"
    _cali_frame(src / "calibration")
    _draco_session(src, "Draco_RAW_TELE_NGC 6992_EXP_300_GAIN_60_2026-09-19-21-59-48-480",
                   obj="NGC 6992")
    ops = ingest.scan_directory_plan(str(src))
    cal = [o for o in ops if o.kind.startswith("cal-")]
    assert len(cal) == 6 and all(o.dest_rel.startswith("Calibration/Draco/") for o in cal)


def test_without_a_session_the_masters_are_held_and_explained(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "loose"
    _cali_frame(src)
    ops = ingest.scan_directory_plan(str(src))
    assert {o.kind for o in ops} == {"unassigned"}
    assert not (config.CALIBRATION_DIR / "unknown").exists()
    groups = ingest.group_ops(ops)
    assert {g.group for g in groups} == {"dark_cam_0", "flat_cam_0", "bias_cam_0"}
    for g in groups:
        aid = ingest.identify_holding(g)
        assert aid["suggested_kind"] == {"dark_cam_0": "dark", "flat_cam_0": "flat",
                                         "bias_cam_0": "bias"}[g.group]
        assert aid["suggested_id"] is None
        assert "unidentified device" in aid["note"]


# ── apply: stamp our copy, never the source ───────────────────────────────────

def test_apply_stamps_the_copy_and_leaves_the_source_alone(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "Veil_nebula"
    _cali_frame(src, darks=(DARK_13,), flats=(FLAT_1,), biases=(BIAS,))
    _draco_session(src, "Draco_RAW_TELE_Unknown_EXP_300_GAIN_60_2026-09-19-21-59-48-480")
    src_dark = src / "CALI_FRAME" / "dark" / "cam_0" / DARK_13
    before = (_sha(src_dark), src_dark.stat().st_mtime_ns)
    ops = ingest.scan_directory_plan(str(src))
    res = ingest.apply_ops(ops)
    assert res["cancelled"] is False and res["moved"] == len(ops)

    dest = config.CALIBRATION_DIR / "Draco" / "darks" / DARK_13
    hdr = fits.getheader(dest)
    assert hdr["IMAGETYP"] == "Master Dark"
    assert hdr["EXPTIME"] == 300.0 and hdr["GAIN"] == 60
    assert hdr["XBINNING"] == 1 and hdr["YBINNING"] == 1
    assert hdr["CCD-TEMP"] == 13 and hdr["NCOMBINE"] == 10
    assert hdr["TELESCOP"] == "Draco" and hdr["ORIGIN"] == "DWARFLAB"
    assert hdr["M110STMP"] == "filename"
    assert hdr["BAYERPAT"] == "BGGR"                       # the original card survives
    assert hdr["BZERO"] == 32768                            # int16 encoding untouched
    assert fits.getdata(dest).tolist() == [[64, 64], [64, 64]]
    flat = fits.getheader(config.CALIBRATION_DIR / "Draco" / "flats" / FLAT_1)
    assert flat["IMAGETYP"] == "Master Flat" and flat["FILTER"] == "ir_1"
    assert "EXPTIME" not in flat and "CCD-TEMP" not in flat  # only what the name carries
    bias = fits.getheader(config.CALIBRATION_DIR / "Draco" / "biases" / BIAS)
    assert bias["IMAGETYP"] == "Master Bias"
    # every downstream reader sees a normal calibration frame
    assert ingest.frame_info(str(dest))["imagetyp"] == "dark"
    assert not list(dest.parent.glob("*.part"))

    # the source is byte-for-byte what it was
    assert (_sha(src_dark), src_dark.stat().st_mtime_ns) == before
    assert "IMAGETYP" not in fits.getheader(src_dark)

    # idempotent: a rescan offers nothing, a re-apply skips (no `_1` twin)
    assert [o for o in ingest.scan_directory_plan(str(src)) if o.kind.startswith("cal-")] == []
    res2 = ingest.apply_ops(ops)
    assert res2["skipped"] == len(ops) and res2["moved"] == 0
    assert sorted(p.name for p in dest.parent.iterdir()) == [DARK_13]


def test_a_master_that_describes_itself_is_not_stamped(tmp_path, monkeypatch):
    """A production unit writing real headers: the shim stays out of the way."""
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "Veil_nebula"
    _headerless_master(src / "CALI_FRAME" / "dark" / "cam_0" / DARK_13, imagetyp="Master Dark")
    _draco_session(src, "Draco_RAW_TELE_Unknown_EXP_300_GAIN_60_2026-09-19-21-59-48-480")
    ops = [o for o in ingest.scan_directory_plan(str(src)) if o.kind == "cal-dark"]
    assert len(ops) == 1 and ops[0].stamp is None
    src_dark = src / "CALI_FRAME" / "dark" / "cam_0" / DARK_13
    ingest.apply_ops(ops)
    dest = config.CALIBRATION_DIR / "Draco" / "darks" / DARK_13
    assert _sha(dest) == _sha(src_dark)                     # a plain byte copy
    assert "M110STMP" not in fits.getheader(dest)


# ── a store's own library, and another store's ────────────────────────────────

def test_foreign_store_calibration_dir_imports_as_itself(tmp_path, monkeypatch):
    """A backup / second machine's ``Calibration/DWARF 3/darks/`` must land in
    this store's library — never as a capture target named ``DWARF 3``."""
    seed_root(tmp_path, monkeypatch)
    other = tmp_path / "other-store"
    _headerless_master(other / "Calibration" / "DWARF 3" / "darks" / DARK_13,
                       imagetyp="Master Dark")
    ops = ingest.scan_directory_plan(str(other))
    assert len(ops) == 1
    op = ops[0]
    assert op.kind == "cal-dark" and op.layout == "calibration"
    assert op.dest_rel == f"Calibration/DWARF 3/darks/{DARK_13}"
    assert op.new_object is False and op.stamp is None
    ingest.apply_ops(ops)
    assert not (config.IMAGES_DIR / "DWARF 3").exists()


def test_own_calibration_library_is_never_reimported(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    mine = config.CALIBRATION_DIR / "Draco" / "darks" / DARK_13
    _headerless_master(mine, imagetyp="Master Dark")
    assert ingest._in_own_store(mine.parent)
    assert ingest.scan_directory_plan(str(config.DATA_ROOT)) == [] or all(
        not o.src.startswith(str(config.CALIBRATION_DIR))
        for o in ingest.scan_directory_plan(str(config.DATA_ROOT)))


def test_device_name_from_a_hostile_header_stays_one_segment(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    src = tmp_path / "Veil_nebula"
    _cali_frame(src, darks=(DARK_13,), flats=(), biases=())
    d = _draco_session(src, "Draco_RAW_TELE_Unknown_EXP_300_GAIN_60_2026-09-19-21-59-48-480")
    for f in d.glob("*.fits"):
        with fits.open(f, mode="update") as h:
            h[0].header["TELESCOP"] = "../../evil/Draco"
    ops = [o for o in ingest.scan_directory_plan(str(src)) if o.kind == "cal-dark"]
    assert len(ops) == 1
    rel = Path(ops[0].dest_rel)
    assert rel.parts[0] == "Calibration" and ".." not in rel.parts
    assert "/" not in rel.parts[1] and rel.parts[2] == "darks"
    Path(ops[0].dest).resolve().relative_to(config.DATA_ROOT.resolve())   # contained
