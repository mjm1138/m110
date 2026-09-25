"""Matching a target's lights to the device-level calibration library
(m110/calibration.py). Header-only: the masters here carry the cards the
ingest shim stamps (IMAGETYP/EXPTIME/GAIN/XBINNING/CCD-TEMP/NCOMBINE/FILTER),
the lights carry what a Draco sub writes. Temp fixtures only.
"""
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from m110 import calibration, config
from tests._helpers import seed_root


def _master(path: Path, imagetyp: str | None, **cards):
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    if imagetyp:
        h.header["IMAGETYP"] = imagetyp
    for k, v in cards.items():
        h.header[k.replace("_", "-")] = v
    h.writeto(path)
    return path


def _light(path: Path, *, exptime=300.0, gain=60, binning=1, temp=13, filt="Duo-Band",
           telescop="Draco", temp_card="DET-TEMP"):
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    h.header["EXPTIME"] = exptime
    h.header["GAIN"] = gain
    h.header["XBINNING"] = binning
    h.header["YBINNING"] = binning
    h.header[temp_card] = temp
    h.header["FILTER"] = filt
    h.header["TELESCOP"] = telescop
    h.header["OBJECT"] = "NGC 6992"
    h.header["DATE-OBS"] = "2026-09-19T22:05:35.997"
    h.writeto(path)
    return path


def _dark(dev, name, temp, n, exptime=300.0, gain=60, binning=1):
    return _master(config.calibration_dir(dev, "darks") / name, "Master Dark",
                   EXPTIME=exptime, GAIN=gain, XBINNING=binning, YBINNING=binning,
                   CCD_TEMP=temp, NCOMBINE=n)


FACTS = {"exptime": 300.0, "gain": 60, "binning": 1, "temp_c": 13.0, "filter": "Duo-Band"}


# ── reading the library ───────────────────────────────────────────────────────

