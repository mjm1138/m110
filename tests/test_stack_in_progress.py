"""A stack running in a sandbox must never be disturbed by M110 tidying it.

The incident (2026-10-20): "Import finished work" on M1 landed between
m110-stack's plate-solve and registration phases. `archive_run` swept the live
`process/` scratch (the solved `bkg_pp_lights_` sequence) and the open log into
`archive/<ts>/`; phase 2 failed with Siril's "No sequence found" and m110-stack
said only "Registration failed (exit 1)".

Four halves, each tested here:
  * the run marker — written for the whole `--run`, removed however it ends,
    stale ones ignored and cleaned;
  * the user-driven writers (`apply_import`, `archive_run`) refuse before any
    write while a marker is live;
  * the automatic writers (`autoprep`, `prune_rejected`) skip such a target, and
    also skip on recent `process/` activity (a Siril GUI run leaves no marker);
  * a later phase whose input vanished says so plainly.
"""
import json
import os
import socket
import subprocess
import sys
import time

import numpy as np
import pytest

from m110 import astrowizard, config, roundtrip, siril
from tests._helpers import seed_root, seed_sandbox


def _isolate(tmp_path, monkeypatch, name="M1", n=3):
    root = tmp_path / "M110"
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    lights = config.lights_dir(name)
    lights.mkdir(parents=True)
    names = [f"Light_{name}_20s_IRCUT_20260101-{i:06d}.fit" for i in range(n)]
    for f in names:
        (lights / f).write_text("x")
    return name, names


def _marker(job_dir, pid=None, host=None, phase="register"):
    """A marker as another (live, by default) process would have written it."""
    path = job_dir / roundtrip.RUN_MARKER
    path.write_text(json.dumps({
        "pid": os.getppid() if pid is None else pid,
        "host": host or socket.gethostname(),
        "started": time.time(), "phase": phase}), encoding="utf-8")
    return path


def _dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def _age(path, seconds):
    t = time.time() - seconds
    os.utime(path, (t, t))


# ── the marker ───────────────────────────────────────────────────────────────

def test_a_live_marker_is_reported(tmp_path):
    _marker(tmp_path, phase="solve")
    info = roundtrip.stack_in_progress(tmp_path)
    assert info and info["phase"] == "solve" and info["job"] == str(tmp_path)


def test_a_stale_marker_is_ignored_and_cleaned_up(tmp_path):
    path = _marker(tmp_path, pid=_dead_pid())
    assert roundtrip.stack_in_progress(tmp_path) is None
    assert not path.exists()


def test_an_unreadable_marker_is_treated_as_stale(tmp_path):
    path = tmp_path / roundtrip.RUN_MARKER
    path.write_text("{not json")
    assert roundtrip.stack_in_progress(tmp_path) is None
    assert not path.exists()


def test_a_marker_from_another_host_cannot_be_probed_so_counts_as_live(tmp_path):
    """A store on a NAS shared by two Macs: the pid means nothing here."""
    _marker(tmp_path, pid=_dead_pid(), host="some-other-mac.local")
    info = roundtrip.stack_in_progress(tmp_path)
    assert info is not None
    assert "some-other-mac.local" in roundtrip.describe_runs([info])


def test_clear_only_removes_our_own_marker(tmp_path):
    """A refused second run must not delete the live run's marker on its way out."""
    theirs = _marker(tmp_path)
    roundtrip.clear_run_marker(tmp_path)
    assert theirs.exists()
    roundtrip.write_run_marker(tmp_path, "stack")
    roundtrip.clear_run_marker(tmp_path)
    assert not theirs.exists()


def test_the_marker_is_never_offered_as_output(tmp_path, monkeypatch):
    target, _ = _isolate(tmp_path, monkeypatch)
    siril.apply_prep(siril.plan_prep(target))
    roundtrip.write_run_marker(config.siril_dir(target), "solve")
    assert not siril.has_unimported_output(target)


