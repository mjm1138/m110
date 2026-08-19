"""Tests for build_derived.py pure functions:
- parse_size_arcmin (catalog size string → max dimension in arcmin)
- default_star_removal_recommended (catalog entry → bool)
- recommend_star_removal_for_folder (slugs + catalog + override → bool)
"""
import pytest

from m110 import config, build_derived
from m110.build_derived import (
    parse_size_arcmin,
    default_star_removal_recommended,
    recommend_star_removal_for_folder,
    STAR_REMOVAL_MIN_ARCMIN,
)


def test_refresh_on_empty_library_does_not_fail(tmp_path, monkeypatch):
    """A brand-new store seeds an empty library.toml (no [catalog] table). The first-
    launch refresh must not KeyError on it (surfaced as "Sync failed" in the status
    bar of the packaged app on an empty store)."""
    from tests._helpers import seed_root
    from m110 import refresh
    from m110 import derived
    seed_root(tmp_path, monkeypatch)          # bootstraps a zero-capture store
    refresh.run_refresh(render=False)         # must not raise (KeyError: 'catalog')
    assert derived.totals_by_slug() == {}


# ── Seestar-stack-only captures (no lights → no sessions) ────────────────────

def test_seestar_only_target_is_captured(tmp_path, monkeypatch):
    images = tmp_path / "Images"
    (images / "M57" / "seestar-stacks").mkdir(parents=True)
    (images / "Empty").mkdir()                       # bare folder, not a capture
    monkeypatch.setattr(config, "IMAGES_DIR", images)
    totals = build_derived.build_totals({}, [])      # no sessions at all
    # the Seestar-only target is surfaced as a zero-integration capture
    assert "M57" in totals["by_folder"]
    assert totals["by_slug"]["m57"]["status"] == "initial"
    assert totals["by_slug"]["m57"]["integration_min"] == 0.0
    # a folder without any capture subdir is NOT a phantom capture
    assert "Empty" not in totals["by_folder"]


# ── build_processing: a finished/ render counts as processed output ──────────

def test_finished_render_is_not_not_processed(tmp_path, monkeypatch):
    """An object whose only processed output is a finished/ raster render (the
    typical imported-Astronomy-library shape: no raw Siril stack) must classify
    as up_to_date / out_of_date — never not_processed."""
    images = tmp_path / "Images"
    tgt = images / "NGC 7023"
    (tgt / "lights").mkdir(parents=True)
    (tgt / "lights" / "Light_a.fit").write_text("x")
    (tgt / "finished").mkdir()
    render = tgt / "finished" / "NGC_7023_processed.png"
    render.write_text("img")
    # make the finished render newer than the light so it reads up_to_date
    import os, time
    os.utime(tgt / "lights" / "Light_a.fit", (time.time() - 100, time.time() - 100))
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    totals = build_derived.build_totals({}, [{
        "object_dir": "NGC 7023", "slugs": ["ngc-7023"], "frames": 1,
        "integration_min": 1.0, "date": "2026-06-28", "filter": "IRCUT",
        "exposure_s": 20,
    }])
    proc = build_derived.build_processing(totals, None, {})
    assert proc["folders"]["NGC 7023"]["status"] == "up_to_date"
    assert proc["counts"]["not_processed"] == 0


# ── build_processing: ready_for_import flag (finished Siril output waiting) ──

def test_ready_for_import_flag(tmp_path, monkeypatch):
    """A target with unimported output in its siril/ sandbox gets
    ready_for_import=True (drives the Processing page's "Ready to import" group)."""
    images = tmp_path / "Images"
    tgt = images / "M51"
    (tgt / "lights").mkdir(parents=True)
    (tgt / "lights" / "Light_a.fit").write_text("x")
    (tgt / "siril").mkdir()
    (tgt / "siril" / "M51_x_processed.png").write_text("png")   # unimported deliverable
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    totals = build_derived.build_totals({}, [{
        "object_dir": "M51", "slugs": ["m51"], "frames": 1,
        "integration_min": 1.0, "date": "2026-06-28", "filter": "IRCUT",
        "exposure_s": 20,
    }])
    proc = build_derived.build_processing(totals, None, {})
    assert proc["folders"]["M51"]["ready_for_import"] is True


