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
    as_ranges,
    build_ssf_register,
    build_ssf_stack,
    coverage_depth,
    drizzle_for,
    find_degenerate,
    naztronomy_name,
    apply_handoff,
    build_plan,
    handoff_candidates,
    handoff_targets,
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


# ── choosing a stack to hand off (ROADMAP 14a) ───────────────────────────────

def _stack(path, **cards):
    cards.setdefault("STACKCNT", 100)
    cards.setdefault("LIVETIME", 6000.0)
    return _sub(path, **cards)


def test_candidates_span_the_three_tiers_a_stack_can_live_in(tmp_path, monkeypatch):
    """A finished stack legitimately sits in any of them, and the sandbox one is
    the common case right after a run — omitting it would mean the handoff could
    not be used until an import the user may not want yet."""
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    t = "M27"
    _stack(config.stacks_dir(t) / "imported.fit", DATE="2026-08-01T00:00:00")
    _stack(config.seestar_stacks_dir(t) / "Stacked_226.fit", DATE="2026-07-01T00:00:00")
    _stack(config.siril_dir(t) / "lights" / "a.fit")          # an input, never offered
    _stack(config.siril_dir(t) / "fresh.fit", DATE="2026-08-19T00:00:00")

    got = handoff_candidates(t)

    # Newest stacked first, by the header's own DATE — not by tier and not by
    # mtime, which is copy time for anything ingest or import put there.
    assert [c.name for c in got] == ["fresh.fit", "imported.fit", "Stacked_226.fit"]
    assert {c.tier for c in got} == {"stacks", "seestar-stacks", "siril"}
    assert "a.fit" not in {c.name for c in got}, "lights/ is an input, not a deliverable"
    assert got[0].frames == 100 and got[0].integration_min == 100.0


def test_intermediates_are_never_offered_as_a_stack(tmp_path, monkeypatch):
    """They carry the same STACKCNT and LIVETIME as the stack they came from, so
    they sort to the very top on merit and are exactly wrong — derived layers, not
    the image. Seen on a real NGC 6543 sandbox, where the two most recent files
    were precisely that pair. Filtered through the shared `hints` vocabulary, so a
    user's edits to it apply here too."""
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    t = "NGC 6543"
    sb = config.siril_dir(t)
    _stack(sb / "C_6_854x20sec_og.fit", DATE="2026-08-20T15:37:08")
    _stack(sb / "starless_C_6_854x20sec_og.fit", DATE="2026-08-20T15:40:36")
    _stack(sb / "starmask_C_6_854x20sec_og.fit", DATE="2026-08-20T15:40:36")

    assert [c.name for c in handoff_candidates(t)] == ["C_6_854x20sec_og.fit"]


def test_a_candidate_already_handed_over_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    t = "M27"
    stack = _stack(config.stacks_dir(t) / "s.fit", DATE="2026-08-01T00:00:00")
    assert handoff_candidates(t)[0].already is False

    apply_handoff(stack)
    assert handoff_candidates(t)[0].already is True


def test_a_stack_with_an_unreadable_header_is_still_offered(tmp_path, monkeypatch):
    """It may be perfectly good. Showing it without its facts beats hiding it,
    and an undated stack sorts last rather than being dropped."""
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    t = "M27"
    config.stacks_dir(t).mkdir(parents=True)
    (config.stacks_dir(t) / "not-really-fits.fit").write_text("junk")
    _stack(config.stacks_dir(t) / "good.fit", DATE="2026-08-01T00:00:00")

    got = handoff_candidates(t)
    assert [c.name for c in got] == ["good.fit", "not-really-fits.fit"]
    assert got[-1].frames is None and got[-1].size_bytes > 0


def test_candidates_are_read_only_and_reject_an_unknown_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    t = "M27"
    _stack(config.stacks_dir(t) / "s.fit")
    before = {p: p.stat().st_mtime_ns for p in (tmp_path / "Images").rglob("*")}

    handoff_candidates(t)

    assert {p: p.stat().st_mtime_ns for p in (tmp_path / "Images").rglob("*")} == before
    assert not config.astrowizard_dir(t).exists(), "listing must not create the sandbox"
    with pytest.raises(StackingError, match="Unknown handoff target"):
        handoff_candidates(t, "pixinsight")


@pytest.mark.parametrize("history,stretched", [
    # Straight off the stacker — Siril's own wording.
    (["mean stacking with winsorized sigma clipping rejection (low=3.000 high=3",
      ".000), additive+scaling normalized input, normalized output"], False),
    # Linear steps. None of these disqualify a stack, and treating them as if
    # they did would rule out perfectly good inputs.
    (["Background extraction (Correction: Subtraction)", "Plate Solve",
      "Photometric CC (algorithm: SPCC)", "GraXpert AI deconvolve: strength 0.50"],
     False),
    # The real case: a file named `_denoise` whose history shows a stretch three
    # entries back. The name says linear step, the header says otherwise.
    (["Background extraction (Correction: Subtraction)", "Plate Solve",
      "VeraLux v1.5.2 Stretch", "GraXpert AI denoise: strength 0.76"], True),
    (["Histogram Transformation"], True),
    (["VeraLux Curves", "SCNR (type=maximum neutral)"], True),
    (["Asinh stretch (10.0)"], True),
])
def test_a_stretch_is_read_from_history_not_from_the_filename(history, stretched):
    from m110.stacking import _is_stretched
    assert _is_stretched(history) is stretched


def test_candidates_report_whether_the_stack_is_still_linear(tmp_path, monkeypatch):
    """AstroWizard starts at background extraction and stretching, so a stretched
    input is the wrong thing — and `stacks/` accumulates both side by side."""
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    t = "M27"
    _stack(config.stacks_dir(t) / "og.fit", DATE="2026-08-01T00:00:00",
           HISTORY="mean stacking with winsorized sigma clipping rejection")
    _stack(config.stacks_dir(t) / "denoise.fit", DATE="2026-08-19T00:00:00",
           HISTORY="VeraLux v1.5.2 Stretch")
    _stack(config.stacks_dir(t) / "nohistory.fit", DATE="2026-07-01T00:00:00")

    by_name = {c.name: c for c in handoff_candidates(t)}
    assert by_name["og.fit"].stretched is False
    assert by_name["denoise.fit"].stretched is True
    # Nothing recorded is not the same as "linear" — say so rather than guess.
    assert by_name["nohistory.fit"].stretched is None


def test_the_sidecar_records_whether_what_was_handed_over_was_linear(
        tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    stack = _stack(config.stacks_dir("M27") / "s.fit", DATE="2026-08-01T00:00:00",
                   HISTORY="VeraLux v1.5.2 Stretch")
    dest = apply_handoff(stack)
    prov = json.loads((dest.parent / (stack.name + ".src.json")).read_text())
    assert prov["stretched"] is True


def test_no_candidates_for_a_target_with_nothing_stacked(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "Images")
    _sub(config.lights_dir("M27") / "Light_0.fit")
    assert handoff_candidates("M27") == []
