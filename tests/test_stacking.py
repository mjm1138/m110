"""Tests for m110/stacking.py — the settings decisions, not Siril itself.

Ported with the module from the Astronomy project, where every one of these
encoded something got wrong at least once while building the NGC 7000 and M15
stacks. The M110-specific additions (layout resolution, the read-only proposal
path, the handoff) are at the bottom. Temp fixtures only — nothing here runs
Siril, and nothing touches a live store.
"""

import json

import numpy as np
import pytest

from m110 import config
from m110.stacking import (
    Frame,
    Overrides,
    Proposal,
    StackingError,
    Survey,
    apply_handoff,
    as_ranges,
    build_plan,
    build_proposal,
    build_ssf_register,
    build_ssf_stack,
    coverage_depth,
    drizzle_for,
    find_degenerate,
    handoff_targets,
    naztronomy_name,
    reconcile,
    rejection_for,
    resolve_layout,
    select_frames,
    seq_names,
    summarize,
    target_for,
)


# --------------------------------------------------------------------------
# drizzle / rejection thresholds
# --------------------------------------------------------------------------


@pytest.mark.parametrize("depth,on,scale,pixfrac", [
    (20, False, 1.0, 1.0),
    (99, False, 1.0, 1.0),      # just under the floor
    (100, True, 1.5, 1.0),
    (108, True, 1.5, 1.0),      # NGC 7000 mosaic
    (299, True, 1.5, 1.0),
    (339, True, 1.5, 0.75),     # M15
    (600, True, 2.0, 0.5),
])
def test_drizzle_by_depth(depth, on, scale, pixfrac):
    got_on, got_scale, got_pf, why = drizzle_for(depth)
    assert (got_on, got_scale, got_pf) == (on, scale, pixfrac)
    assert why


@pytest.mark.parametrize("depth,expected", [
    (5, "p 0.2 0.1"),           # too few for a sigma estimate
    (30, "w 3 3"),              # Naztronomy's default range
    (50, "w 3 3"),
    (108, "w 3 3"),
    (753, "w 3 3"),
])
def test_rejection_by_depth(depth, expected):
    assert rejection_for(depth)[0] == expected


# --------------------------------------------------------------------------
# coverage depth — the number that separates a mosaic from a deep single target
# --------------------------------------------------------------------------


def _survey(ra, dec, fov_w=1.28, fov_h=0.72):
    s = Survey(n_frames=len(ra))
    s._ra, s._dec = np.array(ra, dtype=float), np.array(dec, dtype=float)
    s.fov_w, s.fov_h = fov_w, fov_h
    return s


def test_coverage_depth_single_target_counts_every_frame():
    # All pointings within a few arcmin: every frame covers every point.
    n = 40
    s = _survey([300.0 + i * 0.001 for i in range(n)], [40.0] * n)
    assert coverage_depth(s) == (n, n)


def test_one_junk_pointing_does_not_turn_a_single_target_into_a_mosaic():
    """Found on a real 744-frame LP set: one frame carrying DEC -90 (the south
    celestial pole, against a target at +69) stretched the sky span from ~1 degree
    to ~105. That flipped `is_mosaic` on, projected a 76-gigapixel canvas and an
    86 GB scratch, and would have proposed mosaic settings for a single target."""
    frames = [Frame(name=f"a{i}.fit", exposure=20.0, ra=150.0 + i * 0.001, dec=69.2)
              for i in range(40)]
    frames.append(Frame(name="junk.fit", exposure=20.0, ra=294.19, dec=-90.0))
    geom = {"naxis1": 1080, "naxis2": 1920, "xpixsz": 2.9, "focal": 250.0,
            "object": "M 81"}

    s = summarize(frames, geom)

    assert s.stray_pointings == 1
    assert not s.is_mosaic
    assert s.span_h < 2.0, "the pole frame must not stretch the span"
    assert s.n_frames == 41, "geometry only — every frame is still stacked"


def test_a_real_mosaics_spread_pointings_are_never_treated_as_strays():
    """The cut has to survive a genuine mosaic, whose tiles ARE far apart. What
    separates a tile from a junk header is company, not distance from centre."""
    frames = []
    for row in range(3):
        for col in range(3):
            for i in range(8):
                frames.append(Frame(name=f"t{row}{col}_{i}.fit", exposure=20.0,
                                    ra=300.0 + col * 0.6, dec=44.0 + row * 0.35))
    s = summarize(frames, {"naxis1": 1080, "naxis2": 1920,
                           "xpixsz": 2.9, "focal": 250.0})
    assert s.stray_pointings == 0
    assert s.is_mosaic


