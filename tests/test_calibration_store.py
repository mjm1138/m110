"""Importing a device-level calibration library that is already store-shaped
(``Calibration/<device>/{darks,flats,biases}/`` from a backup or a second
machine), and never re-importing this store's own. Temp fixtures only."""
from pathlib import Path

import numpy as np
from astropy.io import fits

from m110 import calibration, config, ingest
from tests._helpers import seed_root

DARK = "MasterDark_5_20.0s_13.9C_20261015-215239.fit"


def _master(path: Path, imagetyp: str | None = "Master Dark", **cards):
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.full((2, 2), 64, dtype="uint16"))
    if imagetyp:
        h.header["IMAGETYP"] = imagetyp
    h.header["EXPTIME"] = 20.0
    for k, v in cards.items():
        h.header[k] = v
    h.writeto(path)
    return path


def test_foreign_store_calibration_dir_imports_as_itself(tmp_path, monkeypatch):
    """A backup / second machine's ``Calibration/DWARF 3/darks/`` must land in
    this store's library — never as a capture target named ``DWARF 3``."""
    seed_root(tmp_path, monkeypatch)
    other = tmp_path / "other-store"
    _master(other / "Calibration" / "DWARF 3" / "darks" / DARK)
    ops = ingest.scan_directory_plan(str(other))
    assert len(ops) == 1
    op = ops[0]
    assert op.kind == "cal-dark" and op.layout == "calibration"
    assert op.dest_rel == f"Calibration/DWARF 3/darks/{DARK}"
    assert op.object == "DWARF 3" and op.new_object is False
    assert ingest.scan_summary(ops)["objects"] == 0       # a device, not a target
    ingest.apply_ops(ops)
    assert (config.CALIBRATION_DIR / "DWARF 3" / "darks" / DARK).is_file()
    assert not (config.IMAGES_DIR / "DWARF 3").exists()
    # an identical second import is a no-op
    assert ingest.scan_directory_plan(str(other)) == []


def test_own_calibration_library_is_never_reimported(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    mine = _master(config.CALIBRATION_DIR / "S50_15e7e390" / "darks" / DARK)
    assert ingest._in_own_store(mine.parent)
    assert all(not o.src.startswith(str(config.CALIBRATION_DIR))
               for o in ingest.scan_directory_plan(str(config.DATA_ROOT)))


def test_a_hostile_device_folder_stays_one_segment_on_read(tmp_path, monkeypatch):
    """The library reader sanitizes the device name exactly like the writer, so a
    TELESCOP of ``../x`` reads ``Calibration/x``, never a folder above it."""
    seed_root(tmp_path, monkeypatch)
    _master(config.CALIBRATION_DIR / "x" / "darks" / DARK)          # what _safe_segment yields
    _master(config.DATA_ROOT / "x" / "darks" / "outside.fit")       # what a raw join reaches
    names = [m.path.name for m in calibration.library("../x").get("darks", [])]
    assert names == [DARK]