def test_scratch_activity_is_judged_by_recent_writes(tmp_path):
    proc = tmp_path / "process"
    proc.mkdir()
    (proc / "pp_lights_00001.fit").write_bytes(b"x")
    assert roundtrip.scratch_recently_active(tmp_path)
    _age(proc / "pp_lights_00001.fit", 3600)
    _age(proc, 3600)
    assert not roundtrip.scratch_recently_active(tmp_path)
    assert not roundtrip.scratch_recently_active(tmp_path / "nowhere")


# ── user-driven writers refuse ───────────────────────────────────────────────

def _prepped_with_output(tmp_path, monkeypatch):
    target, _ = _isolate(tmp_path, monkeypatch)
    siril.apply_prep(siril.plan_prep(target))
    sb = config.siril_dir(target)
    (sb / f"{target}_2026_processed.png").write_text("PNG")
    proc = sb / "process"
    proc.mkdir()
    (proc / "bkg_pp_lights_.seq").write_text("S")
    return target, sb


def test_import_refuses_while_a_stack_runs_and_writes_nothing(tmp_path, monkeypatch):
    target, sb = _prepped_with_output(tmp_path, monkeypatch)
    _marker(sb)
    plan = siril.scan_finished(target)
    assert plan.running and plan.items           # previewable, but refused
    with pytest.raises(roundtrip.StackInProgress, match="Wait for it to finish"):
        siril.apply_import(target, [it.src for it in plan.items])
    assert not config.finished_dir(target).exists()
    assert (sb / "process" / "bkg_pp_lights_.seq").is_file()
    assert not (sb / "archive").exists()


def test_archive_run_refuses_while_a_stack_runs(tmp_path, monkeypatch):
    target, sb = _prepped_with_output(tmp_path, monkeypatch)
    _marker(sb)
    with pytest.raises(roundtrip.StackInProgress):
        siril._archive_run(target)
    assert (sb / "process").is_dir()


def test_a_marker_in_a_per_filter_job_is_seen(tmp_path, monkeypatch):
    target, sb = _prepped_with_output(tmp_path, monkeypatch)
    job = sb / "LP"
    (job / "lights").mkdir(parents=True)
    _marker(job)
    assert [r["job"] for r in roundtrip.active_runs(target, siril.SANDBOX)] == [str(job)]
    with pytest.raises(roundtrip.StackInProgress):
        siril.apply_import(target, [])


def test_import_proceeds_once_the_marker_is_stale(tmp_path, monkeypatch):
    target, sb = _prepped_with_output(tmp_path, monkeypatch)
    _marker(sb, pid=_dead_pid())
    plan = siril.scan_finished(target)
    assert not plan.running
    res = siril.apply_import(target, [it.src for it in plan.items])
    assert res["imported"] == 1 and res["cleaned"] == "archive"


def test_recent_scratch_activity_is_reported_but_does_not_refuse(tmp_path, monkeypatch):
    """The Siril GUI heuristic only warns: mtime can't say who wrote, and the
    usual moment to import is right after a GUI run finishes."""
    target, sb = _prepped_with_output(tmp_path, monkeypatch)
    plan = siril.scan_finished(target)
    assert plan.scratch_active == [str(sb)] and not plan.running
    res = siril.apply_import(target, [it.src for it in plan.items], cleanup="none")
    assert res["imported"] == 1


# ── automatic writers skip ───────────────────────────────────────────────────

def test_autoprep_skips_a_target_with_a_stack_running(tmp_path, monkeypatch):
    target, _ = _isolate(tmp_path, monkeypatch)
    siril.apply_prep(siril.plan_prep(target))
    _marker(config.siril_dir(target))
    assert siril.autoprep([target])["skipped"] == [target]


def test_autoprep_skips_a_target_whose_scratch_is_being_written(tmp_path, monkeypatch):
    target, _ = _isolate(tmp_path, monkeypatch)
    siril.apply_prep(siril.plan_prep(target))
    (config.siril_dir(target) / "process").mkdir()
    assert siril.autoprep([target])["skipped"] == [target]
    _age(config.siril_dir(target) / "process", 3600)
    assert siril.autoprep([target])["prepared"] == [target]