def test_coverage_depth_mosaic_is_far_below_frame_count():
    # Two tiles a degree apart — well beyond half the short axis (0.36 deg).
    ra = [300.0] * 20 + [301.0] * 20
    s = _survey(ra, [40.0] * 40)
    median, minimum = coverage_depth(s)
    assert median == 20, "each tile should only see its own frames"
    assert minimum == 20
    assert median < s.n_frames


# --------------------------------------------------------------------------
# the settings Siril silently drops
# --------------------------------------------------------------------------


def test_noise_weighting_is_replaced_when_overlap_norm_is_on():
    # Siril: "Weighting by noise cannot be used with overlap normalization,
    # ignoring weights" — reconcile must decide rather than let it be dropped.
    p = Proposal()
    p.set("overlap_norm", True, "")
    p.set("weight", "noise", "")
    reconcile(p)
    assert p.get("weight") == "wfwhm"
    assert p.get("overlap_norm") is True
    assert any("noise weighting" in w.lower() for w in p.warnings)


def test_noise_weighting_survives_without_overlap_norm():
    p = Proposal()
    p.set("overlap_norm", False, "")
    p.set("weight", "noise", "")
    reconcile(p)
    assert p.get("weight") == "noise"
    assert not p.warnings


def _mixed_exposure_survey(fwhm=None):
    s = Survey(n_frames=40, exposures={20.0: 20, 30.0: 20},
               filters={"LP": 40}, naxis1=1080, naxis2=1920,
               depth_median=40, depth_min=40)
    s.fwhm_by_exposure = fwhm or {}
    return s


def test_unmeasured_sharpness_never_claims_comparable_sharpness(tmp_path):
    """The read-only path skips the Siril pass that compares exposures, so the
    old `else` branch recommended noise weighting and justified it with a
    measurement nobody took. Same class as the Gaia "not checked is not not
    found" bug, but worse: it changed the recommendation, not just a warning.

    wFWHM is the safe unmeasured default because the risk is asymmetric — noise
    weighting on a set whose longer subs are softer actively drags resolution
    down, while wFWHM on a comparably-sharp set only leaves SNR on the table.
    """
    p = build_proposal(_mixed_exposure_survey(), None, tmp_path, gaia_checked=False)

    assert p.get("weight") == "wfwhm"
    assert "not measured" in p.settings["weight"].why
    assert "comparable sharpness" not in p.settings["weight"].why
    assert any("provisional" in w.lower() for w in p.warnings)


def test_measured_comparable_sharpness_picks_noise_and_shows_its_numbers(tmp_path):
    p = build_proposal(_mixed_exposure_survey({20.0: 3.10, 30.0: 3.20}), None,
                       tmp_path, gaia_checked=False)
    assert p.get("weight") == "noise"
    why = p.settings["weight"].why
    assert "measured" in why and "3.20" in why and "3.10" in why
    assert not any("provisional" in w.lower() for w in p.warnings)


def test_the_projection_follows_an_overridden_drizzle_scale(tmp_path):
    """A what-if that returns the pre-override number is worse than refusing to
    answer one. Cost scales with the square of the drizzle scale, so this is the
    figure most worth being right — and it was computed once, before overrides,
    so `--no-drizzle` came back with an unchanged 86 GB."""
    d = tmp_path / "siril"
    for i in range(4):
        _sub(d / "lights" / f"L{i}.fit", OBJECT="M81", **_GEOM)

    proposed = build_plan(d, Overrides(drizzle=2.0), deep_measure=False).proposal
    off = build_plan(d, Overrides(no_drizzle=True), deep_measure=False).proposal

    assert proposed.canvas[0] == pytest.approx(off.canvas[0] * 2, rel=0.02)
    assert off.get("drizzle_scale") == 1.0
    # 2.5x, not 4x: drizzle scales the registered sequence by the square of the
    # scale, but the CFA link and the pp_/bkg_pp_ copies stay at native size, and
    # at 1x those fixed intermediates happen to equal the registered sequence.
    # Pinning the real ratio is worth more than asserting "bigger".
    assert proposed.disk_gb / off.disk_gb == pytest.approx(2.5, rel=0.05)


