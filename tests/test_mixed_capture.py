"""One object shot two ways (#203): a Seestar's own app subs (dark-subtracted on the
telescope) beside the same scope's N.I.N.A. subs (not).

Siril prep splits such a filter into one job folder per calibration subset (the
Naztronomy script calibrates a whole folder with its darks/), records the split
beside them, and m110-stack stacks the split folders together, calibrating each
subset on its own. Temp fixtures only.
"""
import json
from pathlib import Path

import numpy as np
from astropy.io import fits

from m110 import config, siril, stacking
from tests._helpers import nina_frame, seed_root

S50 = "S50_15e7e390"


def _app_sub(path: Path, when: str, temp=12.0):
    """A Seestar-app sub: CREATOR + BIAS, IRCUT, 20 s, named the app's way."""
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    for k, v in {"TELESCOP": S50, "INSTRUME": "Seestar S50", "CREATOR": "ZWO Seestar S50",
                 "BIAS": 468, "EXPTIME": 20.0, "GAIN": 80, "XBINNING": 1,
                 "CCD-TEMP": temp, "FILTER": "IRCUT", "OBJECT": "M 74",
                 "DATE-OBS": when}.items():
        h.header[k] = v
    h.writeto(path)


def _mixed_m74(n_app=3, n_nina=3, with_darks=True):
    lights = config.lights_dir("M74")
    for i in range(n_app):
        _app_sub(lights / f"Light_M 74_20.0s_IRCUT_20261018-0{i}0000.fit",
                 f"2026-10-18T0{i}:00:00")
    for i in range(n_nina):
        # N.I.N.A. calls the S50's UV/IR-cut slot "IR"; it reads as IRCUT
        nina_frame(lights / f"2026-11-06_22-0{i}-00_IR_11.00_30.00s_000{i}.fits",
                   obj="M 74", exp=30.0, temp=11.0, filt="IR",
                   date_loc=f"2026-11-06T22:0{i}:00.0")
    if with_darks:
        for i in range(4):
            nina_frame(config.calibration_dir(S50, "darks") / f"d{i}.fits",
                       imagetyp="DARK", obj=None, exp=30.0, temp=5.7, filt="Dark",
                       date_loc="2026-11-07T05:00:00.0")


def test_prep_splits_a_mixed_filter_and_keeps_darks_out_of_the_app_folder(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74()
    plan = siril.plan_prep("M74")
    jobs = {j.filt: j for j in plan.jobs}
    assert set(jobs) == {"IRCUT", "IRCUT_30s"}
    assert jobs["IRCUT"].label == "IRCUT · 20 s · Seestar app"
    assert jobs["IRCUT_30s"].label == "IRCUT · 30 s · N.I.N.A."
    assert len(jobs["IRCUT"].links) == 3 and len(jobs["IRCUT_30s"].links) == 3
    darks = [dst for _src, dst in plan.calib_links]
    assert len(darks) == 4 and all("/IRCUT_30s/darks/" in d for d in darks)
    assert jobs["IRCUT"].preset["darks"] is False and jobs["IRCUT_30s"].preset["darks"] is True
    assert plan.job_groups == {"IRCUT": ["IRCUT", "IRCUT_30s"]}

    siril.apply_prep(plan)
    base = config.siril_dir("M74")
    assert not (base / "IRCUT" / "darks").exists()        # never a darks/ for app subs
    assert len(list((base / "IRCUT_30s" / "darks").iterdir())) == 4
    assert json.loads((base / siril.JOB_GROUPS_NAME).read_text())["groups"] == {
        "IRCUT": ["IRCUT", "IRCUT_30s"]}
    assert siril.job_group(base / "IRCUT_30s") == [base / "IRCUT", base / "IRCUT_30s"]
    assert siril.working_dirs("M74") and set(d.name for d in siril.working_dirs("M74")) == {
        "IRCUT", "IRCUT_30s"}
    steps = (base / "next-steps.md").read_text()
    assert "IRCUT · 30 s · N.I.N.A." in steps and "m110-stack" in steps


def test_an_unmixed_target_is_still_one_job_and_no_group_file(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74(n_nina=0)
    plan = siril.plan_prep("M74")
    assert [j.filt for j in plan.jobs] == [""] and plan.job_groups == {}
    siril.apply_prep(plan)
    assert not (config.siril_dir("M74") / siril.JOB_GROUPS_NAME).exists()
    assert siril.job_group(config.siril_dir("M74")) is None


def test_m110_stack_stacks_a_split_filter_together(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _mixed_m74()
    siril.apply_prep(siril.plan_prep("M74"))
    base = config.siril_dir("M74")
    # pointed at either member, the group stacks in the plain (no-darks) folder
    plan = stacking.build_plan(base / "IRCUT_30s", stacking.Overrides(), deep_measure=False)
    assert plan.working == (base / "IRCUT").resolve()
    assert plan.proposal.get("job_group") == ["IRCUT", "IRCUT_30s"]
    assert len(plan.frames) == 6 and len(plan.group_files) == 6
    subs = plan.proposal.get("calibration_subsets")
    # matched from the library per subset — IRCUT_30s/darks/ is not applied to all
    assert [(sb["label"], bool(sb["calibration"])) for sb in subs] == [
        ("3 × 30 s", True), ("3 × 20 s, dark-subtracted on the telescope", False)]
    lines = plan.solve_ssf.splitlines()
    assert lines[lines.index("cd process/stack_lights") + 2] == "link stack_lights -out=.."
    assert "merge pp1_stack_lights_ pp2_stack_lights_ pp_stack_lights_" in lines
    assert any("Stacking IRCUT + IRCUT_30s together" in w for w in plan.proposal.warnings)
    assert not (plan.working / "process").exists()           # the plan wrote nothing
    staged = stacking.stage_group_lights(plan.working, plan.group_files)
    assert sorted(p.name for p in staged.iterdir()) == sorted(p.name for p in plan.group_files)
