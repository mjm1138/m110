"""Naztronomy preset generation, and asking before replacing one (#174).

The preset is a step function of frame count (drizzle + the four frame-selection
filters, tuned apart), and its telescope + filter label follow the device and
filter. Prep writes a preset only where none exists; one that differs is reported
as a conflict and replaced only through `apply_preset_choices`.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from m110 import config, siril
from ._helpers import seed_root


def _make_lights(target, n, filt="LP", start=0):
    d = config.lights_dir(target)
    d.mkdir(parents=True, exist_ok=True)
    for i in range(start, start + n):
        (d / f"Light_{target}_10.0s_{filt}_20260101-{i:06d}.fit").write_text("x")


def _dwarf_light(target, i, filt, telescop="DWARF 3"):
    d = config.lights_dir(target)
    d.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((4, 4), dtype=np.uint16))
    h.header["FILTER"] = filt
    h.header["TELESCOP"] = telescop
    # The name carries no filter: the header is what prep must read.
    h.writeto(d / f"{target}_15s60_20251215-{i:09d}_16C.fits")


def _preset_path(target):
    return Path(siril.plan_prep(target).jobs[0].preset_path)


def _prep(target):
    return siril.apply_prep(siril.plan_prep(target))


# ── the tier table ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("n,on,roundness,fwhm", [
    (50, False, 95.0, 98.0), (99, False, 95.0, 98.0), (100, True, 95.0, 98.0),
    (500, True, 95.0, 98.0), (501, True, 92.0, 95.0), (1500, True, 92.0, 95.0),
    (1501, True, 90.0, 95.0),
])
def test_filter_tiers(n, on, roundness, fwhm):
    got_on, q = siril.filter_quality_for(n, "IRCUT")
    assert got_on is on
    assert q == {"roundness": roundness, "fwhm": fwhm, "star_count": 100.0, "bg": 98.0}


@pytest.mark.parametrize("filt", ["LP", "lp", "Duo-Band", "Dual-Band"])
def test_dual_band_turns_background_off(filt):
    assert siril.is_dual_band(filt)
    assert siril.filter_quality_for(800, filt)[1]["bg"] == 100.0


@pytest.mark.parametrize("filt", ["IRCUT", "Astro", "VIS", "OTHER", "", None])
def test_broadband_keeps_background(filt):
    assert not siril.is_dual_band(filt)
    assert siril.filter_quality_for(800, filt)[1]["bg"] == 98.0


@pytest.mark.parametrize("telescop,filt,scope,label", [
    ("S50_15e7e390", "LP", "ZWO Seestar S50", "LP (Narrowband)"),
    ("S50_15e7e390", "IRCUT", "ZWO Seestar S50", "No Filter (Broadband)"),
    ("S30_abc", "LP", "ZWO Seestar S30", "LP (Narrowband)"),
    ("DWARF 3", "Duo-Band", "Dwarf 3", "Dual-Band"),
    ("DWARF 3", "Astro", "Dwarf 3", "Astro filter (UV/IR)"),
    ("DWARF 3", "VIS", "Dwarf 3", "Astro filter (UV/IR)"),
    (None, "IRCUT", "ZWO Seestar S50", "No Filter (Broadband)"),     # unknown device
    ("Mystery Scope", "LP", "ZWO Seestar S50", "LP (Narrowband)"),
])
def test_naztronomy_scope(telescop, filt, scope, label):
    assert siril.naztronomy_scope(telescop, filt) == (scope, label)


def test_default_preset_writes_the_tiers_and_label():
    lo = siril.default_preset(50)
    assert lo["filters"] is False
    mid = siril.default_preset(300, "IRCUT")
    assert mid["filters"] is True and mid["filter"] == "No Filter (Broadband)"
    assert (mid["roundness"], mid["fwhm"], mid["bg_filter"], mid["star_count_filter"]) \
        == (95.0, 98.0, 98.0, 100.0)
    lp = siril.default_preset(1000, "LP")
    assert lp["filter"] == "LP (Narrowband)" and lp["bg_filter"] == 100.0
    assert lp["roundness"] == 92.0 and lp["drizzle_amount"] == 2.0
    dwarf = siril.default_preset(2000, "Duo-Band", "DWARF 3")
    assert (dwarf["telescope"], dwarf["filter"]) == ("Dwarf 3", "Dual-Band")
    assert dwarf["roundness"] == 90.0


# ── filter detection ─────────────────────────────────────────────────────────

def test_frame_filter_reads_dwarf_header(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _dwarf_light("M42", 1, "Duo-Band")
    f = next(config.lights_dir("M42").iterdir())
    assert siril.frame_filter(f) == "Duo-Band"


def test_frame_filter_rejects_unsafe_header(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _dwarf_light("M42", 1, "../../etc")
    f = next(config.lights_dir("M42").iterdir())
    assert siril.frame_filter(f) == siril.OTHER_FILTER


def test_dwarf_target_splits_by_header_and_labels_for_dwarf(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    for i in range(3):
        _dwarf_light("M42", i, "Duo-Band")
        _dwarf_light("M42", 10 + i, "Astro")
    plan = siril.plan_prep("M42")
    jobs = {j.filt: j for j in plan.jobs}
    assert set(jobs) == {"Astro", "Duo-Band"}
    assert jobs["Duo-Band"].preset["telescope"] == "Dwarf 3"
    assert jobs["Duo-Band"].preset["filter"] == "Dual-Band"
    assert jobs["Astro"].preset["filter"] == "Astro filter (UV/IR)"


def test_seestar_lp_job_is_labelled_lp(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M27", 120, "LP")
    preset = siril.plan_prep("M27").jobs[0].preset
    assert preset["filter"] == "LP (Narrowband)" and preset["bg_filter"] == 100.0


# ── apply_prep: write only where missing, report what differs ────────────────

def test_first_prep_writes_preset(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    res = _prep("M51")
    assert res["preset_conflicts"] == []
    assert json.loads(_preset_path("M51").read_text())["roundness"] == 95.0


def test_unchanged_proposal_is_not_a_conflict(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    _prep("M51")
    assert siril.plan_prep("M51").jobs[0].preset_state == "same"
    assert _prep("M51")["preset_conflicts"] == []


def test_grown_target_reports_conflict_and_leaves_file(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    _prep("M51")
    pp = _preset_path("M51")
    before = pp.read_text()

    _make_lights("M51", 600, start=120)                    # crosses a tier
    res = _prep("M51")
    assert pp.read_text() == before                        # nothing replaced
    [c] = res["preset_conflicts"]
    assert c.target == "M51" and c.preset_path == str(pp)
    changed = {k: (old, new) for k, old, new in c.changes}
    assert changed["roundness"] == (95.0, 92.0)
    assert changed["drizzle_amount"] == (1.5, 2.0)


def test_hand_saved_preset_is_a_conflict(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    _prep("M51")
    pp = _preset_path("M51")
    edited = {**json.loads(pp.read_text()), "spcc": True}
    pp.write_text(json.dumps(edited, indent=4))
    [c] = _prep("M51")["preset_conflicts"]
    assert ("spcc", True, False) in c.changes
    assert json.loads(pp.read_text())["spcc"] is True


def test_unreadable_preset_is_a_conflict_not_overwritten(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    _prep("M51")
    pp = _preset_path("M51")
    pp.write_text("{not json")
    assert len(_prep("M51")["preset_conflicts"]) == 1
    assert pp.read_text() == "{not json"


def test_replace_archives_and_writes_proposal(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    _prep("M51")
    pp = _preset_path("M51")
    old = pp.read_text()
    _make_lights("M51", 600, start=120)
    conflicts = _prep("M51")["preset_conflicts"]

    out = siril.apply_preset_choices(conflicts, {str(pp)})
    assert out == {"replaced": [str(pp)], "kept": []}
    assert json.loads(pp.read_text())["roundness"] == 92.0
    [archived] = (pp.parent / "archive").iterdir()
    assert archived.read_text() == old
    assert archived.name.startswith("naztronomy_smart_scope_presets.")
    assert siril.plan_prep("M51").jobs[0].preset_state == "same"


def test_keep_is_remembered_until_the_proposal_changes(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    _prep("M51")
    pp = _preset_path("M51")
    old = pp.read_text()
    _make_lights("M51", 600, start=120)
    conflicts = _prep("M51")["preset_conflicts"]

    assert siril.apply_preset_choices(conflicts, set())["kept"] == [str(pp)]
    assert pp.read_text() == old
    assert not (pp.parent / "archive").exists()
    # Same proposal next ingest → not asked again.
    assert siril.plan_prep("M51").jobs[0].preset_state == "declined"
    assert _prep("M51")["preset_conflicts"] == []
    # The proposal moves on (another tier) → asked again.
    _make_lights("M51", 1000, start=720)
    assert len(_prep("M51")["preset_conflicts"]) == 1


def test_archive_names_never_collide(tmp_path):
    pp = tmp_path / "presets" / siril.PRESET_NAME
    pp.parent.mkdir()
    names = set()
    for i in range(3):
        pp.write_text(str(i))
        names.add(siril.archive_preset(pp).name)
    assert len(names) == 3
    assert siril.archive_preset(pp) is None                # nothing left to move


def test_autoprep_collects_conflicts(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    siril.autoprep(["M51"])
    _make_lights("M51", 600, start=120)
    res = siril.autoprep(["M51"])
    assert [c.target for c in res["preset_conflicts"]] == ["M51"]
    # The refresh-time backfill never touches an existing sandbox.
    assert siril.autoprep(["M51"], only_missing=True)["preset_conflicts"] == []
