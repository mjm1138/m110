"""In-store rendering + sessions for DwarfLab Dwarf 3 `.fits` files.

`test_ingest_dwarf` covers the *ingest* classification. This covers what happens
*after* the files are in the store: the `.fits` extension + a Duo-Band narrowband
sub set produce a session, and the in-app RGB `stacked-16_*.fits` stack renders a
hero + gallery thumbnails (the `.fit`-vs-`.fits` and 3-plane-FITS render paths —
the corpus's M42 fixture, pinned as a regression).
"""
import json
from pathlib import Path

import numpy as np
from astropy.io import fits

from m110 import config, scan_sessions, refresh
from tests._helpers import seed_root


def _dwarf_fits(path, obj, exp, filt, date_obs, ra=83.82, dec=-5.39, rgb=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1)
    data = (rng.random((3, 16, 16), dtype="float32") if rgb
            else rng.random((16, 16), dtype="float32"))
    h = fits.PrimaryHDU(data)
    hdr = h.header
    hdr["OBJECT"] = obj
    hdr["FILTER"] = filt
    hdr["EXPTIME"] = exp
    hdr["DATE-OBS"] = date_obs
    hdr["TELESCOP"] = "DWARF 3"
    hdr["RA"] = ra
    hdr["DEC"] = dec
    h.writeto(path, overwrite=True)


def _seed_dwarf_m42():
    lights = config.lights_dir("M42")
    for i in range(4):
        _dwarf_fits(lights / f"M42_15s60_Duo-Band_20260130-19285{i}_0C.fits",
                    "M 42", 15, "Duo-Band", f"2026-01-30T19:28:5{i}.0")
    stacks = config.seestar_stacks_dir("M42")
    _dwarf_fits(stacks / "stacked-16_M42_15s60_Duo-Band_20260130-193136.fits",
                "M 42", 60, "Duo-Band", "2026-01-30T19:31:36.0", rgb=True)


def test_dwarf_fits_lights_produce_a_session(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _seed_dwarf_m42()
    rows = [r for r in scan_sessions.scan() if r["object_dir"] == "M42"]
    assert len(rows) == 1
    r = rows[0]
    assert r["frames"] == 4
    assert r["exposure_s"] == 15
    assert r["filter"] == "DUO-BAND"          # header FILTER, uppercased


def test_dwarf_fits_stack_renders_hero_and_gallery(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _seed_dwarf_m42()
    refresh.run_refresh()                     # add_captured → sessions → derived → images
    hero = config.HERO_DIR / "m42.jpg"
    assert hero.exists() and hero.stat().st_size > 0, "no hero from the .fits stack"
    imgs = json.loads((config.DERIVED_DIR / "images.json").read_text())
    m42 = imgs.get("m42") or []
    assert m42, "no gallery images for the Dwarf-captured M42"
    assert any(i["name"].startswith("stacked-16_") and i["name"].endswith(".fits")
               for i in m42), "the .fits stack is not in the gallery"
    assert all(Path(i["thumb"]).suffix == ".jpg" for i in m42 if i.get("thumb"))