def test_library_reads_stamped_headers_and_skips_what_is_not_a_master(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    d = config.calibration_dir("Draco", "darks")
    _dark("Draco", "d13.fits", 13, 10)
    _master(d / "claims_flat.fits", "Master Flat", XBINNING=1)     # wrong type → skipped
    _master(d / "untyped.fits", None, EXPTIME=300.0, GAIN=60, XBINNING=1)  # folder trusted
    _master(d / "._d13.fits", "Master Dark")                          # AppleDouble → skipped
    (d / "notes.txt").write_text("x")
    lib = calibration.library("Draco")
    assert set(lib) == {"darks"}
    names = sorted(m.path.name for m in lib["darks"])
    assert names == ["d13.fits", "untyped.fits"]
    m = next(m for m in lib["darks"] if m.path.name == "d13.fits")
    assert (m.tier, m.exptime, m.gain, m.binning, m.temp_c, m.ncombine) == \
           ("darks", 300.0, 60, 1, 13.0, 10)
    assert calibration.library("Nobody") == {}


def test_frame_facts_falls_back_to_det_temp_and_exposure(tmp_path):
    p = _light(tmp_path / "a.fits", temp=11, temp_card="DET-TEMP")
    assert calibration.frame_facts(p)["temp_c"] == 11.0
    q = _light(tmp_path / "b.fits", temp=9, temp_card="CCD-TEMP")
    assert calibration.frame_facts(q)["temp_c"] == 9.0
    h = fits.PrimaryHDU(np.zeros((2, 2)))
    h.header["EXPOSURE"] = 20.0
    h.writeto(tmp_path / "c.fits")
    assert calibration.frame_facts(tmp_path / "c.fits")["exptime"] == 20.0
    assert calibration.frame_facts(tmp_path / "missing.fits") is None


# ── dark matching ─────────────────────────────────────────────────────────────

def test_dark_exact_settings_then_nearest_temperature(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _dark("Draco", "d12.fits", 12, 11)
    _dark("Draco", "d13.fits", 13, 10)
    _dark("Draco", "d26.fits", 26, 1)
    _dark("Draco", "d10s.fits", 13, 5, exptime=10.0)         # wrong exposure
    _dark("Draco", "dg0.fits", 13, 5, gain=0)                 # wrong gain
    _dark("Draco", "db2.fits", 13, 5, binning=2)              # wrong binning
    assert calibration.match_masters(FACTS, "Draco").darks.name == "d13.fits"
    assert calibration.match_masters(dict(FACTS, temp_c=12.4), "Draco").darks.name == "d12.fits"
    assert calibration.match_masters(dict(FACTS, temp_c=24.0), "Draco").darks.name == "d26.fits"
    # a tie on temperature → the master averaged from more frames
    assert calibration.match_masters(dict(FACTS, temp_c=12.5), "Draco").darks.name == "d12.fits"
    # the 10 s dark serves 10 s lights only at ITS gain; nothing at 20 s at all
    assert calibration.match_masters(dict(FACTS, exptime=10.0), "Draco").darks.name == "d10s.fits"
    res = calibration.match_masters(dict(FACTS, exptime=20.0), "Draco")
    assert res.darks is None
    assert any("no master dark for 20 s, gain 60, bin 1" in n for n in res.notes)
    res = calibration.match_masters(dict(FACTS, gain=80), "Draco")
    assert res.darks is None and any("gain 80" in n for n in res.notes)


def test_a_wide_temperature_gap_is_noted_not_hidden(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _dark("Draco", "d26.fits", 26, 1)
    res = calibration.match_masters(FACTS, "Draco")
    assert res.darks.name == "d26.fits"
    assert any("13 °C warmer" in n for n in res.notes)
    res = calibration.match_masters(dict(FACTS, temp_c=None), "Draco")
    assert res.darks.name == "d26.fits"
    assert any("no sensor temperature" in n for n in res.notes)


# ── bias + flat matching ──────────────────────────────────────────────────────

def test_bias_prefers_same_gain_else_sole_candidate_with_a_note(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    b = config.calibration_dir("Draco", "biases")
    _master(b / "bias_g2.fits", "Master Bias", GAIN=2, XBINNING=1)
    res = calibration.match_masters(FACTS, "Draco")
    assert res.biases.name == "bias_g2.fits"
    assert any("no master bias at gain 60" in n for n in res.notes)
    _master(b / "bias_g60.fits", "Master Bias", GAIN=60, XBINNING=1)
    res = calibration.match_masters(FACTS, "Draco")
    assert res.biases.name == "bias_g60.fits"
    assert not any("gain 60" in n and "no master bias" in n for n in res.notes)
    assert calibration.match_masters(dict(FACTS, binning=2), "Draco").biases is None


def test_flats_need_an_unambiguous_filter_match(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    f = config.calibration_dir("Draco", "flats")
    _master(f / "flat_ir_1.fits", "Master Flat", XBINNING=1, FILTER="ir_1")
    _master(f / "flat_ir_2.fits", "Master Flat", XBINNING=1, FILTER="ir_2")
    # the ir_N ↔ name map for the Draco is unverified → no flat, and a note that says so
    res = calibration.match_masters(FACTS, "Draco")
    assert res.flats is None
    assert any("filter-index map is unverified" in n for n in res.notes)
    # once the map is known, the one matching flat is chosen
    monkeypatch.setitem(calibration.FILTER_INDEX, "draco", {"ir_1": "Duo-Band"})
    assert calibration.match_masters(FACTS, "Draco").flats.name == "flat_ir_1.fits"
    # a flat named for the filter matches directly, case-insensitively
    _master(f / "flat_duo.fits", "Master Flat", XBINNING=1, FILTER="DUO-BAND")
    res = calibration.match_masters(FACTS, "Draco")
    assert res.flats is None and any("2 master flats could apply" in n for n in res.notes)
    # a flat with no FILTER card at all serves any filter
    assert calibration.filter_matches("Duo-Band", None, "Draco")
    assert not calibration.filter_matches(None, "ir_1", "Draco")


def test_an_empty_library_says_so(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    res = calibration.match_masters(FACTS, "Draco")
    assert not res and res.as_dict() == {}
    assert res.notes == ["no calibration library for Draco (Calibration/Draco/ is empty)"]


# ── from a set of lights ──────────────────────────────────────────────────────

def test_facts_from_frames_take_the_dominant_group_and_flag_mixing():
    frames = ([{"exptime": 300.0, "gain": 60, "binning": 1, "temp_c": t,
                "filter": "Duo-Band", "telescop": "Draco"} for t in (11, 13, 15, 12)]
              + [{"exptime": 10.0, "gain": 80, "binning": 1, "temp_c": 30,
                  "filter": "VIS", "telescop": None}])
    f = calibration.facts_from_frames(frames)
    assert (f["exptime"], f["gain"], f["binning"]) == (300.0, 60, 1)
    assert f["temp_c"] == 12.5 and f["filter"] == "Duo-Band" and f["telescop"] == "Draco"
    assert f["mixed"] and f["groups"] == {"300.0s/g60/b1": 4, "10.0s/g80/b1": 1}
    assert not calibration.facts_from_frames(frames[:4])["mixed"]
    assert calibration.facts_from_frames([])["exptime"] is None


def test_match_for_target_reads_the_lights_and_refuses_mixed_settings(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    lights = config.lights_dir("NGC 6992")
    for i, t in enumerate((11, 13, 15)):
        _light(lights / f"Unknown_300s60_Duo-Band_2026091{i}-220535997_{t}C.fits", temp=t)
    (lights / "stacked-16_x.fits").write_text("not a sub")   # product: ignored
    _dark("Draco", "d13.fits", 13, 10)
    _dark("Draco", "d26.fits", 26, 1)
    assert calibration.device_for_target("NGC 6992") == "Draco"
    facts = calibration.target_facts("NGC 6992")
    assert (facts["exptime"], facts["gain"], facts["temp_c"], facts["filter"]) == \
           (300.0, 60, 13.0, "Duo-Band")
    res = calibration.match_for_target("NGC 6992")
    assert res.device == "Draco" and res.darks.name == "d13.fits"
    # a second exposure population → refused, with the way out named
    _light(lights / "Unknown_10s80_Duo-Band_20260919-230000000_13C.fits", exptime=10.0, gain=80)
    _light(lights / "Unknown_10s80_Duo-Band_20260919-230100000_13C.fits", exptime=10.0, gain=80)
    _light(lights / "Unknown_10s80_Duo-Band_20260919-230200000_13C.fits", exptime=10.0, gain=80)
    _light(lights / "Unknown_10s80_Duo-Band_20260919-230300000_13C.fits", exptime=10.0, gain=80)
    res = calibration.match_for_target("NGC 6992")
    assert not res and any("mixed capture settings" in n and "--only-exposure" in n
                           for n in res.notes)


def test_lights_without_a_telescope_cannot_pick_a_library(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    lights = config.lights_dir("M51")
    _light(lights / "Light_M51_20.0s_LP_20260101-000000.fit", telescop="")
    assert calibration.device_for_target("M51") is None
    res = calibration.match_for_target("M51")
    assert not res and any("no TELESCOP" in n for n in res.notes)
    assert calibration.match_for_target("Nothing here") .notes    # missing target: a note, no crash


def test_sampling_reads_a_bounded_number_of_headers(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    lights = config.lights_dir("NGC 6992")
    for i in range(60):
        _light(lights / f"Unknown_300s60_Duo-Band_20260919-22{i:04d}_13C.fits")
    calls = []
    real = calibration.frame_facts
    monkeypatch.setattr(calibration, "frame_facts", lambda p: calls.append(p) or real(p))
    calibration.target_facts("NGC 6992", sample=24)
    assert len(calls) == 24
    assert len(set(calls)) == 24                              # evenly spaced, no repeats