# ── build_processing: rejection% + freshness use the stack DATE, not the total ──

def _write_stack(folder, stackcnt, date, exp_s=20):
    """Write a minimal FITS stack carrying STACKCNT / LIVETIME / DATE headers."""
    from astropy.io import fits
    import numpy as np
    (folder / "stacks").mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    hdu.header["STACKCNT"] = stackcnt
    hdu.header["LIVETIME"] = stackcnt * exp_s
    hdu.header["EXPTIME"] = exp_s
    hdu.header["DATE"] = date
    hdu.writeto(folder / "stacks" / "stacked.fit", overwrite=True)


def _sess(target, date, frames):
    return {"object_dir": target, "slugs": [target.lower()], "frames": frames,
            "integration_min": frames * 20 / 60, "date": date,
            "filter": "IRCUT", "exposure_s": 20}


def test_rejection_measured_against_frames_present_at_stack_time(tmp_path, monkeypatch):
    """A stack of 90/100 pre-stack frames is 10% rejection — even after 200 more
    frames are captured. The later frames are unintegrated backlog, not rejects
    (the ~/Astronomy bug: rejection was computed against the running total)."""
    images = tmp_path / "Images"
    tgt = images / "M99"
    (tgt / "lights").mkdir(parents=True)
    _write_stack(tgt, stackcnt=90, date="2026-05-01T12:00:00")
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = [_sess("M99", "2026-04-20", 100),   # present when stacked
                _sess("M99", "2026-06-01", 200)]    # captured since
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    f = proc["folders"]["M99"]
    sm = f["stack_meta"]
    assert sm["frames_at_stack"] == 100            # only the pre-stack session
    assert sm["stack_rejection_pct"] == 10         # 1 - 90/100, not 1 - 90/300
    assert f["status"] == "out_of_date"            # 200 frames captured after the stack
    assert f["new_lights_since_stack"] == 200


def test_stack_read_from_working_files(tmp_path, monkeypatch):
    """The real Siril stack often lands in working_files/ (the ingest lights-guard
    diverts processing-product .fit there). It's still read for In-stack / "+ new" /
    rejection from its STACKCNT/DATE header — the M10 live-library case, where the
    Processing view otherwise showed "—" in-stack and an mtime-inflated backlog."""
    from astropy.io import fits
    import numpy as np
    images = tmp_path / "Images"
    tgt = images / "M10"
    (tgt / "lights").mkdir(parents=True)
    (tgt / "finished").mkdir()
    (tgt / "finished" / "M_10_processed.png").write_text("png")   # processed output exists
    wf = tgt / "working_files"
    wf.mkdir()
    hdu = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    hdu.header["STACKCNT"] = 301
    hdu.header["LIVETIME"] = 301 * 20
    hdu.header["EXPTIME"] = 20
    hdu.header["DATE"] = "2026-06-12T20:00:00"
    hdu.writeto(wf / "M_10_301x20sec_2026-06-11_drizzle_2026-06-12_og.fit")
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = [_sess("M10", "2026-06-10", 336),   # present when stacked (<= 06-12)
                _sess("M10", "2026-06-15", 177)]    # captured after the stack date
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    f = proc["folders"]["M10"]
    sm = f["stack_meta"]
    assert sm and sm["stack_frames"] == 301                 # in-stack read from working_files/
    assert f["new_lights_since_stack"] == 177               # date-based, not mtime fallback
    assert sm["stack_rejection_pct"] == round((1 - 301 / 336) * 100)   # 10%


# ── "latest stack" = header DATE, not file mtime ──────────────────────────

