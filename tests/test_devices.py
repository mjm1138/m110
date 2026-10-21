"""Telescope identity from the FITS ``TELESCOP`` card (m110.devices)."""
from m110 import devices
from m110.planning_config import DEVICE_PRESETS


def test_folder_name_is_the_trimmed_header_string():
    assert devices.folder_name("Draco") == "Draco"
    assert devices.folder_name("DWARF 3 ") == "DWARF 3"     # real names, verbatim
    assert devices.folder_name("") == "unknown"
    assert devices.folder_name(None) == "unknown"


def test_preset_key_maps_known_devices_and_every_key_exists():
    cases = {
        "DWARF 3": "dwarf_3", "Dwarf3": "dwarf_3", "DWARF III": "dwarf_3",
        "DWARF Mini": "dwarf_mini",
        "S50_15e7e390": "seestar_s50", "Seestar S50": "seestar_s50",
        "Seestar S30": "seestar_s30", "S30 Pro": "seestar_s30_pro",
        "S30_pro_abc": "seestar_s30_pro",
    }
    for tel, key in cases.items():
        assert devices.preset_key(tel) == key, tel
        assert key in DEVICE_PRESETS
    assert devices.preset_key("ASIAIR") is None
    assert devices.preset_key("") is None
    assert devices.preset_key(None) is None


# ── the registry (devices.toml) and per-device rollups ────────────────────────
import numpy as np
import pytest
from astropy.io import fits

from m110 import build_derived, calibration, config, scan_sessions
from tests._helpers import seed_root


def test_registry_round_trip_and_clearing(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    assert devices.load_registry() == {}
    devices.save_device("S50_15e7e390", nickname="Backyard S50")
    devices.save_device('Odd "name"', nickname="Quoted", retired=True, preset="seestar_s30")
    reg = devices.load_registry()
    assert reg["S50_15e7e390"] == {"nickname": "Backyard S50"}
    assert reg['Odd "name"'] == {"nickname": "Quoted", "retired": True, "preset": "seestar_s30"}
    assert devices.label("S50_15e7e390", reg) == "Backyard S50"
    assert devices.label("S50_aaaa", reg) == "ZWO Seestar S50 · aaaa"
    assert devices.label("unknown", reg) == "Unknown telescope"
    # a user-chosen model for an unrecognised TELESCOP
    devices.save_device("Mystery", preset="dwarf_3")
    assert devices.label("Mystery") == "DwarfLab Dwarf 3 · Mystery"
    assert devices.effective_preset("Mystery") == "dwarf_3"
    # clearing every field drops the entry
    devices.save_device("S50_15e7e390", nickname="")
    assert "S50_15e7e390" not in devices.load_registry()
    with pytest.raises(ValueError):
        devices.save_device("x", colour="red")


def test_a_malformed_registry_reads_as_empty(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    config.DEVICES_TOML.write_text("[devices\nnot toml", encoding="utf-8")
    assert devices.load_registry() == {}
    config.DEVICES_TOML.write_text('[devices."A"]\nnickname = 3\nretired = "yes"\n',
                                   encoding="utf-8")
    assert devices.load_registry() == {"A": {}}           # wrong types ignored


def _sub(path, tel, temp=12.0, when="20261015-210000"):
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    for k, v in {"TELESCOP": tel, "GAIN": 80, "XBINNING": 1, "CCD-TEMP": temp,
                 "EXPTIME": 20.0, "FILTER": "IRCUT", "DATE-OBS": "2026-10-16T03:00:00"}.items():
        h.header[k] = v
    h.writeto(path)


def test_two_scopes_on_one_target_and_night_are_two_sessions(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    lights = config.lights_dir("M 51")
    for i in range(3):
        _sub(lights / f"Light_M 51_20.0s_IRCUT_20261015-21000{i}.fit", "S50_aaaa0001")
    for i in range(2):
        _sub(lights / f"Light_M 51_20.0s_IRCUT_20261015-22000{i}.fit", "S30_bbbb0002")
    rows = sorted(scan_sessions.scan(), key=lambda r: r["device"])
    assert [(r["device"], r["frames"]) for r in rows] == [("S30_bbbb0002", 2),
                                                          ("S50_aaaa0001", 3)]
    assert {r["date"] for r in rows} == {"2026-10-15"}


def test_a_one_scope_folder_reads_only_its_sample(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    lights = config.lights_dir("M 51")
    for i in range(80):
        _sub(lights / f"Light_M 51_20.0s_IRCUT_20261015-2{i:05d}.fit", "S50_aaaa0001")
    reads = []
    real = scan_sessions._read_capture_facts
    monkeypatch.setattr(scan_sessions, "_read_capture_facts",
                        lambda p: reads.append(p) or real(p))
    (row,) = scan_sessions.scan()
    assert row["device"] == "S50_aaaa0001" and row["frames"] == 80
    assert len(set(reads)) <= scan_sessions._SAMPLE_BETWEEN + 2


def test_totals_and_the_rollup_split_by_device(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    lights = config.lights_dir("M 51")
    for i in range(3):
        _sub(lights / f"Light_M 51_20.0s_IRCUT_20261015-21000{i}.fit", "S50_aaaa0001")
    for i in range(2):
        _sub(lights / f"Light_M 51_20.0s_IRCUT_20261016-22000{i}.fit", "S30_bbbb0002")
    _sub(config.lights_dir("M 13") / "Light_M 13_20.0s_IRCUT_20261017-220000.fit", None)
    devices.save_device("S30_bbbb0002", nickname="Travel scope")
    rows = scan_sessions.scan()
    scan_sessions.write_jsonl(rows)
    build_derived.main()
    from m110 import derived
    totals = derived.load_totals()
    assert totals["by_slug"]["m51"]["by_device"] == {
        "S30_bbbb0002": {"frames": 2, "integration_min": 0.67, "session_count": 1},
        "S50_aaaa0001": {"frames": 3, "integration_min": 1.0, "session_count": 1}}
    devs = {d["device"]: d for d in derived.load_devices()}
    assert set(devs) == {"S50_aaaa0001", "S30_bbbb0002", "unknown"}
    s30 = devs["S30_bbbb0002"]
    assert s30["label"] == "Travel scope" and s30["model"] == "ZWO Seestar S30"
    assert s30["serial"] == "bbbb0002" and s30["totals"]["integration_min"] == 0.67
    assert [o["slug"] for o in s30["objects"]] == ["m51"]
    assert devs["unknown"]["label"] == "Unknown telescope"
    # most recent capture first
    assert [d["device"] for d in derived.load_devices()][0] == "unknown"


def test_dark_label_reads_like_the_library():
    from datetime import datetime
    assert calibration.dark_label(datetime(2026, 10, 15, 21, 52, 39), 13.9) == \
        "Oct 15 21:52 · 13.9 °C"
    assert calibration.dark_label("2026-10-05T09:05:00", 7.7) == "Oct 5 09:05 · 7.7 °C"
    assert calibration.dark_label(None, None) == "undated · ? °C"
