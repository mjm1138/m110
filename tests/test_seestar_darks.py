"""The Seestar dark library (``<volume>/darklibrary/<exp>s/MasterDark_*``):
archived per device, never applied — Seestar subs are already dark-subtracted on
the device. Temp fixtures only, never live data."""
from pathlib import Path

import numpy as np
from astropy.io import fits

from m110 import calibration, config, devices, ingest, siril
from m110.stacking import Overrides, build_plan
from tests._helpers import (mount_darklibrary, mount_seestar, seed_root,
                            seestar_master_dark)

S50 = "S50_c0ffee00"
LIGHT = {"TELESCOP": S50, "INSTRUME": "Seestar S50", "GAIN": 80, "XBINNING": 1,
         "CCD-TEMP": 14.0}


# ── the guard ─────────────────────────────────────────────────────────────────

def test_only_seestars_have_device_applied_darks():
    assert devices.darks_applied_on_device("S50_15e7e390")
    assert devices.darks_applied_on_device("Seestar S30")
    assert not devices.darks_applied_on_device("DWARF 3")
    assert not devices.darks_applied_on_device(None)


def test_a_seestar_library_dark_is_never_matched(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    seestar_master_dark(config.calibration_dir(S50, "darks") / "MasterDark_5_20.0s_13.9C_20261015-215239.fit", 13.9)
    res = calibration.match_masters(
        {"exptime": 20.0, "gain": 80, "binning": 1, "temp_c": 14.0}, S50)
    assert res.darks is None
    assert res.notes == [calibration.DARKS_ON_DEVICE_NOTE]     # no bias/flat noise


def test_library_reads_stackcnt_as_frames_averaged(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    seestar_master_dark(config.calibration_dir(S50, "darks") / "m.fit", 13.9, stackcnt=5)
    (m,) = calibration.library(S50)["darks"]
    assert (m.exptime, m.gain, m.binning, m.temp_c, m.ncombine) == (20.0, 80, 1, 13.9, 5)


def _seestar_target(name="M 72", n=3):
    lights = config.lights_dir(name)
    lights.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        h = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
        h.header["EXPTIME"] = 20.0
        h.header["FILTER"] = "IRCUT"
        h.header["DATE-OBS"] = f"2026-10-16T01:3{i}:00"
        for k, v in LIGHT.items():
            h.header[k] = v
        h.writeto(lights / f"Light_{name}_20.0s_IRCUT_20261015-19300{i}.fit")
    return name


def test_siril_prep_links_no_library_dark_for_a_seestar(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    target = _seestar_target()
    seestar_master_dark(config.calibration_dir(S50, "darks") / "d.fit", 13.9)
    plan = siril.plan_prep(target)
    assert plan.calib_links == [] and "darks" not in plan.calib_kinds
    assert calibration.DARKS_ON_DEVICE_NOTE in plan.calib_notes


def test_siril_prep_warns_when_a_seestar_object_has_its_own_darks(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    target = _seestar_target()
    seestar_master_dark(config.darks_dir(target) / "my_dark.fit", 14.0)
    plan = siril.plan_prep(target)
    assert plan.calib_source == "target" and "darks" in plan.calib_kinds
    assert any("subtracts twice" in n for n in plan.calib_notes)


def _seestar_job(tmp_path, n=3):
    from tests.test_stacking import _sub
    d = tmp_path / "siril"
    for i in range(n):
        _sub(d / "lights" / f"Light_M 72_20.0s_IRCUT_20261015-19300{i}.fit",
             EXPTIME=20.0, GAIN=80, XBINNING=1, CCD_TEMP=14.0, FILTER="IRCUT",
             TELESCOP=S50, OBJECT="M 72")
    return d


def test_m110_stack_never_takes_a_seestar_library_dark(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CALIBRATION_DIR", tmp_path / "Calibration")
    d = _seestar_job(tmp_path)
    seestar_master_dark(config.calibration_dir(S50, "darks") / "d.fit", 14.0)
    plan = build_plan(d, Overrides(), deep_measure=False)
    assert plan.proposal.get("calibration") is None
    assert any("already dark-subtracted" in w for w in plan.proposal.warnings)


def test_m110_stack_warns_about_a_dark_beside_seestar_lights(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CALIBRATION_DIR", tmp_path / "Calibration")
    d = _seestar_job(tmp_path)
    seestar_master_dark(d / "darks" / "d.fit", 14.0)
    plan = build_plan(d, Overrides(), deep_measure=False)
    assert "darks" in plan.proposal.get("calibration")          # the user's call
    assert any("subtracted twice" in w for w in plan.proposal.warnings)


# ── archiving: ingest ─────────────────────────────────────────────────────────

MASTERS = [("24.9", "20261015-192853"), ("13.9", "20261015-215239")]


def test_device_scan_files_the_dark_library_under_the_telescope(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    myworks, _subs = mount_seestar(tmp_path, monkeypatch, "M 72", extra=LIGHT)
    mount_darklibrary(myworks.parent, MASTERS)
    ops = ingest.scan_seestar_plan()
    cal = sorted((o for o in ops if o.kind == "cal-dark"), key=lambda o: o.dest_rel)
    assert [o.dest_rel for o in cal] == [
        f"Calibration/{S50}/darks/MasterDark_5_20.0s_13.9C_20261015-215239.fit",
        f"Calibration/{S50}/darks/MasterDark_5_20.0s_13.9C_20261015-215239.jpg",
        f"Calibration/{S50}/darks/MasterDark_5_20.0s_24.9C_20261015-192853.fit",
        f"Calibration/{S50}/darks/MasterDark_5_20.0s_24.9C_20261015-192853.jpg"]
    assert all(o.layout == "seestar-darks" and not o.new_object for o in cal)
    assert not any(o.kind == "unassigned" for o in ops)          # _thn.jpg isn't content
    (group,) = [g for g in ingest.group_ops(ops) if g.kind == "cal-dark"]
    assert group.frames == 2 and group.object == S50             # masters, not previews
    assert ingest.scan_summary(ops)["objects"] == 1              # M 72, not the scope

    ingest.apply_ops(ops)
    lib = config.calibration_dir(S50, "darks")
    src = myworks.parent / "darklibrary" / "20s" / "MasterDark_5_20.0s_13.9C_20261015-215239.fit"
    assert (lib / src.name).read_bytes() == src.read_bytes()     # byte-identical, no stamp
    assert not any(o.kind == "cal-dark" for o in ingest.scan_seestar_plan())   # reconnect: no-op


def test_a_volume_without_identifiable_lights_holds_its_darks(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    vol = tmp_path / "Volumes" / "Seestar S50"
    lib = mount_darklibrary(vol, MASTERS[:1])
    ops = ingest.scan_directory_plan(str(vol / "darklibrary"))
    assert ops and all(o.kind == "unassigned" for o in ops)
    (group,) = ingest.group_ops(ops)
    info = ingest.identify_holding(group, coords={}, cat={})
    assert "unidentified telescope" in info["note"]
    assert info["suggested_slug"] is None
    assert lib.is_dir()


def test_only_a_seestar_telescop_names_the_dark_library(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    myworks, _ = mount_seestar(tmp_path, monkeypatch, "M 72",
                               extra=dict(LIGHT, TELESCOP="DWARF 3"))
    mount_darklibrary(myworks.parent, MASTERS[:1])
    ops = ingest.scan_seestar_plan()
    assert not any(o.kind == "cal-dark" for o in ops)


# ── QA: which dark a capture got, and how far off it was (rule v1) ────────────
# Replays the measured S50 pattern of 2026-10-15: M 72 ran 19:30→21:49 on the one
# dark it had (24.9 °C) while the sensor cooled to 14.4 °C; C 6 began 21:53 right
# after a fresh 13.9 °C dark.

LIBRARY = [("24.9", "20261015-192853"), ("13.9", "20261015-215239"),
           ("10.5", "20261015-235231")]


def _library(dev=S50):
    for temp, stamp in LIBRARY:
        seestar_master_dark(config.calibration_dir(dev, "darks")
                            / f"MasterDark_5_20.0s_{temp}C_{stamp}.fit", float(temp))
    return calibration.library(dev)["darks"]


def _lights(target, run, *, tel=S50):
    """`run` = [(device-clock 'YYYYMMDD-HHMMSS', CCD-TEMP), …]."""
    lights = config.lights_dir(target)
    lights.mkdir(parents=True, exist_ok=True)
    for stamp, temp in run:
        h = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
        for k, v in dict(LIGHT, TELESCOP=tel, **{"CCD-TEMP": temp}).items():
            h.header[k] = v
        h.header["EXPTIME"] = 20.0
        h.header["FILTER"] = "IRCUT"
        h.header["DATE-OBS"] = "2026-10-16T01:30:00"
        h.writeto(lights / f"Light_{target}_20.0s_IRCUT_{stamp}.fit")


M72 = [("20261015-193000", 24.8), ("20261015-200600", 21.1), ("20261015-204037", 17.6),
       ("20261015-211400", 15.4), ("20261015-214951", 14.4)]
C6 = [("20261015-215347", 13.6), ("20261015-232400", 11.2)]


def test_runs_split_only_on_a_long_device_clock_gap():
    names = [f"L_{s}.fit" for s in ("20261015-193000", "20261015-200600",
                                    "20261015-214951", "20261016-201500")]
    assert calibration.split_runs(names) == [names[:3], names[3:]]


def test_device_clock_reads_the_filename_stamp_only():
    assert str(calibration.device_clock("MasterDark_5_20.0s_13.9C_20261015-215239.fit")) \
        == "2026-10-15 21:52:39"
    assert str(calibration.device_clock("Light_M 72_20.0s_IRCUT_20261015-193000.fit")) \
        == "2026-10-15 19:30:00"
    assert calibration.device_clock("dark_exp_300_gain_60.fits") is None


def test_rule_v1_picks_the_dark_that_existed_nearest_the_starting_temperature(
        tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    masters = _library()
    clock = calibration.device_clock
    kw = dict(exptime=20.0, gain=80, binning=1, masters=masters)
    # M 72: only the 24.9 °C dark existed; made 67 s before, 0.1 °C off → confirmed
    ad = calibration.applied_dark(clock("x_20261015-193000.fit"), 24.8, **kw)
    assert ad.master.temp_c == 24.9 and ad.link == "confirmed"
    assert round(ad.gap(14.4), 1) == 10.5
    # C 6: the 13.9 °C dark made for it a minute earlier
    ad = calibration.applied_dark(clock("x_20261015-215347.fit"), 13.6, **kw)
    assert ad.master.temp_c == 13.9 and ad.link == "confirmed"
    # the next night: nearest of what exists, but nothing was made for this run
    ad = calibration.applied_dark(clock("x_20261016-221155.fit"), 12.4, **kw)
    assert ad.master.temp_c == 13.9 and ad.link == "inferred"
    # before the library existed → no link at all
    assert calibration.applied_dark(clock("x_20261003-195507.fit"), 25.9, **kw) is None
    # other settings never match
    assert calibration.applied_dark(clock("x_20261016-221155.fit"), 12.4,
                                    **dict(kw, exptime=10.0)) is None


def test_sessions_carry_the_capture_facts_and_the_dark_gap(tmp_path, monkeypatch):
    from m110 import scan_sessions
    seed_root(tmp_path, monkeypatch)
    _library()
    _lights("M 72", M72)
    _lights("C 6", C6)
    rows = {r["object_dir"]: r for r in scan_sessions.scan()}
    m72 = rows["M 72"]
    assert (m72["telescop"], m72["gain"]) == (S50, 80)
    assert (m72["temp_first"], m72["temp_last"], m72["temp_min"], m72["temp_max"]) \
        == (24.8, 14.4, 14.4, 24.8)
    assert m72["dark_ref"] == "MasterDark_5_20.0s_24.9C_20261015-192853.fit"
    assert (m72["dark_temp_c"], m72["dark_gap_c"], m72["dark_link"], m72["dark_rule"]) \
        == (24.9, 10.5, "confirmed", "v2")
    c6 = rows["C 6"]
    assert c6["dark_temp_c"] == 13.9 and c6["dark_gap_c"] == 2.7


def test_session_headers_are_cached_between_scans(tmp_path, monkeypatch):
    from m110 import scan_sessions
    seed_root(tmp_path, monkeypatch)
    _lights("M 72", M72)
    scan_sessions.scan()
    reads = []
    real = scan_sessions._read_capture_facts
    monkeypatch.setattr(scan_sessions, "_read_capture_facts",
                        lambda p: reads.append(p) or real(p))
    scan_sessions.scan()
    assert reads == []


def test_a_non_seestar_session_gets_facts_but_no_dark_link(tmp_path, monkeypatch):
    from m110 import scan_sessions
    seed_root(tmp_path, monkeypatch)
    _library("DWARF 3")
    _lights("M 72", M72, tel="DWARF 3")
    (row,) = scan_sessions.scan()
    assert row["telescop"] == "DWARF 3" and row["temp_max"] == 24.8
    assert row["dark_ref"] is None and row["dark_gap_c"] is None


def test_m110_stack_warns_on_and_can_drop_drifted_frames(tmp_path, monkeypatch):
    from tests.test_stacking import _sub
    seed_root(tmp_path, monkeypatch)
    _library()
    d = tmp_path / "job"
    for stamp, temp in M72:
        _sub(d / "lights" / f"Light_M 72_20.0s_IRCUT_{stamp}.fit", EXPTIME=20.0,
             GAIN=80, XBINNING=1, CCD_TEMP=temp, FILTER="IRCUT", TELESCOP=S50,
             OBJECT="M 72")
    plan = build_plan(d, Overrides(), deep_measure=False)
    (w,) = [w for w in plan.proposal.warnings if "--max-dark-gap" in w]
    assert w.startswith("4 of 5 selected frames") and "worst 10.5 °C" in w
    assert "confirmed" in w
    plan = build_plan(d, Overrides(max_dark_gap=3.0), deep_measure=False)
    assert len(plan.dropped) == 4
    assert not any("--max-dark-gap" in w for w in plan.proposal.warnings)


# ── sensor health + the device rollup ─────────────────────────────────────────

def test_master_stats_count_hot_pixels_robustly(tmp_path):
    rng = np.random.default_rng(0)
    data = rng.normal(476, 10, (64, 64)).astype("uint16")
    data[3, 4] = data[10, 11] = 4000
    p = tmp_path / "m.fit"
    fits.PrimaryHDU(data).writeto(p)
    st = calibration.master_stats(p)
    assert st["hot_px"] == 2 and abs(st["median"] - 476) < 2 and st["shape"] == [64, 64]
    assert 8 < st["sigma"] < 12


def test_device_rollup_links_masters_to_the_captures_they_served(tmp_path, monkeypatch):
    from m110 import build_derived, derived, scan_sessions
    seed_root(tmp_path, monkeypatch)
    _library()
    (config.calibration_dir(S50, "darks")
     / "MasterDark_5_20.0s_24.9C_20261015-192853.jpg").write_bytes(b"\xff\xd8")
    _lights("M 72", M72)
    _lights("C 6", C6)
    scan_sessions.write_jsonl(scan_sessions.scan())
    build_derived.main()
    (dev,) = derived.load_devices()   # (a library-less telescope would sort after it)
    assert dev["device"] == S50 and dev["label"] == "ZWO Seestar S50 · c0ffee00"
    assert dev["darks_applied_on_device"] is True
    by_file = {m["file"]: m for m in dev["masters"]}
    m249 = by_file["MasterDark_5_20.0s_24.9C_20261015-192853.fit"]
    assert m249["captures"] == 1 and m249["made"] == "2026-10-15T19:28:53"
    assert m249["preview"].endswith("192853.jpg") and m249["frames"] == 5
    assert "hot_px" in m249 and "median" in m249
    assert by_file["MasterDark_5_20.0s_10.5C_20261015-235231.fit"]["captures"] == 0
    assert [c["object_dir"] for c in dev["captures"]] == ["C 6", "M 72"]
    # stats are cached by content: a second rollup reads no pixels
    monkeypatch.setattr(calibration, "master_stats",
                        lambda p: (_ for _ in ()).throw(AssertionError("re-read")))
    build_derived.main()


# ── rule v2: the device switches darks mid-run, inside a sticky window ────────
# Replays the real C 6 run of 2026-10-17 (live-store subs, read-only analysis,
# DONE.md): it started at 26.0 °C on the 24.9 °C dark, held it at 23.4 °C even
# though 23.2 was nearer, switched to 23.2 at 22.1 °C (2.8 off 24.9), held 23.2
# all the way down to 16.6 °C, and switched to 13.9 at 16.25 °C (2.35 from it).

FULL_LIBRARY = LIBRARY + [("23.2", "20261016-204959"), ("7.7", "20261017-015231")]
C6_OCT17 = [("20261017-191608", 26.0), ("20261017-194500", 24.375),
            ("20261017-195200", 23.4), ("20261017-200311", 22.062),
            ("20261017-202900", 20.2), ("20261017-205500", 18.6),
            ("20261017-213827", 16.6), ("20261017-214409", 16.25),
            ("20261017-214534", 16.5), ("20261017-220800", 15.8)]


def _full_library():
    for temp, stamp in FULL_LIBRARY:
        seestar_master_dark(config.calibration_dir(S50, "darks")
                            / f"MasterDark_5_20.0s_{temp}C_{stamp}.fit", float(temp))
    return calibration.library(S50)["darks"]


def test_rule_v2_follows_the_measured_mid_run_switches(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    masters = _full_library()
    used = calibration.applied_darks(
        [(f"Light_C 6_20.0s_LP_{s}.fit", t) for s, t in C6_OCT17],
        exptime=20.0, gain=80, binning=1, masters=masters)
    assert [ad.master.temp_c for ad in used] == [
        24.9, 24.9, 24.9,          # 23.4 °C: still within 2.5 of 24.9 → sticky
        23.2, 23.2, 23.2, 23.2,    # 22.06: 2.84 off → nearest within the window
        13.9, 13.9, 13.9]          # 16.25: 13.9 comes within 2.5; 16.5 jitter keeps it
    assert used[0].link == "inferred"          # 24.9 was made two nights earlier
    assert {ad.link for ad in used[3:]} == {"inferred"}
    assert round(max(ad.gap(t) for ad, (_, t) in zip(used, C6_OCT17)), 1) == 6.6


def test_rule_v2_never_switches_to_a_dark_made_later(tmp_path, monkeypatch):
    """Oct 15 M 72: the 13.9 °C dark was made at 21:52, after the run ended, so the
    24.9 °C dark stays in use however far the sensor cools."""
    seed_root(tmp_path, monkeypatch)
    masters = _full_library()
    used = calibration.applied_darks(
        [(f"Light_M 72_20.0s_IRCUT_{s}.fit", t) for s, t in M72],
        exptime=20.0, gain=80, binning=1, masters=masters)
    assert {ad.master.temp_c for ad in used} == {24.9}


def test_a_session_lists_every_dark_it_used(tmp_path, monkeypatch):
    from m110 import scan_sessions
    from m110.ui.widgets import dark_gap_item
    seed_root(tmp_path, monkeypatch)
    _full_library()
    _lights("C 6", C6_OCT17)
    (row,) = scan_sessions.scan()
    assert [n.split("_")[3] for n in row["dark_refs"]] == ["24.9C", "23.2C", "13.9C"]
    assert row["dark_ref"] == row["dark_refs"][0] and row["dark_rule"] == "v2"
    assert row["dark_gap_c"] == 6.6
    item = dark_gap_item(row)
    assert item.text() == "3 darks · Δ6.6 ⚠"
    tip = item.toolTip()
    assert "switches are inferred" in tip
    # named exactly as the Devices page's dark library names them, in order
    assert tip.index("Oct 15 19:28 · 24.9 °C") < tip.index("Oct 16 20:49 · 23.2 °C") \
        < tip.index("Oct 15 21:52 · 13.9 °C")


def test_m110_stack_gaps_follow_the_switches(tmp_path, monkeypatch):
    from tests.test_stacking import _sub
    seed_root(tmp_path, monkeypatch)
    _full_library()
    d = tmp_path / "job"
    for stamp, temp in C6_OCT17:
        _sub(d / "lights" / f"Light_C 6_20.0s_LP_{stamp}.fit", EXPTIME=20.0, GAIN=80,
             XBINNING=1, CCD_TEMP=temp, FILTER="LP", TELESCOP=S50, OBJECT="C 6")
    plan = build_plan(d, Overrides(max_dark_gap=3.0), deep_measure=False)
    # only 20.2 (3.0 off 23.2 — not over), 18.6 and 16.6 drifted past 3 °C
    assert len(plan.dropped) == 2


def test_a_myworks_source_also_covers_the_dark_library_beside_it(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    myworks, _ = mount_seestar(tmp_path, monkeypatch, "M 72", extra=LIGHT)
    assert ingest.source_scan_roots(myworks) == [myworks]          # no library yet
    lib = mount_darklibrary(myworks.parent, MASTERS[:1]).parent
    assert ingest.source_scan_roots(myworks) == [myworks, lib]
    assert ingest.source_scan_roots(myworks / "M 72_sub") == [myworks / "M 72_sub"]
    assert ingest.source_scan_roots(None) == []
    ops = ingest.scan_source_plan(myworks)
    assert any(o.kind == "cal-dark" for o in ops) and any(o.kind == "light" for o in ops)
