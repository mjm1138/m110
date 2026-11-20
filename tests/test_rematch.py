"""Re-matching an existing Siril sandbox's calibration when the library, the
target's own frames or the matching rules change (`siril.plan_rematch` /
`apply_rematch`, `processing.rematch_calibration`, the sync hook and the
Processing page's Re-match Calibration…). Temp fixtures only."""
import json
from pathlib import Path

import numpy as np
from astropy.io import fits

from m110 import calibration, config, processing, siril
from tests._helpers import nina_frame, seed_root
from tests.test_mixed_capture import S50, _mixed_m74


def _raw_darks(temp, n=4, exp=30.0, night="2026-11-07T05:00:00.0", prefix="d"):
    return [nina_frame(config.calibration_dir(S50, "darks") / f"{prefix}{i}.fits",
                       imagetyp="DARK", obj=None, exp=exp, temp=temp, filt="Dark",
                       date_loc=night) for i in range(n)]


def _master(name, temp, exp=30.0):
    path = config.calibration_dir(S50, "darks") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    for k, v in {"IMAGETYP": "Master Dark", "EXPTIME": exp, "GAIN": 80,
                 "XBINNING": 1, "CCD-TEMP": temp, "NCOMBINE": 20,
                 "TELESCOP": "S50 Prime"}.items():
        h.header[k] = v
    h.writeto(path)
    return path


def _names(d: Path) -> list[str]:
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def _prep():
    siril.apply_prep(siril.plan_prep("M74"))
    return config.siril_dir("M74")


# ── the stamp ────────────────────────────────────────────────────────────────