def _write_named_stack(folder, name, stackcnt, date, *, mtime=None,
                       subdir="stacks", exp_s=20):
    """Write a stack under `subdir` with an explicit filename and, optionally, a
    file mtime detached from its header DATE (what a byte-copy produces)."""
    from astropy.io import fits
    import numpy as np
    import os
    d = folder / subdir if subdir else folder
    d.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    hdu.header["STACKCNT"] = stackcnt
    hdu.header["LIVETIME"] = stackcnt * exp_s
    hdu.header["EXPTIME"] = exp_s
    if date:
        hdu.header["DATE"] = date
    path = d / name
    hdu.writeto(path, overwrite=True)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_latest_stack_picked_by_header_date_not_mtime(tmp_path, monkeypatch):
    """Two real stacks, mtime order inverted against header DATE — the superseded
    one was re-copied into stacks/ later, so it carries the newest mtime.

    The live-library M71 case: the 118-frame stack (DATE 06-10, copied 07-16) was
    beating the 393-frame one (DATE 07-10), which reported In-stack 118 instead of
    393 and "+ new" 417 instead of 123. mtime is copy time, not provenance."""
    images = tmp_path / "Images"
    tgt = images / "M71"
    (tgt / "lights").mkdir(parents=True)
    # Superseded by content, newest on disk.
    _write_named_stack(tgt, "M_71_118x20sec_processed.fit", 118,
                       "2026-06-10T19:51:29", mtime=1_784_260_770)   # 2026-07-16
    # Current by content, older on disk.
    _write_named_stack(tgt, "M_71_393x20sec_finished.fit", 393,
                       "2026-07-10T20:55:57", mtime=1_783_716_999)   # 2026-07-10
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = [_sess("M71", "2026-06-10", 123), _sess("M71", "2026-06-11", 93),
                _sess("M71", "2026-06-12", 116), _sess("M71", "2026-07-07", 85),
                _sess("M71", "2026-07-12", 123)]          # the only unintegrated one
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    f = proc["folders"]["M71"]
    sm = f["stack_meta"]
    assert sm["stack_file"] == "M_71_393x20sec_finished.fit"
    assert sm["stack_frames"] == 393
    assert sm["frames_at_stack"] == 417                    # 123+93+116+85, on/before 07-10
    assert sm["stack_rejection_pct"] == 6                  # 1 - 393/417, not 1 - 118/123
    assert f["new_lights_since_stack"] == 123              # not 417
    assert f["status"] == "out_of_date"


def test_processing_derivative_yields_identical_numbers(tmp_path, monkeypatch):
    """A starless/crop derivative inherits its parent's STACKCNT and LIVETIME, so
    it is arithmetically interchangeable with the parent. Selection is therefore
    deliberately *not* filename-filtered — and the DATE sort lands on the final
    product anyway, since the last processing step is written last."""
    images = tmp_path / "Images"
    tgt = images / "M51"
    (tgt / "lights").mkdir(parents=True)
    _write_named_stack(tgt, "M_51_1560x20sec_crop.fit", 1560, "2026-05-28T04:48:45")
    _write_named_stack(tgt, "starmask_M_51_1560x20sec_crop.fit", 1560, "2026-05-28T04:51:18")
    _write_named_stack(tgt, "M_51_1560x20sec_processed.fit", 1560, "2026-05-28T05:08:08")
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = [_sess("M51", "2026-05-01", 1700)]
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    sm = proc["folders"]["M51"]["stack_meta"]
    assert sm["stack_file"] == "M_51_1560x20sec_processed.fit"   # latest DATE wins
    assert sm["stack_frames"] == 1560                            # same either way


def test_undated_stack_falls_back_to_mtime_and_loses_to_a_dated_one(tmp_path, monkeypatch):
    """No header DATE (pre-Siril / hand-made stack) → mtime is the only signal left,
    but any dated stack still outranks it: a real DATE beats a guess."""
    images = tmp_path / "Images"
    tgt = images / "M92"
    (tgt / "lights").mkdir(parents=True)
    _write_named_stack(tgt, "undated_newest.fit", 500, None, mtime=1_790_000_000)
    _write_named_stack(tgt, "undated_older.fit", 400, None, mtime=1_700_000_000)
    monkeypatch.setattr(config, "IMAGES_DIR", images)
    sessions = [_sess("M92", "2026-05-01", 600)]
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    assert proc["folders"]["M92"]["stack_meta"]["stack_frames"] == 500   # mtime fallback

    # A dated stack wins even with the oldest mtime on disk.
    _write_named_stack(tgt, "dated.fit", 450, "2026-06-01T00:00:00", mtime=1_600_000_000)
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    assert proc["folders"]["M92"]["stack_meta"]["stack_frames"] == 450


# ── combined targets: a stack covering only part of them is demoted (OBJECT) ──