def test_reprojecting_never_leaves_two_contradictory_disk_warnings(tmp_path):
    d = tmp_path / "siril"
    for i in range(4):
        _sub(d / "lights" / f"L{i}.fit", OBJECT="M81", **_GEOM)
    p = build_plan(d, Overrides(no_drizzle=True), deep_measure=False).proposal
    disk_warnings = [w for w in p.warnings if "framing=max projects" in w]
    assert len(disk_warnings) <= 1


def test_measured_softer_long_subs_still_picks_wfwhm(tmp_path):
    """The decisive case: longer subs blurrier, so noise weighting would reward
    them for having better per-frame SNR."""
    p = build_proposal(_mixed_exposure_survey({20.0: 3.09, 30.0: 4.85}), None,
                       tmp_path, gaia_checked=False)
    assert p.get("weight") == "wfwhm"
    assert "softer" in p.settings["weight"].why


# --------------------------------------------------------------------------
# empty registered frames
# --------------------------------------------------------------------------


def test_find_degenerate_flags_the_undersized_frame(tmp_path):
    for i in range(1, 11):
        size = 1_000_000 if i == 7 else 17_000_000
        (tmp_path / f"r_bkg_pp_lights_{i:05d}.fit.fz").write_bytes(b"\0" * size)
    assert find_degenerate(tmp_path, "r_bkg_pp_lights_") == [7]


def test_find_degenerate_returns_nothing_for_a_healthy_sequence(tmp_path):
    for i in range(1, 11):
        (tmp_path / f"r_bkg_pp_lights_{i:05d}.fit.fz").write_bytes(b"\0" * 17_000_000)
    assert find_degenerate(tmp_path, "r_bkg_pp_lights_") == []


def test_degenerate_frames_become_unselect_lines():
    p = Proposal()
    for k, v in (("bg_extract", True), ("rejection", "l 5 5"), ("weight", "noise"),
                 ("overlap_norm", False), ("rgb_equal", False), ("feather", 30),
                 ("out", "result"), ("compress", True)):
        p.set(k, v, "")
    ssf = build_ssf_stack("lights", p, [147])
    assert "unselect r_bkg_pp_lights_ 147 147" in ssf
    assert "-feather=30" in ssf
    assert "-overlap_norm" not in ssf


# --------------------------------------------------------------------------
# sequence naming — the prefix chain has to match what Siril actually writes
# --------------------------------------------------------------------------


def test_seq_names_with_and_without_background_extraction():
    p = Proposal()
    p.set("bg_extract", True, "")
    assert seq_names("lights", p) == ("bkg_pp_lights_", "r_bkg_pp_lights_")
    p.set("bg_extract", False, "")
    assert seq_names("lights", p) == ("pp_lights_", "r_pp_lights_")


# --------------------------------------------------------------------------
# Naztronomy-compatible output filename
# --------------------------------------------------------------------------


def test_naztronomy_name_reproduces_a_real_filename():
    from datetime import datetime
    hdr = {"OBJECT": "NGC 7000", "EXPTIME": 20.0, "STACKCNT": 810,
           "DATE-OBS": "2026-08-02T00:31:41"}
    got = naztronomy_name(hdr, True, 2.0, datetime(2026, 8, 2, 14, 22))
    assert got == "NGC_7000_810x20sec_2026-08-02_drizzle-2-0x_2026-08-02_1422_og"


# --------------------------------------------------------------------------
# frame selection — indices must be relative to the full file list, because
# `link` ingests everything and `unselect` is applied afterwards
# --------------------------------------------------------------------------


def _m15_frames():
    """243 x 10s on 2026-07-13, then 96 x 20s on 2026-07-19 — the real shape."""
    return ([Frame(name=f"a{i:04d}.fit", exposure=10.0, date="2026-07-13")
             for i in range(243)]
            + [Frame(name=f"b{i:04d}.fit", exposure=20.0, date="2026-07-19")
               for i in range(96)])


def test_only_exposure_keeps_the_right_frames_and_indices():
    frames = _m15_frames()
    kept, dropped = select_frames(frames, [10.0], None, None)
    assert len(kept) == 243
    assert all(f.exposure == 10.0 for f in kept)
    assert dropped == list(range(244, 340))     # 1-based, the 20s tail