def test_prune_rejected_skips_a_target_with_a_stack_running(tmp_path, monkeypatch):
    """Siril's `link` points the scratch at the lights/ files — unlinking one
    mid-run pulls a frame out from under it."""
    target, names = _isolate(tmp_path, monkeypatch)
    siril.apply_prep(siril.plan_prep(target))
    rej = config.rejected_dir(target)
    rej.mkdir()
    (config.lights_dir(target) / names[0]).rename(rej / names[0])
    marker = _marker(config.siril_dir(target))
    assert siril.prune_rejected(target)["skipped"] is True
    assert (config.siril_dir(target) / "lights" / names[0]).exists()
    marker.unlink()
    assert siril.prune_rejected(target)["pruned"] == 1


def test_astrowizard_autoprep_skips_a_sandbox_with_a_stack_running(tmp_path, monkeypatch):
    target, _ = _isolate(tmp_path, monkeypatch)
    astrowizard.prepare_lights(target)
    _marker(config.astrowizard_dir(target))
    assert astrowizard.autoprep([target])["skipped"] == [target]


# ── m110-stack: the marker's lifecycle, and saying what vanished ─────────────

def _sub(path, **cards):
    from astropy.io import fits
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="float32"))
    h.header["EXPTIME"] = 20.0
    h.header["DATE-OBS"] = "2026-05-25T22:00:00"
    for k, v in cards.items():
        h.header[k] = v
    h.writeto(path)


def _drive(tmp_path, monkeypatch, on_phase, between=None):
    """`m110-stack --run` over three frames with Siril stubbed. `on_phase(name,
    working)` runs inside each fake phase and may return a non-zero exit code."""
    from m110 import stacking as st
    d = tmp_path / "siril"
    for i in range(3):
        _sub(d / "lights" / f"Light_{i}.fit", OBJECT="M1")

    def fake_run(siril_, working, ssf, log_path, heartbeat, on_line=None,
                 on_raw=None):
        if "seqplatesolve" in ssf:
            (working / "process").mkdir(exist_ok=True)
            (working / "process" / "bkg_pp_lights_.seq").write_text("S")
            log_path.write_text("3 images successfully platesolved out of 3 "
                                "included\n")
            return on_phase("solve", working) or 0, []
        if "seqapplyreg" in ssf:
            rc = on_phase("register", working)
            if not rc:
                (working / "process" / "r_bkg_pp_lights_.seq").write_text("S")
            return rc or 0, []
        rc = on_phase("stack", working)
        if not rc:
            _sub(working / "result.fit", OBJECT="M1", STACKCNT=3, LIVETIME=60.0)
        return rc or 0, []

    monkeypatch.setattr(st, "run_siril", fake_run)
    monkeypatch.setattr(st, "require_siril", lambda: "siril")
    monkeypatch.setattr(st, "find_degenerate",       # runs between phases 2 and 3
                        lambda *a, **k: (between and between(d)) or [])
    monkeypatch.delenv("SIRIL_CLI", raising=False)
    monkeypatch.setattr(sys, "argv", ["m110-stack", str(d), "--run",
                                      "--plain-name", "--keep-process"])
    return st.main(), d


def test_the_marker_spans_the_run_and_names_each_phase(tmp_path, monkeypatch):
    seen = []

    def on_phase(name, working):
        info = roundtrip.stack_in_progress(working)
        seen.append((name, info and info["phase"], info and info["pid"]))

    rc, d = _drive(tmp_path, monkeypatch, on_phase)
    assert rc == 0
    assert seen == [(p, p, os.getpid()) for p in ("solve", "register", "stack")]
    assert not (d / roundtrip.RUN_MARKER).exists()


def test_the_marker_is_removed_after_a_failed_run(tmp_path, monkeypatch):
    rc, d = _drive(tmp_path, monkeypatch,
                   lambda name, w: 1 if name == "register" else 0)
    assert rc == 1
    assert not (d / roundtrip.RUN_MARKER).exists()