def _write_object_stack(folder, name, stackcnt, date, obj, *, exp_s=20):
    """A stack carrying an OBJECT header — the signal that says which object(s) it
    actually covers."""
    from astropy.io import fits
    import numpy as np
    (folder / "stacks").mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(np.zeros((2, 2), dtype="uint16"))
    hdu.header["STACKCNT"] = stackcnt
    hdu.header["LIVETIME"] = stackcnt * exp_s
    hdu.header["EXPTIME"] = exp_s
    hdu.header["DATE"] = date
    if obj is not None:
        hdu.header["OBJECT"] = obj
    hdu.writeto(folder / "stacks" / name, overwrite=True)


def _combined_sessions(target="M81 M82"):
    return [{"object_dir": target, "slugs": ["m81", "m82"], "frames": 3000,
             "integration_min": 1000.0, "date": "2026-05-01",
             "filter": "LP", "exposure_s": 20},
            {"object_dir": target, "slugs": ["m81", "m82"], "frames": 1799,
             "integration_min": 600.0, "date": "2026-06-04",
             "filter": "LP", "exposure_s": 20}]


def test_single_object_stack_demoted_on_a_combined_target(tmp_path, monkeypatch):
    """The live `M81 M82` case: an `OBJECT = "M 81"` 271-frame stack sat in the
    combined folder and carried the newest header DATE, so it was selected and
    measured against the *pair's* 4799 captured frames — 94% "rejected", nonsense.
    OBJECT is header truth: a strict subset of the target's objects is not a stack
    of that target, so it loses to one that covers both."""
    images = tmp_path / "Images"
    tgt = images / "M81 M82"
    (tgt / "lights").mkdir(parents=True)
    _write_object_stack(tgt, "M81_M82_1983x20sec.fit", 1983,
                        "2026-06-04T15:23:47", "M81 M82")
    _write_object_stack(tgt, "M_81_271x20sec_og.fit", 271,
                        "2026-06-04T15:34:49", "M 81")     # newest DATE, but partial
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = _combined_sessions()
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    sm = proc["folders"]["M81 M82"]["stack_meta"]
    assert sm["stack_file"] == "M81_M82_1983x20sec.fit"
    assert sm["stack_frames"] == 1983
    assert sm["stack_rejection_pct"] == 59          # 1 - 1983/4799, not 1 - 271/4799


def test_partial_stack_still_used_when_it_is_the_only_one(tmp_path, monkeypatch):
    """Demote, don't drop — a partial stack beats no stack metadata at all."""
    images = tmp_path / "Images"
    tgt = images / "M81 M82"
    (tgt / "lights").mkdir(parents=True)
    _write_object_stack(tgt, "M_81_271x20sec_og.fit", 271,
                        "2026-06-04T15:34:49", "M 81")
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = _combined_sessions()
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    assert proc["folders"]["M81 M82"]["stack_meta"]["stack_frames"] == 271


@pytest.mark.parametrize("obj", [None, "", "Unknown", "M 51"])
def test_no_signal_or_unrelated_object_never_demotes(tmp_path, monkeypatch, obj):
    """Absence of evidence isn't evidence: a missing/unrecognized OBJECT keeps its
    place. An *unrelated* object is left alone too — that's a misfiled stack, a
    different problem from a partial one, and not this rule's job to guess at."""
    images = tmp_path / "Images"
    tgt = images / "M81 M82"
    (tgt / "lights").mkdir(parents=True)
    _write_object_stack(tgt, "older_full.fit", 1983, "2026-05-01T00:00:00", "M81 M82")
    _write_object_stack(tgt, "newer_unknown.fit", 500, "2026-06-04T00:00:00", obj)
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = _combined_sessions()
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    assert proc["folders"]["M81 M82"]["stack_meta"]["stack_file"] == "newer_unknown.fit"


def test_single_object_target_is_unaffected_by_the_partial_rule(tmp_path, monkeypatch):
    """No non-empty strict subset of a one-object target exists, so the rule can
    never fire there — an `OBJECT = "M 71"` stack in the M71 folder is the norm."""
    images = tmp_path / "Images"
    tgt = images / "M71"
    (tgt / "lights").mkdir(parents=True)
    _write_object_stack(tgt, "M_71_393x20sec.fit", 393, "2026-07-10T20:55:57", "M 71")
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = [_sess("M71", "2026-07-01", 417)]
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    assert proc["folders"]["M71"]["stack_meta"]["stack_frames"] == 393


