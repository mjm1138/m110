"""Session scan — mount mode from the reported EQMODE header, not a date guess.

`mount_mode` used to be a hardcoded date heuristic (this store's Seestar switchover)
that would mislabel any other user or device. Both the Seestar and the Dwarf 3 write
an `EQMODE` card (int 0/1, "Equatorial mode"), so the scan now reads that and only
falls back to the date rule when it's absent.
"""
from __future__ import annotations

import numpy as np
from astropy.io import fits

from m110 import config, scan_sessions
from ._helpers import seed_root


def _write_sub(path, eqmode):
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    if eqmode is not None:
        hdu.header["EQMODE"] = (eqmode, "Equatorial mode")
    hdu.writeto(path, overwrite=True)


def test_read_eqmode_coercions(tmp_path):
    _write_sub(tmp_path / "eq1.fit", 1)
    _write_sub(tmp_path / "eq0.fit", 0)
    _write_sub(tmp_path / "none.fit", None)          # card absent
    (tmp_path / "stub.fit").write_text("x")           # not a real FITS
    assert scan_sessions._read_eqmode(tmp_path / "eq1.fit") is True
    assert scan_sessions._read_eqmode(tmp_path / "eq0.fit") is False
    assert scan_sessions._read_eqmode(tmp_path / "none.fit") is None
    assert scan_sessions._read_eqmode(tmp_path / "stub.fit") is None


def test_scan_mount_mode_prefers_eqmode_over_date(tmp_path, monkeypatch):
    """A sub dated after EQ_FROM (date heuristic → EQ) but flagged EQMODE=0 in the
    header must be reported as Alt-Az — the header wins over the date guess."""
    seed_root(tmp_path, monkeypatch)
    _write_sub(config.IMAGES_DIR / "M63" / "lights"
               / "Light_M63_30.0s_LP_20260529-010101.fit", 0)   # Alt-Az in header
    rows = [r for r in scan_sessions.scan() if r["object_dir"] == "M63"]
    assert rows and rows[0]["mount_mode"] == "Alt-Az"


def test_scan_mount_mode_reads_eq_from_header(tmp_path, monkeypatch):
    """A Dwarf-style sub (header-only key path) flagged EQMODE=1 reports EQ."""
    seed_root(tmp_path, monkeypatch)
    # A non-Seestar filename forces the header path in _session_key too; EQMODE=1.
    hdu_dir = config.IMAGES_DIR / "M86" / "lights"
    hdu_dir.mkdir(parents=True)
    hdu = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    hdu.header["EQMODE"] = (1, "Equatorial mode")
    hdu.header["DATE-OBS"] = "2026-03-23T02:08:52"
    hdu.header["EXPTIME"] = 30.0
    hdu.header["FILTER"] = "Astro"
    hdu.writeto(hdu_dir / "M 86_30s60_Astro_20260323-020852621_12C.fits")
    rows = [r for r in scan_sessions.scan() if r["object_dir"] == "M86"]
    assert rows and rows[0]["mount_mode"] == "EQ"


def test_scan_mount_mode_falls_back_to_date_without_eqmode(tmp_path, monkeypatch):
    """No readable EQMODE (a non-FITS stub) → the legacy date heuristic still applies:
    2026-05-29 is after EQ_FROM, so EQ."""
    seed_root(tmp_path, monkeypatch)
    lights = config.IMAGES_DIR / "M64" / "lights"
    lights.mkdir(parents=True)
    (lights / "Light_M64_30.0s_LP_20260529-010101.fit").write_text("x")
    rows = [r for r in scan_sessions.scan() if r["object_dir"] == "M64"]
    assert rows and rows[0]["mount_mode"] == "EQ"