def test_exclude_night_drops_that_session():
    kept, dropped = select_frames(_m15_frames(), None, ["2026-07-19"], None)
    assert len(kept) == 243
    assert len(dropped) == 96


def test_only_night_is_the_inverse():
    kept, dropped = select_frames(_m15_frames(), None, None, ["2026-07-19"])
    assert len(kept) == 96
    assert dropped == list(range(1, 244))


def test_no_filters_keeps_everything():
    kept, dropped = select_frames(_m15_frames(), None, None, None)
    assert len(kept) == 339 and dropped == []


def test_summary_reflects_the_selection_not_the_folder():
    frames = _m15_frames()
    kept, _ = select_frames(frames, [10.0], None, None)
    s = summarize(kept, {})
    assert s.n_frames == 243
    assert s.exposures == {10.0: 243}
    assert s.integration_min == pytest.approx(243 * 10 / 60)
    assert list(s.nights) == ["2026-07-13"]


def test_as_ranges_collapses_runs():
    assert as_ranges([1, 2, 3, 7, 8, 20]) == [(1, 3), (7, 8), (20, 20)]
    assert as_ranges([]) == []


def test_excluded_frames_become_unselect_ranges_in_phase_one():
    p = Proposal()
    for k, v in (("bg_extract", True), ("drizzle", True), ("drizzle_scale", 1.5),
                 ("pixfrac", 0.7), ("debayer", False), ("compress", True),
                 ("compress_quant", 64), ("filters", None)):
        p.set(k, v, "")
    ssf = build_ssf_register("lights", p, list(range(244, 340)))
    assert "unselect lights_ 244 339" in ssf
    assert ssf.index("link lights") < ssf.index("unselect lights_")


def test_naztronomy_name_omits_drizzle_segment_when_off():
    from datetime import datetime
    hdr = {"OBJECT": "M 109", "EXPTIME": 20.0, "STACKCNT": 343,
           "DATE-OBS": "2026-06-17T03:00:00"}
    got = naztronomy_name(hdr, False, 1.0, datetime(2026, 6, 21, 17, 15))
    assert got == "M_109_343x20sec_2026-06-17_2026-06-21_1715_og"
    assert "drizzle" not in got


# --------------------------------------------------------------------------
# M110 integration: layout, the read-only path, the handoff
# --------------------------------------------------------------------------


# Enough header for the surveyor to derive a plate scale and therefore a canvas
# and a disk projection. Seestar S50 numbers.
_GEOM = {"XPIXSZ": 2.9, "FOCALLEN": 250.0}


def _sub(path, **cards):
    """A tiny FITS frame with the cards the surveyor and handoff actually read."""
    from astropy.io import fits
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="float32"))
    h.header["EXPTIME"] = cards.pop("EXPTIME", 20.0)
    h.header["DATE-OBS"] = cards.pop("DATE_OBS", "2026-05-25T22:00:00")
    for k, v in cards.items():
        h.header[k.replace("_", "-")] = v
    h.writeto(path)
    return path


def test_resolve_layout_accepts_a_sandbox_a_lights_dir_and_a_loose_folder(tmp_path):
    sandbox = tmp_path / "siril"
    _sub(sandbox / "lights" / "a.fit")
    assert resolve_layout(sandbox) == (sandbox.resolve(), (sandbox / "lights").resolve())
    # Pointed straight at lights/ — Siril's cwd must still be its parent.
    assert resolve_layout(sandbox / "lights")[0] == sandbox.resolve()
    # A loose folder of subs, never in a store. `.fits` counts too (Dwarf writes it).
    loose = tmp_path / "loose"
    _sub(loose / "b.fits")
    assert resolve_layout(loose) == (loose.parent.resolve(), loose.resolve())