def test_status_up_to_date_when_all_frames_precede_stack(tmp_path, monkeypatch):
    images = tmp_path / "Images"
    tgt = images / "M100"
    (tgt / "lights").mkdir(parents=True)
    _write_stack(tgt, stackcnt=180, date="2026-06-10T12:00:00")
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = [_sess("M100", "2026-05-01", 100), _sess("M100", "2026-06-09", 100)]
    totals = build_derived.build_totals({}, sessions)
    proc = build_derived.build_processing(totals, None, {}, sessions)
    f = proc["folders"]["M100"]
    assert f["status"] == "up_to_date"
    assert f["new_lights_since_stack"] == 0
    assert f["stack_meta"]["frames_at_stack"] == 200   # both sessions preceded the stack


# ── parse_size_arcmin ────────────────────────────────────────────────────────

class TestParseSizeArcmin:
    def test_simple_arcminutes(self):
        assert parse_size_arcmin("11'×7'") == 11.0

    def test_picks_longer_axis(self):
        # Returns max, not first
        assert parse_size_arcmin("3'×8'") == 8.0

    def test_degrees_converted_to_arcmin(self):
        assert parse_size_arcmin("3°×1°") == 180.0  # 3° = 180'

    def test_mixed_units(self):
        # Hypothetical mix — degrees and arcmin in one string
        assert parse_size_arcmin("1°×30'") == 60.0  # 1° wins

    def test_single_dimension(self):
        # Some catalog entries are just one number (e.g. "20'" for a globular)
        assert parse_size_arcmin("20'") == 20.0

    def test_decimal_values(self):
        assert parse_size_arcmin("1.5°") == 90.0
        assert parse_size_arcmin("8.5'×4.2'") == 8.5

    def test_empty_string(self):
        assert parse_size_arcmin("") == 0.0

    def test_no_dimensions_found(self):
        # String without unit markers
        assert parse_size_arcmin("unknown") == 0.0

    def test_none_input(self):
        # parse_size_arcmin should tolerate None (some catalog entries miss size)
        assert parse_size_arcmin(None) == 0.0


# ── default_star_removal_recommended ─────────────────────────────────────────

class TestDefaultStarRemoval:
    # Galaxies — type "galaxy"
    def test_large_galaxy_recommended(self):
        entry = {"type": "galaxy", "size": "27'×14'"}
        assert default_star_removal_recommended(entry) is True

    def test_small_galaxy_not_recommended(self):
        # 5' < 8' threshold
        entry = {"type": "galaxy", "size": "5'×3'"}
        assert default_star_removal_recommended(entry) is False

    def test_threshold_boundary_inclusive(self):
        # Exactly 8' should qualify (>= threshold)
        entry = {"type": "galaxy", "size": "8'×6'"}
        assert default_star_removal_recommended(entry) is True

    def test_galaxy_group(self):
        # "galaxy_group" contains "galaxy" → matches keyword
        entry = {"type": "galaxy_group", "size": "1.5°"}
        assert default_star_removal_recommended(entry) is True

    # Nebulae — catalog uses shorthand: "emission", "planetary", "reflection"
    def test_emission_nebula_large(self):
        entry = {"type": "emission", "size": "85'×60'"}  # M42
        assert default_star_removal_recommended(entry) is True

    def test_planetary_nebula_large(self):
        entry = {"type": "planetary", "size": "8'×6'"}  # M27
        assert default_star_removal_recommended(entry) is True

    def test_planetary_nebula_small(self):
        entry = {"type": "planetary", "size": "4'×3'"}  # M57
        assert default_star_removal_recommended(entry) is False

    def test_supernova_remnant(self):
        # "emission_snr" should match via the "emission" or "snr" keyword
        entry = {"type": "emission_snr", "size": "7'×5'"}
        # 7 < 8 → not recommended on size grounds, but type would qualify
        assert default_star_removal_recommended(entry) is False

    def test_reflection_nebula(self):
        entry = {"type": "reflection", "size": "10'×8'"}
        assert default_star_removal_recommended(entry) is True

    # Clusters — never recommended (no type keyword match)
    def test_globular_never_recommended(self):
        # Even at huge sizes, globulars are point sources of stars
        entry = {"type": "globular", "size": "20'"}
        assert default_star_removal_recommended(entry) is False

    def test_open_cluster_never_recommended(self):
        entry = {"type": "open_cluster", "size": "95'"}  # M44 size
        assert default_star_removal_recommended(entry) is False

    # Edge cases
    def test_missing_type(self):
        entry = {"size": "20'×10'"}
        assert default_star_removal_recommended(entry) is False

    def test_missing_size(self):
        entry = {"type": "galaxy"}
        assert default_star_removal_recommended(entry) is False

    def test_empty_dict(self):
        assert default_star_removal_recommended({}) is False