def test_the_key_tracks_the_library_the_targets_own_frames_and_the_rules(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    k0 = calibration.calibration_key("M74", S50)
    assert calibration.calibration_key("M74", S50) == k0          # stable
    _raw_darks(11.0)
    k1 = calibration.calibration_key("M74", S50)
    assert k1 != k0                                               # library grew
    nina_frame(config.darks_dir("M74") / "own.fits", imagetyp="DARK", obj=None,
               exp=30.0, temp=11.0, filt="Dark")
    k2 = calibration.calibration_key("M74", S50)
    assert k2 != k1                                               # target's own
    monkeypatch.setattr(calibration, "MATCH_RULES", calibration.MATCH_RULES + 1)
    assert calibration.calibration_key("M74", S50) != k2          # rules changed


def test_prep_stamps_the_key_and_a_current_sandbox_is_not_replanned(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0)
    base = _prep()
    assert siril.read_manifest(base)["calibration_key"] == \
        calibration.calibration_key("M74", S50)
    monkeypatch.setattr(siril, "plan_prep",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-planned")))
    assert siril.plan_rematch("M74").status == "current"


def test_header_and_library_caches_follow_the_files(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    (p,) = _raw_darks(5.0, n=1)
    assert calibration.frame_facts(p)["temp_c"] == 5.0
    with fits.open(p, mode="update") as hdul:
        hdul[0].header["CCD-TEMP"] = 9.5
    assert calibration.frame_facts(p)["temp_c"] == 9.5
    assert len(calibration.library(S50)["darks"]) == 1
    _raw_darks(6.0, n=2, prefix="e")
    assert len(calibration.library(S50)["darks"]) == 3


# ── re-matching ──────────────────────────────────────────────────────────────

def test_a_nearer_dark_replaces_the_linked_one_and_the_manifest_agrees(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    old = _master("master_16C.fits", 16.0)                # lights are at 11 °C
    base = _prep()
    assert _names(base / "darks") == [old.name]
    preset = base / "presets" / siril.PRESET_NAME
    edited = {**json.loads(preset.read_text()), "drizzle_amount": 9.9}
    preset.write_text(json.dumps(edited))                  # a hand edit

    _raw_darks(11.0)                                       # a better match arrives
    rp = siril.plan_rematch("M74")
    assert rp.status == "changes"
    assert any("dark master master_16C.fits, 16 °C → 4 raw frames" in c
               for c in rp.changes), rp.changes
    res = siril.apply_rematch(rp)
    assert res["written"] and res["removed"] == 1
    assert _names(base / "darks") == [f"d{i}.fits" for i in range(4)]
    assert old.is_file()                                   # the library keeps it
    m = siril.read_manifest(base)
    assert m["jobs"][0]["calibration"]["darks"]["kind"] == "raw-set"
    assert m["calibration_key"] == calibration.calibration_key("M74", S50)
    assert json.loads(preset.read_text())["drizzle_amount"] == 9.9
    assert siril.plan_rematch("M74").status == "current"


def test_new_darks_switch_on_a_hand_edited_presets_darks_and_nothing_else(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    base = _prep()
    preset = base / "presets" / siril.PRESET_NAME
    before = json.loads(preset.read_text())
    assert before["darks"] is False
    preset.write_text(json.dumps({**before, "feather": True}))
    _raw_darks(11.0)
    siril.apply_rematch(siril.plan_rematch("M74"))
    after = json.loads(preset.read_text())
    assert after["darks"] is True and after["feather"] is True
    assert {k: v for k, v in after.items() if k not in ("darks", "feather")} == \
        {k: v for k, v in before.items() if k not in ("darks", "feather")}


def test_new_darks_split_a_job_and_the_old_layout_is_retired(tmp_path, monkeypatch):
    """App + N.I.N.A. subs with no darks anywhere: one job at the sandbox root.
    N.I.N.A. darks arrive → IRCUT (app) + IRCUT_30s (N.I.N.A. + darks). The root
    lights/ goes (it is no longer a job), presets and process/ stay."""
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(with_darks=False)
    base = _prep()
    assert len(_names(base / "lights")) == 6
    (base / "process").mkdir()
    (base / "process" / "keep.fit").write_bytes(b"scratch")
    import os
    for p in (base / "process", base / "process" / "keep.fit"):
        os.utime(p, (0, 0))                 # old scratch: Siril isn't running
    _raw_darks(5.7)
    rp = siril.plan_rematch("M74")
    assert any(c.startswith("job folders: . → IRCUT, IRCUT_30s") for c in rp.changes)
    siril.apply_rematch(rp)
    assert not (base / "lights").exists()
    assert (base / "presets" / siril.PRESET_NAME).is_file()
    assert (base / "process" / "keep.fit").is_file()
    assert [d.name for d in siril.working_dirs("M74")] == ["IRCUT", "IRCUT_30s"]
    assert len(_names(base / "IRCUT" / "lights")) == 3
    assert len(_names(base / "IRCUT_30s" / "lights")) == 3
    assert not (base / "IRCUT" / "darks").exists()
    assert _names(base / "IRCUT_30s" / "darks") == [f"d{i}.fits" for i in range(4)]
    assert all((config.lights_dir("M74") / n).is_file()
               for n in _names(base / "IRCUT" / "lights"))       # nothing lost


def test_a_file_the_user_put_in_darks_is_kept_and_noted(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    _master("master_16C.fits", 16.0)
    base = _prep()
    mine = base / "darks" / "my_master.fit"
    nina_frame(mine, imagetyp="DARK", obj=None, exp=30.0, temp=11.0, filt="Dark")
    _raw_darks(11.0)
    res = siril.apply_rematch(siril.plan_rematch("M74"))
    assert mine.is_file() and "master_16C.fits" not in _names(base / "darks")
    assert any("did not link (my_master.fit)" in n for n in res["notes"])


def test_a_busy_sandbox_or_one_with_output_waiting_is_left_for_later(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    _prep()
    _raw_darks(11.0)
    monkeypatch.setattr(siril.roundtrip, "sandbox_busy", lambda *a: True)
    assert siril.plan_rematch("M74").status == "skipped"
    out = processing.rematch_calibration()
    assert out["skipped"] == ["M74"] and out["updated"] == []
    monkeypatch.setattr(siril.roundtrip, "sandbox_busy", lambda *a: False)
    monkeypatch.setattr(siril, "has_unimported_output", lambda t: True)
    assert siril.plan_rematch("M74").status == "skipped"


def test_an_ingest_reprep_no_longer_leaves_the_old_dark_beside_the_new(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    _master("master_16C.fits", 16.0)
    base = _prep()
    _raw_darks(11.0)
    siril.autoprep(["M74"])                                # the ingest path
    assert _names(base / "darks") == [f"d{i}.fits" for i in range(4)]
    nina = siril.read_manifest(base)["jobs"][0]["calibration"]["darks"]
    assert [Path(f).name for f in nina["files"]] == _names(base / "darks")


# ── orchestration + UI ───────────────────────────────────────────────────────

def test_rematch_calibration_covers_the_store_and_respects_the_siril_setting(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    _master("master_16C.fits", 16.0)
    _prep()
    _raw_darks(11.0)
    monkeypatch.setattr(processing, "enabled_workflow_ids", lambda: ["astrowizard"])
    assert processing.rematch_calibration()["updated"] == []
    monkeypatch.setattr(processing, "enabled_workflow_ids", lambda: ["siril"])
    out = processing.rematch_calibration()
    assert out["updated"] == ["M74"] and out["changes"]["M74"]
    assert processing.rematch_calibration()["updated"] == []      # now current


def test_sync_rematches_and_the_status_bar_says_so(tmp_path, monkeypatch, qapp):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    _master("master_16C.fits", 16.0)
    _prep()
    _raw_darks(11.0)
    from m110.ui.main import RefreshWorker, recalibrated_message
    w = RefreshWorker()
    got = []
    w.done.connect(got.append)
    w.run()                                     # synchronously, on this thread
    assert got and got[0]["recalibrated"] == ["M74"]
    assert recalibrated_message(["M74"]) == "  ·  Calibration re-matched: M74"
    assert recalibrated_message(list("ABCDE")) == \
        "  ·  Calibration re-matched: A, B, C (+2 more)"
    assert recalibrated_message([]) == ""
    w.deleteLater()


def test_the_rematch_dialog_previews_then_applies(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    _master("master_16C.fits", 16.0)
    base = _prep()
    _raw_darks(11.0)
    from PySide6.QtCore import Qt
    from m110.ui.rematch_dialog import RematchDialog
    dlg = RematchDialog("M74")
    qtbot.addWidget(dlg)
    qtbot.waitUntil(lambda: dlg._apply_btn.isEnabled(), timeout=10000)
    assert "4 raw frames" in dlg._info.text()
    assert _names(base / "darks") == ["master_16C.fits"]      # preview wrote nothing
    with qtbot.waitSignal(dlg.rematched, timeout=10000):
        qtbot.mouseClick(dlg._apply_btn, Qt.LeftButton)
    assert _names(base / "darks") == [f"d{i}.fits" for i in range(4)]


def test_the_processing_page_offers_rematch(tmp_path, monkeypatch, qtbot):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    _prep()
    from m110.ui import rematch_dialog
    from m110.ui.pages.processing import ProcessingPage
    opened = []
    monkeypatch.setattr(rematch_dialog.RematchDialog, "exec",
                        lambda self: opened.append(self._target))
    page = ProcessingPage()
    qtbot.addWidget(page)
    page.open_rematch("M74")
    assert opened == ["M74"]


def test_a_split_sandbox_stays_split_when_one_filter_is_left(tmp_path, monkeypatch):
    """M81, 2026-11-20: its LP subs moved to another target, leaving IRCUT only.
    The IRCUT job keeps its folder (presets, earlier stacks) rather than moving to
    the sandbox root, where the LP folder's leftover links would hide it."""
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_app=0, with_darks=False)
    base = config.siril_dir("M74")
    lp = base / "LP" / "lights"
    lp.mkdir(parents=True)
    (lp / "gone_LP_0001.fits").write_bytes(b"x")         # a sub moved elsewhere
    ir = base / "IRCUT"
    (ir / "lights").mkdir(parents=True)
    (ir / "M74_stack.fit").write_bytes(b"stack")
    plan = siril.plan_prep("M74")
    assert [j.filt for j in plan.jobs] == ["IRCUT"]
    siril.apply_prep(plan)
    assert len(_names(ir / "lights")) == 3 and not (base / "lights").exists()
    assert (ir / "M74_stack.fit").is_file()
    assert _names(lp) == ["gone_LP_0001.fits"]           # never the last copy
