"""A data root on NFS (#161): macOS AppleDouble sidecars must be invisible.

On a filesystem that can't hold an extended attribute, macOS writes ``._<name>``
beside every file it creates — and since macOS 26 that is *every* file, because
the OS stamps ``com.apple.provenance`` on each one. A store on an NFS export
therefore grows one sidecar per sub, per profile, per guide, and nothing on the
mount side can stop it. The sidecar's name passes every extension test and its
bytes are a binary header, so before this the app crashed at startup (a
``._default.toml`` parsed as a site profile), import failed while hardlinking a
``._Light_x.fit`` into the Siril sandbox, and sessions double-counted.

Each test plants the *real* sidecar bytes next to real content and asserts the
consumer neither crashes nor counts it. The fixture bytes are the AppleDouble
header the reporter captured — offset 37 is the ``0xb0`` the original traceback
blamed on "invalid start byte".
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from m110 import (astrowizard, build_images, config, fieldguide, migrate,
                  planning_config, processing, roundtrip, scan_sessions, siril)
from m110.assistant import outbox
from m110.backup.scope import (SCOPE_ESSENTIALS, SCOPE_EVERYTHING, is_excluded,
                               iter_source_files)
from ._helpers import seed_root

# The first 48 bytes of a real ``._default.toml`` from a Synology NFS export
# (magic 00051607, version 2, "Mac OS X" filler, two entries) padded with the
# byte the traceback named.
APPLEDOUBLE = (bytes.fromhex("0005160700020000")       # magic, version 2
               + b"Mac OS X" + b" " * 8              # filler
               + bytes.fromhex("0002")                # two entries
               + bytes(11) + b"\xb0" + bytes(10))     # entry table, 0xb0 at 37
assert APPLEDOUBLE[37] == 0xB0


def sidecar(path: Path) -> Path:
    """Write the AppleDouble sidecar macOS would leave beside `path`."""
    p = path.parent / f"._{path.name}"
    p.write_bytes(APPLEDOUBLE)
    return p


def _lights(target: str, n: int = 3) -> list[Path]:
    d = config.lights_dir(target)
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(n):
        f = d / f"Light_{target}_20.0s_LP_20260918-23{i:04d}.fit"
        f.write_text("sub")
        sidecar(f)
        out.append(f)
    return out


# ── the one predicate ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "._Light_IC 1805_60.0s_LP_20260918-235231.fit", "._stacked.fits",
    "._default.toml", ".DS_Store", "._M42_final.png", ".hidden.fit",
])
def test_hidden_names_are_never_fits_or_lights(name):
    assert config.is_hidden_name(name)
    assert not config.is_fits_file(name)
    assert not config.is_light_frame(name)


def test_the_real_names_still_pass():
    assert not config.is_hidden_name("Light_IC 1805_60.0s_LP_20260918-235231.fit")
    assert config.is_light_frame("Light_IC 1805_60.0s_LP_20260918-235231.fit")
    assert config.is_fits_file("stacked.FITS")


# ── the startup crash: profiles ───────────────────────────────────────────────

def test_profiles_listing_skips_the_sidecar_and_the_page_can_load(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    prof = root / config.INTERNAL_DIRNAME / "profiles" / "default.toml"
    assert prof.is_file()
    sidecar(prof)
    assert planning_config.list_profiles() == ["default"]
    # What the Planning page does on construction: load every listed profile.
    for name in planning_config.list_profiles():
        planning_config.load_site(name)


# ── the second startup crash: saved field guides ──────────────────────────────

def test_guides_listing_skips_the_sidecar_and_a_binary_title_read_survives(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    path = fieldguide.save(__import__("datetime").date(2026, 9, 18), "NFS night",
                           "# Observing plan — 2026-09-18\n")
    sidecar(path)
    guides = fieldguide.list_guides()
    assert [g["name"] for g in guides] == [path.name]
    # Even if a binary file reaches the title reader, it must not raise.
    assert fieldguide._title_of(path.parent / f"._{path.name}") == f"._{path.stem}"


# ── import: the sandbox hardlink step ─────────────────────────────────────────

def test_siril_prep_never_links_a_sidecar(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _lights("IC 1805", 3)
    plan = siril.plan_prep("IC 1805")
    assert plan.total_lights == 3
    res = siril.apply_prep(plan)
    assert res["linked"] == 3
    linked = sorted(p.name for p in (config.siril_dir("IC 1805") / "lights").iterdir())
    assert linked and not any(n.startswith("._") for n in linked)
    # The reconcile after a rejection walks the same lists.
    assert siril.prune_rejected("IC 1805") == {"pruned": 0, "orphans": 0, "skipped": False}


def test_astrowizard_prep_never_links_a_sidecar(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _lights("IC 1805", 2)
    astrowizard.prepare_lights("IC 1805")
    names = [p.name for p in astrowizard.lights_dir("IC 1805").rglob("*") if p.is_file()]
    assert len(names) == 2 and not any(n.startswith("._") for n in names)


def test_calibration_frames_skip_sidecars(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _lights("M31", 1)
    d = config.darks_dir("M31")
    d.mkdir(parents=True)
    dark = d / "Dark_001.fit"
    dark.write_text("d")
    sidecar(dark)
    assert [p.name for p in siril._calib_frames("M31")["darks"]] == ["Dark_001.fit"]


# ── sessions, integration, target discovery ───────────────────────────────────

def test_sessions_do_not_double_count(tmp_path, monkeypatch):
    """The Seestar filename fast path is a ``re.search`` — the ``._`` prefix did
    not stop it matching, so every sidecar counted as a second sub."""
    seed_root(tmp_path, monkeypatch)
    _lights("IC 1805", 3)
    rows = [s for s in scan_sessions.scan() if s["object_dir"] == "IC 1805"]
    assert sum(s["frames"] for s in rows) == 3
    assert processing._store_targets() == ["IC 1805"]


def test_a_target_holding_only_sidecars_is_not_a_target(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    d = config.lights_dir("Ghost")
    d.mkdir(parents=True)
    (d / "._Light_Ghost_20.0s_LP_20260918-230000.fit").write_bytes(APPLEDOUBLE)
    assert processing._store_targets() == []
    assert siril.plan_prep("Ghost").total_lights == 0


def test_derived_totals_and_stacks_ignore_sidecars(tmp_path, monkeypatch):
    from m110 import refresh, derived
    from astropy.io import fits
    root = seed_root(tmp_path, monkeypatch)
    _lights("M31", 3)
    stacks = config.stacks_dir("M31")
    stacks.mkdir(parents=True)
    st = stacks / "M31_stacked.fit"
    fits.PrimaryHDU(np.zeros((2, 2), dtype="float32")).writeto(st)
    sidecar(st)
    refresh.run_refresh(render=False)
    entry = derived.load_processing()["folders"]["M31"]
    assert entry["frames"] == 3
    names = [p["name"] for p in entry["processed_files"]]
    assert names == ["M31_stacked.fit"] and entry["processed_count"] == 1
    # The sessions rollup on disk is the double-count's other witness.
    rows = [json.loads(l) for l in (root / config.INTERNAL_DIRNAME / "sessions.jsonl")
            .read_text().splitlines() if l.strip()]
    assert sum(r["frames"] for r in rows if r["object_dir"] == "M31") == 3


# ── the stacker's frame survey ────────────────────────────────────────────────

def test_stack_plan_does_not_open_a_sidecar_as_fits(tmp_path):
    from m110.stacking import build_plan, Overrides
    from .test_stacking import _GEOM, _sub
    d = tmp_path / "siril"
    for i in range(3):
        sidecar(_sub(d / "lights" / f"L{i}.fit", OBJECT="M81", **_GEOM))
    plan = build_plan(d, Overrides(), deep_measure=False)
    assert len(plan.frames) == 3


# ── finished-output discovery and the gallery ─────────────────────────────────

def test_finished_output_scan_never_offers_a_sidecar(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    _lights("M42", 1)
    siril.apply_prep(siril.plan_prep("M42"))
    out = config.siril_dir("M42") / "M42_processed.png"
    out.write_bytes(b"png")
    sidecar(out)
    found = sorted(p.name for p, _k, _d in roundtrip.finished_outputs("M42", siril.SANDBOX))
    assert found == ["M42_processed.png"]


def test_gallery_discovery_skips_sidecars(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    fin = config.finished_dir("M42")
    fin.mkdir(parents=True)
    render = fin / "M42_final.jpg"
    render.write_bytes(b"jpg")
    sidecar(render)
    assert [p.name for p in build_images._photos_in(fin)] == ["M42_final.jpg"]
    names = [i["name"] for i in build_images.discover_images("m42", ["M42"], {})]
    assert names == ["M42_final.jpg"]


# ── backup, outbox, migration ─────────────────────────────────────────────────

@pytest.mark.parametrize("rel", [
    "Images/M 31/finished/._M31_final.png", "Images/M 31/._finished",
    "Objects/m31/._journal.md", ".m110_internal_data/._library.toml",
    "Images/M 31/.DS_Store", "Media/Moon_photo/Thumbs.db",
])
@pytest.mark.parametrize("scope", [SCOPE_EVERYTHING, SCOPE_ESSENTIALS])
def test_backups_never_ship_os_sidecars(rel, scope):
    assert is_excluded(rel, scope) is True


def test_backup_source_listing_drops_sidecars_but_keeps_the_files(tmp_path):
    root = tmp_path / "M110"
    fin = root / "Images" / "M 31" / "finished"
    fin.mkdir(parents=True)
    (fin / "M31_final.png").write_bytes(b"x")
    sidecar(fin / "M31_final.png")
    (root / "Objects" / "m31").mkdir(parents=True)
    (root / "Objects" / "m31" / "journal.md").write_text("j")
    sidecar(root / "Objects" / "m31" / "journal.md")
    assert iter_source_files(root) == ["Images/M 31/finished/M31_final.png",
                                       "Objects/m31/journal.md"]


def test_outbox_quota_ignores_sidecars(tmp_path, monkeypatch):
    root = seed_root(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "ASSISTANT_DIR", root / config.INTERNAL_DIRNAME / "assistant")
    monkeypatch.setattr(config, "ASSISTANT_OUTBOX",
                        root / config.INTERNAL_DIRNAME / "assistant" / "outbox")
    monkeypatch.setattr(outbox, "MAX_FILES", 2)
    p = outbox.write("a.md", "x")
    sidecar(Path(p))
    outbox.write("b.md", "x")                  # would be "already holds 2" if counted
    with pytest.raises(outbox.OutboxError, match="already holds"):
        outbox.write("c.md", "x")


def test_a_legacy_container_held_alive_only_by_sidecars_is_dropped(tmp_path):
    d = tmp_path / "data"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "._old.toml").write_bytes(APPLEDOUBLE)
    (d / ".DS_Store").write_bytes(b"")
    migrate._drop_legacy(d)
    assert not d.exists()
