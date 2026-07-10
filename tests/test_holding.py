"""Holding-area grouping (temp fixtures, never live data).

A held Inbox folder that spans several objects should split into one row per
detected object (FITS OBJECT / nearest by RA·Dec), so each can be triaged and
assigned independently; files with no readable identity stay bundled per folder.
"""
import numpy as np
from astropy.io import fits

from m110 import config, ingest
from tests._helpers import seed_root


def _held_fits(path, obj, ra, dec):
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    if obj is not None:
        h.header["OBJECT"] = obj
    h.header["RA"] = ra
    h.header["DEC"] = dec
    h.writeto(path)


def _rows():
    return ingest.group_ops(ingest.scan_holding())


def test_mixed_folder_splits_by_detected_object(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    d = config.STAGING_DIR / "mixed"
    for i in range(2):
        _held_fits(d / f"m42_{i}.fits", "M 42", 83.82, -5.39)
    for i in range(2):
        _held_fits(d / f"m13_{i}.fits", "M 13", 250.42, 36.46)
    (d / "loose.jpg").write_bytes(b"j")     # no header → unidentifiable, stays bundled

    rows = _rows()
    by_obj = {g.object: g for g in rows}
    assert "M42" in by_obj and by_obj["M42"].frames == 2
    assert "M13" in by_obj and by_obj["M13"].frames == 2
    # the headerless file bundles under the source folder (object not resolved)
    bundled = [g for g in rows if g.object not in ("M42", "M13")]
    assert len(bundled) == 1
    assert bundled[0].frames == 1
    assert bundled[0].ops[0].object == ""      # never falsely tagged
    assert len(rows) == 3


def test_single_object_folder_stays_one_row(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    d = config.STAGING_DIR / "onetarget"
    for i in range(3):
        _held_fits(d / f"m42_{i}.fits", "M 42", 83.82, -5.39)

    rows = _rows()
    assert len(rows) == 1
    assert rows[0].object == "M42"
    assert rows[0].frames == 3


def test_object_detected_by_pointing_when_header_absent(tmp_path, monkeypatch):
    """No OBJECT header, but RA/Dec within tolerance of a catalog object → still
    routed to that object's row (identify-by-pointing)."""
    seed_root(tmp_path, monkeypatch)
    d = config.STAGING_DIR / "bypointing"
    _held_fits(d / "a.fits", None, 83.82, -5.39)    # M42's pointing
    rows = _rows()
    assert len(rows) == 1
    assert rows[0].object == "M42"