# ── recommend_star_removal_for_folder ────────────────────────────────────────

class TestFolderRecommendation:
    @pytest.fixture
    def catalog(self):
        """Minimal catalog fixture matching real entries."""
        return {
            "m51": {"type": "galaxy", "size": "11'×7'"},       # qualifies
            "m81": {"type": "galaxy", "size": "27'×14'"},      # qualifies
            "m82": {"type": "galaxy", "size": "11'×4'"},       # qualifies
            "m13": {"type": "globular", "size": "20'"},        # never
            "m92": {"type": "globular", "size": "14'"},        # never
            "m57": {"type": "planetary", "size": "4'×3'"},     # too small
            "m97": {"type": "planetary", "size": "3'"},        # too small
        }

    def test_single_qualifying_slug(self, catalog):
        assert recommend_star_removal_for_folder(["m51"], catalog, None) is True

    def test_single_non_qualifying_slug(self, catalog):
        assert recommend_star_removal_for_folder(["m13"], catalog, None) is False

    def test_multi_slug_any_qualifies(self, catalog):
        # M81 M82 — both qualify
        assert recommend_star_removal_for_folder(
            ["m81", "m82"], catalog, None
        ) is True

    def test_multi_slug_some_qualify(self, catalog):
        # If a folder fed both M51 (galaxy ≥8') and M97 (small planetary),
        # the ANY-qualifies rule says yes
        assert recommend_star_removal_for_folder(
            ["m51", "m97"], catalog, None
        ) is True

    def test_multi_slug_none_qualify(self, catalog):
        # M97 alone wouldn't qualify; M57 alone wouldn't either
        assert recommend_star_removal_for_folder(
            ["m97", "m57"], catalog, None
        ) is False

    def test_override_true_wins_over_default_false(self, catalog):
        # M97 wouldn't qualify by default, but override forces True
        assert recommend_star_removal_for_folder(
            ["m97"], catalog, override=True
        ) is True

    def test_override_false_wins_over_default_true(self, catalog):
        # M51 qualifies by default, but override forces False
        assert recommend_star_removal_for_folder(
            ["m51"], catalog, override=False
        ) is False

    def test_override_none_falls_through_to_default(self, catalog):
        # Explicit None == "no override, use default"
        assert recommend_star_removal_for_folder(
            ["m51"], catalog, override=None
        ) is True

    def test_unknown_slug_does_not_qualify(self, catalog):
        # Slug missing from catalog → no entry → no recommendation
        assert recommend_star_removal_for_folder(
            ["nonexistent"], catalog, None
        ) is False

    def test_empty_slug_list(self, catalog):
        # No slugs → no recommendation
        assert recommend_star_removal_for_folder([], catalog, None) is False


# ── threshold sanity check ───────────────────────────────────────────────────

class TestThresholdConfig:
    def test_threshold_is_8(self):
        # If someone bumps the threshold, this fails loudly so the change is
        # explicit (rather than a silent tightening / loosening).
        assert STAR_REMOVAL_MIN_ARCMIN == 8.0


def test_parse_size_dims():
    from m110.build_derived import parse_size_dims
    assert parse_size_dims("27'×14'") == (27.0, 14.0)
    assert parse_size_dims("3°×1°") == (180.0, 60.0)
    maj, minr = parse_size_dims('49"')                    # arcsec (M40)
    assert abs(maj - 49 / 60) < 1e-9 and minr == maj
    assert parse_size_dims("110'") == (110.0, 110.0)      # single dim = circular
    assert parse_size_dims("") is None