def test_resolve_layout_raises_rather_than_exiting(tmp_path):
    """The original script `sys.exit`d here, which would kill an importing process."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(StackingError):
        resolve_layout(empty)


def test_target_for_finds_the_capture_target_and_declines_outside_the_store(
        tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    (tmp_path / "Images" / "M81 M82" / "siril" / "LP").mkdir(parents=True)
    assert target_for(config.siril_dir("M81 M82")) == "M81 M82"
    assert target_for(config.siril_job_dir("M81 M82", "LP")) == "M81 M82"
    assert target_for(tmp_path / "elsewhere") is None


def test_the_read_only_path_writes_nothing_and_says_what_it_skipped(tmp_path):
    """`deep_measure=False` is what makes the assistant tool honest: pure header
    reads, and the two Siril-backed checks are declared missing rather than
    silently reported as negative."""
    d = tmp_path / "siril"
    for i in range(3):
        _sub(d / "lights" / f"Light_{i}.fit", OBJECT="M27", FILTER="LP")
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}

    plan = build_plan(d, Overrides(), deep_measure=False)

    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")} == before
    assert plan.survey.n_frames == 3
    assert any("headers only" in w for w in plan.proposal.warnings)
    # "not checked" must not be reported as "not found".
    assert not any("catalogue not found" in w for w in plan.proposal.warnings)
    assert "stack" in plan.stack_ssf and "seqapplyreg" in plan.register_ssf


def test_as_json_is_serialisable_and_carries_the_proposal(tmp_path):
    d = tmp_path / "siril"
    _sub(d / "lights" / "Light_0.fit", OBJECT="M27")
    payload = build_plan(d, deep_measure=False).as_json()
    json.loads(json.dumps(payload, default=str))          # what the CLI/tool emit
    assert payload["survey"]["n_frames"] == 1
    assert "rejection" in payload["settings"]


# ── the handoff ──────────────────────────────────────────────────────────────

def test_handoff_hardlinks_the_stack_and_records_its_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    sandbox = config.siril_dir("M27")
    stack = _sub(sandbox / "M27_1746x20sec_og.fit",
                 OBJECT="M27", FILTER="LP", STACKCNT=1746, LIVETIME=34920.0,
                 DATE="2026-08-17T11:13:00")

    dest = apply_handoff(stack)

    assert dest == config.astrowizard_dir("M27") / stack.name
    assert dest.stat().st_ino == stack.stat().st_ino     # hardlinked, costs no disk
    prov = json.loads((dest.parent / (stack.name + ".src.json")).read_text())
    # Provenance comes from what Siril recorded in the header, never from mtime —
    # ingest and import both copy bytes, so mtime is copy time and lies.
    assert prov["source"] == stack.name
    assert prov["frames"] == 1746
    assert prov["stacked_at"] == "2026-08-17T11:13:00"
    assert prov["object"] == "M27"


def test_handoff_refuses_an_unknown_tool_and_a_path_outside_the_store(
        tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    inside = _sub(config.siril_dir("M27") / "s.fit")
    with pytest.raises(StackingError, match="Unknown handoff target"):
        apply_handoff(inside, "pixinsight")
    outside = _sub(tmp_path / "elsewhere" / "s.fit")
    with pytest.raises(StackingError, match="not inside the M110 store"):
        apply_handoff(outside)


def test_handoff_targets_never_offers_the_stacker_as_a_destination():
    """siril is the head of the chain, not somewhere a finished stack is sent."""
    assert "siril" not in handoff_targets()
    assert set(handoff_targets()) <= set(config.SANDBOX_DIRNAMES)


def test_handoff_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    stack = _sub(config.siril_dir("M27") / "s.fit", OBJECT="M27")
    assert apply_handoff(stack) == apply_handoff(stack)   # re-running must not raise


def test_every_siril_spawn_sanitizes_the_child_environment():
    """Asserted on the source, because the failure is invisible from a dev run.

    A frozen M110 exports QT_PLUGIN_PATH / QML*_IMPORT_PATH / _MEI* into its
    children. Siril's own bundled Python then loads our Qt alongside its PyQt6 —
    two Qt sets in one process, objc duplicate-class warnings, then SIGABRT.
    Running from source those vars are unset, so a passing manual test proves
    nothing; only the packaged build fails, and only for a user.
    """
    import ast
    import inspect

    from m110 import stacking

    src = inspect.getsource(stacking)
    spawns = [
        node for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("run", "Popen", "call", "check_output")
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    assert spawns, "no subprocess spawns found — did the module move?"
    for node in spawns:
        kwargs = {k.arg for k in node.keywords}
        assert "env" in kwargs, (
            f"subprocess spawn at line {node.lineno} inherits our environment; "
            "it must pass env=launch._child_env()")