def test_a_second_run_in_the_same_folder_is_refused(tmp_path, monkeypatch, capsys):
    """It would clear the first run's scratch before its own phase 1."""
    d = tmp_path / "siril"
    d.mkdir()
    theirs = _marker(d, phase="solve")
    rc, _ = _drive(tmp_path, monkeypatch, lambda *a: pytest.fail("ran Siril"))
    assert rc == 2
    assert theirs.exists()
    assert "Not starting a second run" in capsys.readouterr().err


def test_registration_failure_says_the_scratch_was_swept_into_the_archive(
        tmp_path, monkeypatch, capsys):
    """The incident, replayed: an import's archive sweep lands between phases."""
    def on_phase(name, working):
        if name == "solve":
            dest = working / "archive" / "20261020-085357"
            dest.mkdir(parents=True)
            (working / "process").rename(dest / "process")
        if name == "register":
            return 1

    rc, _ = _drive(tmp_path, monkeypatch, on_phase)
    out = capsys.readouterr().out
    assert rc == 1
    assert "Registration failed (exit 1): process/ was moved or removed during " \
           "the run — was the sandbox imported or cleaned up?" in out
    assert "archive/20261020-085357/process/" in out


def test_stack_failure_says_when_the_registered_sequence_vanished(
        tmp_path, monkeypatch, capsys):
    import shutil

    def on_phase(name, working):
        if name == "stack":
            shutil.rmtree(working / "process")
            return 1

    rc, _ = _drive(tmp_path, monkeypatch, on_phase)
    out = capsys.readouterr().out
    assert rc == 1 and "FAILED (exit 1). process/ was moved or removed" in out


def test_a_sweep_between_register_and_stack_is_reported_too(
        tmp_path, monkeypatch, capsys):
    import shutil

    rc, _ = _drive(tmp_path, monkeypatch,
                   lambda name, w: 1 if name == "stack" else 0,
                   between=lambda d: shutil.rmtree(d.resolve() / "process",
                                                 ignore_errors=True))
    assert rc == 1 and "process/ was moved or removed" in capsys.readouterr().out


def test_an_ordinary_registration_failure_keeps_the_ordinary_message(
        tmp_path, monkeypatch, capsys):
    rc, _ = _drive(tmp_path, monkeypatch,
                   lambda name, w: 1 if name == "register" else 0)
    out = capsys.readouterr().out
    assert "Registration failed (exit 1). Log:" in out
    assert "moved or removed" not in out


# ── the import dialog ────────────────────────────────────────────────────────

def test_import_dialog_refuses_while_a_stack_runs(tmp_path, monkeypatch, qapp, qtbot):
    pytest.importorskip("PySide6")
    seed_root(tmp_path, monkeypatch)
    sb = seed_sandbox("M51")
    _marker(sb)
    from m110.ui.import_dialog import ImportDialog
    dlg = ImportDialog("M51", "m51")
    try:
        qtbot.waitUntil(lambda: dlg._plan is not None)
        assert not dlg._import_btn.isEnabled()
        assert "A stack is running in this sandbox" in dlg._info.text()
        dlg._do_import()                          # even if reached: no worker
        assert dlg._worker is None
        assert not config.finished_dir("M51").exists()
    finally:
        dlg.reject()
        dlg.deleteLater()
        qapp.processEvents()


def test_import_dialog_warns_and_leaves_the_sandbox_on_recent_scratch(
        tmp_path, monkeypatch, qapp, qtbot):
    pytest.importorskip("PySide6")
    seed_root(tmp_path, monkeypatch)
    sb = seed_sandbox("M51")
    (sb / "process").mkdir()
    from m110.ui.import_dialog import ImportDialog
    dlg = ImportDialog("M51", "m51")
    try:
        qtbot.waitUntil(dlg._import_btn.isEnabled)
        assert "Siril may still be working here" in dlg._info.text()
        assert dlg._cleanup.currentData() == "none"
    finally:
        dlg.reject()
        dlg.deleteLater()
        qapp.processEvents()
