"""Celestron Origin folder ingest (temporary fixtures, never live captures)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from astropy.io import fits

from m110 import config, ingest
from tests._helpers import seed_root


TARGET = "Pacman Nebula - NGC 281"


def _origin_fits(path: Path, imagetyp: str, *, obj: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    hdr = hdu.header
    hdr["CREATOR"] = "Origin 1.5.6240"
    hdr["TELESCOP"] = "RASA6F2"
    hdr["MOUNT"] = "Origin"
    hdr["CAMERA"] = "Origin178-test"
    hdr["IMAGETYP"] = imagetyp
    hdr["OBJECT"] = obj or (TARGET if imagetyp == "LIGHT" else imagetyp)
    hdr["DATE-OBS"] = "2026-09-26T21:01:08"
    hdr["TIMEZONE"] = "-0400"
    hdr["EXPTIME"] = 15.0
    hdr["FILTER"] = "Nebula"
    hdr["BAYERPAT"] = "RGGB"
    hdu.writeto(path)


def _origin_session(src: Path, *, folder: str, include_info: bool = True) -> Path:
    session = src / folder
    _origin_fits(session / "Light0001.fits", "LIGHT")
    _origin_fits(session / "Light0002.fits", "LIGHT")
    _origin_fits(session / "dark0007.fits", "DARK")
    _origin_fits(session / "bias0007.fits", "BIAS")
    _origin_fits(session / "flat.fits", "FLAT")
    (session / "dark0007.json").write_text(json.dumps({"cameraType": "Origin178"}))
    (session / "FinalStackedMaster.tiff").write_bytes(b"small TIFF fixture")
    if include_info:
        (session / "info.json").write_text(json.dumps({
            "StackedInfo": {
                "objectName": TARGET,
                "dateTime": "2026-09-26T21:01:08-04:00",
                "filter": "Nebula",
                "stackedDepth": 2,
            },
        }))
    return session


def _by_kind(ops):
    grouped = {}
    for op in ops:
        grouped.setdefault(op.kind, []).append(op)
    return grouped


def _relative_names(root: Path, ops):
    return {Path(op.dest).relative_to(root).as_posix() for op in ops}


def test_origin_session_routes_stamped_frames_stacks_and_sidecars(tmp_path, monkeypatch):
    """Without Origin routing, reused light names collide and session files hit Inbox."""
    root = seed_root(tmp_path, monkeypatch)
    src = tmp_path / "Origin"
    _origin_session(src, folder="Pacman_Nebula_-_NGC_281_2026-09-26_21-01-08")

    ops = ingest.scan_directory_plan(src)
    by_kind = _by_kind(ops)
    names = _relative_names(root, ops)

    assert {op.layout for op in ops} == {"origin"}
    assert "unassigned" not in by_kind
    assert {
        "Images/NGC 281/lights/Light0001_20260926-210108.fits",
        "Images/NGC 281/lights/Light0002_20260926-210108.fits",
        "Images/NGC 281/darks/dark0007_20260926-210108.fits",
        "Images/NGC 281/biases/bias0007_20260926-210108.fits",
        "Images/NGC 281/flats/flat_20260926-210108.fits",
        "Images/NGC 281/seestar-stacks/20260926-210108_FinalStackedMaster.tiff",
        "Images/NGC 281/seestar-stacks/20260926-210108_info.json",
        "Images/NGC 281/seestar-stacks/20260926-210108_dark0007.json",
    } <= names
    assert all(op.action == "copy" for op in ops)


def test_origin_sessions_with_reused_light_names_import_once_each(tmp_path, monkeypatch):
    """A second Origin session must add its subs, while reimporting one adds none."""
    root = seed_root(tmp_path, monkeypatch)
    src = tmp_path / "Origin"
    _origin_session(src, folder="Pacman_Nebula_-_NGC_281_2026-09-26_21-01-08")
    _origin_session(src, folder="Pacman_Nebula_-_NGC_281_2026-09-29_01-31-17")

    first = ingest.scan_directory_plan(src)
    light_names = {
        Path(op.dest).name for op in first if op.kind == "light"
    }
    assert light_names == {
        "Light0001_20260926-210108.fits",
        "Light0002_20260926-210108.fits",
        "Light0001_20260929-013117.fits",
        "Light0002_20260929-013117.fits",
    }

    result = ingest.apply_ops(first)
    assert result == {"moved": len(first), "skipped": 0, "cancelled": False}
    assert ingest.scan_directory_plan(src) == []
    assert sorted(p.name for p in config.lights_dir(TARGET).iterdir()) == sorted(light_names)


def test_origin_creator_header_recognizes_a_session_without_info_json(tmp_path, monkeypatch):
    """Current Origin FITS headers are a supported fallback when info.json is absent."""
    root = seed_root(tmp_path, monkeypatch)
    src = tmp_path / "Origin"
    _origin_session(
        src,
        folder="Pacman_Nebula_-_NGC_281_2026-09-26_21-01-08",
        include_info=False,
    )

    ops = ingest.scan_directory_plan(src)
    assert ops
    assert {op.layout for op in ops} == {"origin"}
    assert all(op.object == TARGET for op in ops)
    assert "unassigned" not in _by_kind(ops)
