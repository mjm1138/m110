"""DwarfLab Dwarf 3 ingest + sessions (temp fixtures, never live data).

The Dwarf 3 writes header-rich ``.fits`` subs (no IMAGETYP), an in-app
``stacked-16_*.fits`` stack, per-sub previews in a ``Thumbnail/`` dir, and
``stacked.jpg``/aux rasters — all inside ``DWARF_RAW_*`` / ``STARTRAILS_*``
session folders. These tests pin the recognizer + the header-driven session scan.
"""
from pathlib import Path

import numpy as np
from astropy.io import fits

from m110 import config, ingest, scan_sessions
from tests._helpers import seed_root


def _dwarf_sub(path: Path, obj, exp, gain, filt, ra, dec, date_obs,
               camera="TELE", naxis=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    shape = (2, 2) if naxis == 2 else (3, 2, 2)
    h = fits.PrimaryHDU(np.zeros(shape, dtype="uint16"))
    hdr = h.header
    hdr["DATE-OBS"] = date_obs
    hdr["EXPTIME"] = exp
    hdr["GAIN"] = gain
    hdr["FILTER"] = filt
    hdr["CAMERA"] = camera
    hdr["RA"] = ra
    hdr["DEC"] = dec
    hdr["OBJECT"] = obj
    hdr["TELESCOP"] = "DWARF 3"
    hdr["INSTRUME"] = "DWARF 3"
    h.writeto(path)


def _dwarf_session(src, folder, obj, exp=15, gain=60, filt="Duo-Band",
                   ra=83.82, dec=-5.39, n=3, camera="TELE"):
    """A realistic on-device session dir: raw subs + in-app stack + stacked.jpg +
    a Thumbnail/ dir + aux rasters. Returns the session dir."""
    d = src / folder
    d.mkdir(parents=True)
    stamp = "20260130-19285"
    for i in range(n):
        _dwarf_sub(d / f"{obj}_{exp}s{gain}_{filt}_{stamp}{i}092_0C.fits",
                   obj, exp, gain, filt, ra, dec, f"2026-01-30T19:28:5{i}.092",
                   camera=camera)
    # in-app stack (RGB) + its preview rasters
    _dwarf_sub(d / f"stacked-16_{obj}_{exp}s{gain}_{filt}_20260130-192840065.fits",
               obj, exp * n, gain, filt, ra, dec, "2026-01-30T19:31:36.867",
               camera=camera, naxis=3)
    (d / f"stacked-16_{obj}_{exp}s{gain}_{filt}_20260130-192840065.png").write_bytes(b"png")
    (d / "stacked.jpg").write_bytes(b"jpg")
    (d / "stacked_thumbnail.jpg").write_bytes(b"thumb")
    (d / "img_reference.png").write_bytes(b"ref")
    (d / "shotsInfo.json").write_text("{}")
    # per-sub previews live in a Thumbnail/ sidecar dir
    thumb = d / "Thumbnail"
    thumb.mkdir()
    for i in range(n):
        (thumb / f"{obj}_{exp}s{gain}_{filt}_{stamp}{i}092_0C.jpg").write_bytes(b"t")
    return d


def _by_kind(ops):
    out = {}
    for op in ops:
        out.setdefault(op.kind, []).append(op)
    return out


def test_fits_extension_recognized_as_light():
    assert config.is_light_frame("M 42_15s60_Duo-Band_x_0C.fits")
    assert config.is_light_frame("Moon_0.0025s0_VIS_x_17C.fits")
    assert not config.is_light_frame("stacked-16_M 42.fits")   # a product, not a sub


def test_dwarf_session_routes_lights_stack_and_skips_previews(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    src = tmp_path / "external"
    _dwarf_session(src, "DWARF_RAW_TELE_M 42_EXP_15_GAIN_60_2026-01-30-19-27-59",
                   "M 42", n=3)

    ops = ingest.scan_directory_plan(str(src))
    by_kind = _by_kind(ops)
    assert all(op.action == "copy" for op in ops)
    assert all(op.layout == "dwarf" for op in ops)

    # 3 raw subs → M42/lights (folded from "M 42")
    lights = by_kind["light"]
    assert len(lights) == 3
    assert all("Images/M42/lights/" in o.dest_rel for o in lights)

    # stacked-16 fits + its .png + stacked.jpg → the object's stack tier
    stack_names = sorted(Path(o.src).name for o in by_kind["stack"])
    assert any(n.startswith("stacked-16_") and n.endswith(".fits") for n in stack_names)
    assert "stacked.jpg" in stack_names
    assert any(n.startswith("stacked-16_") and n.endswith(".png") for n in stack_names)
    assert all("Images/M42/seestar-stacks/" in o.dest_rel for o in by_kind["stack"])

    # per-sub Thumbnail/ + aux rasters (stacked_thumbnail, img_*) are NOT held
    assert "unassigned" not in by_kind
    held = [Path(o.src).name for o in ops if o.kind == "unassigned"]
    assert held == []


def test_dwarf_startrails_to_media(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    src = tmp_path / "external"
    d = src / "STARTRAILS_DWARF_RAW_WIDE_EXP_10_GAIN_0_2026-02-15-22-20-55"
    d.mkdir(parents=True)
    for i in range(3):
        _dwarf_sub(d / f"startrails_10s0_2026021{i}-222124795_24C.fits",
                   "", 10, 0, "", 0.0, 0.0, f"2026-02-1{i}T22:21:24.791",
                   camera="WIDE")
    (d / "startrails_classic_20260215-222055955.mp4").write_bytes(b"mp4")
    (d / "stacked.jpg").write_bytes(b"jpg")
    (d / "stacked_thumbnail.jpg").write_bytes(b"t")

    ops = ingest.scan_directory_plan(str(src))
    by_kind = _by_kind(ops)
    # only the mp4 + composite jpg are imported, as Media; raw subs ignored
    assert set(by_kind) == {"media"}
    dests = sorted(o.dest_rel for o in by_kind["media"])
    assert dests == [
        "Media/Startrails_photo/stacked.jpg",
        "Media/Startrails_video/startrails_classic_20260215-222055955.mp4",
    ]


def test_dwarf_unknown_object_goes_to_holding(tmp_path, monkeypatch):
    """OBJECT='Unknown' is a device placeholder → the subs land in the holding
    area (for identify-by-pointing), not a literal "Unknown" target."""
    root = seed_root(tmp_path, monkeypatch)
    src = tmp_path / "external"
    d = src / "DWARF_RAW_WIDE_Unknown_EXP_10_GAIN_0_2026-06-11-23-47-45"
    d.mkdir(parents=True)
    for i in range(3):
        _dwarf_sub(d / f"Unknown_10s0_2026061{i}-001323089_30C.fits",
                   "Unknown", 10, 0, "", 271.47, -14.05,
                   f"2026-06-1{i}T00:13:23.084", camera="WIDE")

    ops = ingest.scan_directory_plan(str(src))
    by_kind = _by_kind(ops)
    assert set(by_kind) == {"unassigned"}
    assert all(o.dest_rel.startswith("Inbox/") for o in by_kind["unassigned"])
    assert not (config.IMAGES_DIR / "Unknown").exists()


def test_scan_sessions_from_dwarf_headers(tmp_path, monkeypatch):
    """After apply, the header-driven session scan reads DATE-OBS/EXPTIME/FILTER
    off the Dwarf .fits subs and produces a correct session row."""
    root = seed_root(tmp_path, monkeypatch)
    src = tmp_path / "external"
    _dwarf_session(src, "DWARF_RAW_TELE_M 42_EXP_15_GAIN_60_2026-01-30-19-27-59",
                   "M 42", exp=15, filt="Duo-Band", n=4)
    ingest.apply_ops(ingest.scan_directory_plan(str(src)))

    rows = scan_sessions.scan()
    m42 = [r for r in rows if r["object_dir"] == "M42"]
    assert len(m42) == 1
    r = m42[0]
    assert r["date"] == "2026-01-30"
    assert r["frames"] == 4
    assert r["exposure_s"] == 15
    assert r["filter"] == "DUO-BAND"
    assert r["integration_min"] == round(4 * 15 / 60.0, 2)