def _sess_obs(target, date, frames, first_obs, last_obs):
    """A session carrying its real UTC window, as `scan_sessions` now writes it."""
    return {**_sess(target, date, frames),
            "first_obs": first_obs, "last_obs": last_obs}


def test_frames_shot_the_same_night_as_the_stack_are_backlog_not_history(
        tmp_path, monkeypatch):
    """The M16 case: 285 frames, 79 in the stack, reported "up to date".

    `date` is the *observing night's label*, not a calendar day of the frames'
    timestamps — subs shot after local midnight keep the previous evening's
    label. So the night labelled 2026-08-17 is made entirely of frames stamped
    2026-08-18, and truncating the stack's `DATE` to a day and asking
    `date <= stack_date` filed all 202 of them as "present when stacked".
    Two wrong numbers followed: no backlog, and a 72% rejection rate that was
    really the backlog sitting in the denominator.
    """
    images = tmp_path / "Images"
    tgt = images / "M16"
    (tgt / "lights").mkdir(parents=True)
    _write_stack(tgt, stackcnt=79, date="2026-08-17T18:55:10")
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = [
        # Labelled the 16th; actually exposed in the small hours of the 17th.
        _sess_obs("M16", "2026-08-16", 83,
                  "2026-08-17T04:14:46", "2026-08-17T04:59:21"),
        # Labelled the 17th — the same *label* as the stack's date — but every
        # frame is hours later than the stack, on the following calendar day.
        _sess_obs("M16", "2026-08-17", 202,
                  "2026-08-18T03:41:13", "2026-08-18T05:19:29"),
    ]
    totals = build_derived.build_totals({}, sessions)
    f = build_derived.build_processing(totals, None, {}, sessions)["folders"]["M16"]

    assert f["status"] == "out_of_date"
    assert f["new_lights_since_stack"] == 202
    # Only the 83 frames that existed when the stack was made are the
    # rejection denominator — 79/83 is 5% rejected, not 72%.
    assert f["stack_meta"]["frames_at_stack"] == 83
    assert f["stack_meta"]["stack_rejection_pct"] == 5


def test_a_session_straddling_the_stack_counts_as_backlog(tmp_path, monkeypatch):
    """Stacking mid-session leaves frames on both sides of the instant, and the
    session row can't say how many. Surfacing the backlog beats rounding it
    away — a spurious "restack me" is recoverable, a hidden 200-frame gap is the
    bug being fixed."""
    images = tmp_path / "Images"
    tgt = images / "M27"
    (tgt / "lights").mkdir(parents=True)
    _write_stack(tgt, stackcnt=50, date="2026-08-17T22:00:00")
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = [_sess_obs("M27", "2026-08-17", 120,
                          "2026-08-17T21:00:00", "2026-08-17T23:30:00")]
    totals = build_derived.build_totals({}, sessions)
    f = build_derived.build_processing(totals, None, {}, sessions)["folders"]["M27"]
    assert f["status"] == "out_of_date"
    assert f["new_lights_since_stack"] == 120


def test_sessions_without_a_window_still_use_the_day_comparison(tmp_path, monkeypatch):
    """`first_obs`/`last_obs` are new, and sessions.jsonl is only rewritten on a
    refresh — so an existing store's rows lack them until then. The old
    day-granularity path has to keep working rather than crash or read as
    up-to-date across the board."""
    images = tmp_path / "Images"
    tgt = images / "M13"
    (tgt / "lights").mkdir(parents=True)
    _write_stack(tgt, stackcnt=100, date="2026-06-10T12:00:00")
    monkeypatch.setattr(config, "IMAGES_DIR", images)

    sessions = [_sess("M13", "2026-05-01", 100),    # no first_obs/last_obs
                _sess("M13", "2026-07-01", 40)]
    totals = build_derived.build_totals({}, sessions)
    f = build_derived.build_processing(totals, None, {}, sessions)["folders"]["M13"]
    assert f["status"] == "out_of_date"
    assert f["new_lights_since_stack"] == 40
    assert f["stack_meta"]["frames_at_stack"] == 100
