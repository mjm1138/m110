"""Naztronomy preset generation + the edited-vs-pristine re-tune guard.

The preset is a step-function of frame count (drizzle + star-quality filters).
`apply_prep` re-tunes it as frames grow — but only while it's still an untouched
default; a hand-edited preset is preserved.
"""
from __future__ import annotations

import json

from m110 import config, siril
from ._helpers import seed_root


def _make_lights(target, n, filt="LP"):
    d = config.lights_dir(target)
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (d / f"Light_{target}_10.0s_{filt}_20260101-{i:06d}.fit").write_text("x")


def _preset_path(target):
    return siril.plan_prep(target).jobs[0].preset_path


# ── frame-count tuning ───────────────────────────────────────────────────────

def test_filter_quality_buckets():
    assert siril.filter_quality_for(50) == (False, 98.0)
    assert siril.filter_quality_for(100) == (True, 98.0)
    assert siril.filter_quality_for(500) == (True, 98.0)
    assert siril.filter_quality_for(501) == (True, 95.0)
    assert siril.filter_quality_for(1500) == (True, 95.0)
    assert siril.filter_quality_for(1501) == (True, 90.0)


def test_default_preset_tunes_filters_by_count():
    lo = siril.default_preset(50)      # below floor
    assert lo["filters"] is False
    mid = siril.default_preset(300)
    assert mid["filters"] is True
    assert mid["roundness"] == mid["fwhm"] == mid["star_count_filter"] == mid["bg_filter"] == 98.0
    big = siril.default_preset(1000)
    assert big["roundness"] == 95.0 and big["drizzle_amount"] == 2.0
    huge = siril.default_preset(2000)
    assert huge["roundness"] == 90.0


def test_is_default_preset_detects_edits():
    d = siril.default_preset(300)
    assert siril.is_default_preset(d)
    edited = {**d, "roundness": 42.0}
    assert not siril.is_default_preset(edited)
    assert not siril.is_default_preset({})       # unreadable/garbage → not default


# ── apply_prep: re-tune pristine, preserve edited ────────────────────────────

def test_preset_retunes_while_pristine(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    siril.apply_prep(siril.plan_prep("M51"))
    p1 = json.loads(open(_preset_path("M51")).read())
    assert p1["roundness"] == 98.0 and p1["drizzle_amount"] == 1.5

    _make_lights("M51", 600)                      # grow across buckets
    siril.apply_prep(siril.plan_prep("M51"))
    p2 = json.loads(open(_preset_path("M51")).read())
    assert p2["roundness"] == 95.0 and p2["drizzle_amount"] == 2.0   # re-tuned


def test_preset_preserved_when_edited(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _make_lights("M51", 120)
    siril.apply_prep(siril.plan_prep("M51"))
    pp = _preset_path("M51")
    edited = {**json.loads(open(pp).read()), "roundness": 42.0, "spcc": True}
    open(pp, "w").write(json.dumps(edited, indent=4) + "\n")

    _make_lights("M51", 600)
    siril.apply_prep(siril.plan_prep("M51"))
    after = json.loads(open(pp).read())
    assert after["roundness"] == 42.0 and after["spcc"] is True       # preserved
    assert after["drizzle_amount"] == 1.5                             # not re-tuned
