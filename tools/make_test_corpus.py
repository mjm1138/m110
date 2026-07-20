#!/usr/bin/env python3
"""Generate a synthetic M110 data store for manual testing, and tar it up.

Builds a realistic-but-tiny store (real FITS with proper headers + filenames,
small rendered PNGs) that exercises the whole app:

  * captured objects with lights + Seestar stacks   → gallery / hero / sessions
  * a captured object shot with a **DwarfLab Dwarf 3** (M42): header-rich `.fits`
        subs (Duo-Band narrowband) + an in-app `stacked-16_*.fits` stack → exercises
        the `.fits` extension, a narrowband filter, and 2nd-device rendering/sessions
  * a captured **globular cluster** (M13) → object-type variety (the corpus is
        otherwise galaxies + nebulae; feeds the prioritizer type-weights)
  * **video media** (a Timelapse_video/*.mp4) → the Media page's video-row path
  * a **per-image curation override** (#17) on M42 → the detail pane's
        Finished / Working gallery split has a non-default example
  * an object with an imported finished render+stack → "finished" display
  * an object with UNIMPORTED Siril output           → Import-finished-work round-trip
  * a captured-but-uncatalogued folder (IC 1396)     → auto-cataloging on refresh +
        the "Enrich online" / Add-object target (in no bundled catalog)
  * a multi-object folder ("M81 M82")                → many-to-many target→object
  * Phase 5 (Library / catalogs / goals):
      - Caldwell activated as a 2nd goal + captured Caldwell objects (C20 NGC 7000,
        C27 Crescent, C33 Veil) → Summary goal progress, the Catalog filter, and
        multi-identifier labels ("C20 (NGC 7000)")
      - a stale Library stub (C33/NGC 6992: blank name, "unknown" type) → the
        right-click "Fill in missing metadata" target (repairs from the reference)
  * unclassifiable files in the Inbox holding area   → Import → Holding area panel
        (6c): headerless FITS + a stray render (a grouped dump), a no-IMAGETYP
        loose FITS, and a loose orphan → manual assign (object + kind)
  * an external import-source folder (ships beside the store) → Import → Browse…:
        a Seestar-style export that classifies (grouping, case-canonicalisation
        m13→M13, a mis-pointed M65→M66 remap, an in-app stack, media) + a mixed dump
        whose strays sweep into the holding area + **Dwarf 3 on-device sessions**
        (a `DWARF_RAW_*` raw-subs+stack session, a `STARTRAILS_*` folder → Media,
        and an `Unknown`-object session → the holding area for identify-by-pointing)

The generator is committed (it's small + reproducible); its OUTPUT is meant to
live OUTSIDE the repo (default ~/m110-testdata) so the repo stays lean.

Usage:
    python tools/make_test_corpus.py                 # → ~/m110-testdata/...
    python tools/make_test_corpus.py --out DIR --tar FILE
    python tools/make_test_corpus.py --no-tar        # leave the dir, skip the tarball

Then test against it (no install changes needed):
    tar xzf ~/m110-testdata/m110-test-corpus.tar.gz -C ~/Documents
    M110_DATA_ROOT=~/Documents/M110-test m110     # then Refresh (Ctrl+R)
    # Import → Browse… → ~/Documents/M110-test-import-source to exercise the
    # classify + sweep-to-holding flow. The tarball also unpacks that source folder.
"""
from __future__ import annotations

import argparse
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

from m110 import config, catalog, objects


# ── synthetic media helpers ──────────────────────────────────────────────────

def _blob(size: int = 72, seed: int = 0) -> np.ndarray:
    """A small star-field-ish float32 frame (gaussian blob + noise)."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size]
    cx, cy = rng.uniform(size * 0.3, size * 0.7, 2)
    blob = np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * (size / 8) ** 2))
    img = 1000 * blob + rng.normal(200, 30, (size, size))
    # a few "stars"
    for _ in range(8):
        sx, sy = rng.integers(0, size, 2)
        img[sy, sx] += rng.uniform(2000, 6000)
    return img.astype("float32")


def _fits(path: Path, obj: str, ra: float, dec: float,
          exp: float, filt: str, when: datetime, seed: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(data=_blob(seed=seed))
    h = hdu.header
    h["OBJECT"] = obj
    h["FILTER"] = filt
    h["EXPTIME"] = exp
    h["DATE-OBS"] = when.strftime("%Y-%m-%dT%H:%M:%S")
    h["RA"] = round(ra, 5)
    h["DEC"] = round(dec, 5)
    hdu.writeto(path, overwrite=True)


def _fits_unclassifiable(path: Path, seed: int, obj: str | None = None):
    """A FITS frame with no IMAGETYP and (by default) no OBJECT — the kind of file
    the importer can't place, so it falls into the Inbox/ holding area (6c)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(data=_blob(seed=seed))
    if obj:
        hdu.header["OBJECT"] = obj          # an object but still no IMAGETYP/kind
    hdu.writeto(path, overwrite=True)


def _png(path: Path, seed: int = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    arr = _blob(size=240, seed=seed)
    arr = (255 * (arr - arr.min()) / (np.ptp(arr) or 1)).astype("uint8")
    rgb = np.dstack([arr, (arr * 0.8).astype("uint8"), (arr * 1.0).astype("uint8")])
    Image.fromarray(rgb, "RGB").save(path)


def _lights(folder: str, obj: str, ra: float, dec: float, exp: int, filt: str,
            start: datetime, n: int, seed0: int, kind: str = "Light"):
    """Write n light subs into Images/<folder>/lights/ (Seestar filename form)."""
    d = config.lights_dir(folder)
    for i in range(n):
        when = start + timedelta(seconds=21 * i)
        name = (f"{kind}_{obj}_{exp}s_{filt}_"
                f"{when.strftime('%Y%m%d-%H%M%S')}.fit")
        _fits(d / name, obj, ra, dec, exp, filt, when, seed0 + i)


def _seestar_stack(folder: str, obj: str, ra: float, dec: float, n: int,
                   exp: int, filt: str, when: datetime, seed: int):
    d = config.seestar_stacks_dir(folder)
    base = f"Stacked_{n}_{obj}_{exp}s_{filt}_{when.strftime('%Y%m%d-%H%M%S')}"
    _fits(d / f"{base}.fit", obj, ra, dec, exp, filt, when, seed)
    _png(d / f"{base}.jpg", seed)   # the device preview render


# ── DwarfLab Dwarf 3 helpers (.fits subs + in-app stacked-16 stack) ───────────

def _dwarf_fits(path: Path, obj: str, ra: float, dec: float, exp: float,
                filt: str, when: datetime, seed: int, gain: int = 60,
                camera: str = "TELE", rgb: bool = False):
    """A Dwarf 3 `.fits` frame — header-rich, **no IMAGETYP**, `.fits` extension.
    `rgb=True` writes a 3-plane frame like the in-app `stacked-16_*` stack."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.stack([_blob(seed=seed), _blob(seed=seed + 1), _blob(seed=seed + 2)])
            if rgb else _blob(seed=seed))
    hdu = fits.PrimaryHDU(data=data)
    h = hdu.header
    h["OBJECT"] = obj
    h["FILTER"] = filt
    h["EXPTIME"] = exp
    h["GAIN"] = gain
    h["DATE-OBS"] = when.strftime("%Y-%m-%dT%H:%M:%S")
    h["RA"] = round(ra, 5)
    h["DEC"] = round(dec, 5)
    h["CAMERA"] = camera
    h["TELESCOP"] = "DWARF 3"
    h["INSTRUME"] = "DWARF 3"
    hdu.writeto(path, overwrite=True)


def _dwarf_lights(folder: str, obj: str, ra: float, dec: float, exp: int,
                  filt: str, start: datetime, n: int, seed0: int, gain: int = 60):
    """n Dwarf `.fits` subs → Images/<folder>/lights/ (Dwarf filename form; header
    drives the session — the filename has no Seestar `Light_…` fast-path)."""
    d = config.lights_dir(folder)
    for i in range(n):
        when = start + timedelta(seconds=(exp + 3) * i)
        name = (f"{obj}_{exp}s{gain}_{filt}_"
                f"{when.strftime('%Y%m%d-%H%M%S')}{i:03d}_0C.fits")
        _dwarf_fits(d / name, obj, ra, dec, exp, filt, when, seed0 + i, gain)


def _dwarf_stack(folder: str, obj: str, ra: float, dec: float, n: int, exp: int,
                 filt: str, when: datetime, seed: int, gain: int = 60):
    """The Dwarf in-app `stacked-16_*.fits` + `stacked.jpg` → the device-stack tier."""
    d = config.seestar_stacks_dir(folder)
    base = f"stacked-16_{obj}_{exp}s{gain}_{filt}_{when.strftime('%Y%m%d-%H%M%S')}"
    _dwarf_fits(d / f"{base}.fits", obj, ra, dec, exp * n, filt, when, seed, gain,
                rgb=True)
    _png(d / "stacked.jpg", seed)   # the device preview render


def _video(path: Path):
    """A tiny placeholder video file (valid enough for extension-based listing)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")


# ── corpus ───────────────────────────────────────────────────────────────────

def coord(coords: dict, slug: str, default=(180.0, 30.0)):
    return coords.get(slug, default)


def build(out: Path):
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    config.set_data_root(out)
    config.ensure_data_root(out)          # skeleton + seed catalog + journal stubs
    coords = catalog.load_coords()

    def C(slug):
        return coord(coords, slug)

    # ---- captured objects (live in Images/) ----
    base = datetime(2026, 5, 20, 1, 0, 0)

    ra, dec = C("m51")
    _lights("M51", "M51", ra, dec, 30, "LP", base, 12, 100)
    _lights("M51", "M51", ra, dec, 30, "LP", base + timedelta(days=4), 10, 200)
    _seestar_stack("M51", "M51", ra, dec, 120, 30, "LP", base + timedelta(days=4, hours=2), 300)

    ra, dec = C("m81")
    _lights("M81", "M81", ra, dec, 20, "IRCUT", base + timedelta(days=1), 15, 400)
    _seestar_stack("M81", "M81", ra, dec, 80, 20, "IRCUT", base + timedelta(days=1, hours=1), 500)

    ra, dec = C("m101")
    _lights("M101", "M101", ra, dec, 30, "LP", base + timedelta(days=2), 18, 600)

    # M63 — already imported finished work (finished/ render + stacks/ stack)
    ra, dec = C("m63")
    _lights("M63", "M63", ra, dec, 30, "LP", base + timedelta(days=3), 14, 700)
    _seestar_stack("M63", "M63", ra, dec, 90, 30, "LP", base + timedelta(days=3, hours=1), 750)
    _png(config.finished_dir("M63") / "M63_119x30sec_processed.png", 760)
    _fits(config.stacks_dir("M63") / "M63_119x30sec_processed.fit",
          "M63", ra, dec, 30, "LP", base + timedelta(days=3, hours=3), 761)

    # M81 M82 — multi-object capture folder
    ra, dec = C("m81")
    _lights("M81 M82", "M81 M82", ra, dec, 20, "LP", base + timedelta(days=5), 16, 800)

    # NGC 7000 (C20, North America) — captured; becomes a known Caldwell member once
    # the Caldwell goal is activated below (multi-id label "C20 (NGC 7000)").
    _lights("NGC 7000", "NGC 7000", 314.7, 44.5, 10, "LP", base + timedelta(days=6), 20, 900)
    _seestar_stack("NGC 7000", "NGC 7000", 314.7, 44.5, 100, 10, "LP",
                   base + timedelta(days=6, hours=1), 950)

    # IC 1396 (Elephant Trunk) — captured but in NO bundled catalog and not in the
    # reference: auto-cataloged as a minimal stub on first refresh; the "Enrich
    # online" / Add-object target (Fill-missing can't help — nothing in the reference).
    _lights("IC 1396", "IC 1396", 324.74, 57.5, 20, "LP", base + timedelta(days=11), 16, 980)

    # M42 (Orion) — captured with a **DwarfLab Dwarf 3**: header-rich `.fits` subs
    # (Duo-Band narrowband) + the in-app `stacked-16_*.fits` stack. Exercises the
    # `.fits` extension, a narrowband filter, and 2nd-device sessions/rendering.
    ra, dec = C("m42")
    _dwarf_lights("M42", "M42", ra, dec, 15, "Duo-Band", base + timedelta(days=10), 14, 5000)
    _dwarf_stack("M42", "M42", ra, dec, 60, 15, "Duo-Band",
                 base + timedelta(days=10, hours=1), 5100)

    # M13 (Hercules Cluster) — a captured globular, for object-type variety (the
    # corpus is otherwise galaxies + nebulae; the prioritizer type-weights + the
    # Library/Planning views want a cluster).
    ra, dec = C("m13")
    _lights("M13", "M13", ra, dec, 30, "LP", base + timedelta(days=12), 16, 5200)
    _seestar_stack("M13", "M13", ra, dec, 100, 30, "LP",
                   base + timedelta(days=12, hours=1), 5300)

    # ---- M106 — a Siril sandbox with UNIMPORTED output (round-trip test) ----
    ra, dec = C("m106")
    _lights("M106", "M106", ra, dec, 20, "LP", base + timedelta(days=7), 13, 1000)
    sb = config.siril_dir("M106")
    (sb / "lights").mkdir(parents=True, exist_ok=True)
    for i in range(13):                            # the (would-be hardlinked) inputs
        _fits(sb / "lights" / f"Light_M106_20s_LP_2026052{i%9}-01000{i%9}.fit",
              "M106", ra, dec, 20, "LP", base + timedelta(days=7, seconds=i), 1000 + i)
    (sb / "presets").mkdir(exist_ok=True)
    (sb / "presets" / "naztronomy_smart_scope_presets.json").write_text(
        '{"_note": "synthetic preset for testing"}\n')
    (sb / "next-steps.md").write_text("# Next steps\n\nSynthetic sandbox.\n")
    stem = "M106_119x20sec_2026-05-27_drizzle-1-5x_spcc"
    _png(sb / f"{stem}_processed.png", 1100)        # deliverable render
    _fits(sb / f"{stem}_processed.fit", "M106", ra, dec, 20, "LP",
          base + timedelta(days=7, hours=2), 1101)  # deliverable stack
    _fits(sb / f"{stem}_og.fit", "M106", ra, dec, 20, "LP", base, 1102)      # intermediate
    _fits(sb / f"{stem}.fit", "M106", ra, dec, 20, "LP", base, 1103)         # intermediate

    # ---- Phase 5: catalogs / goals / fill-missing -------------------------------
    from m110 import goals

    # A *stale* Library stub for C33/NGC 6992 (the East Veil): blank name, "unknown"
    # type — an object that entered the Library before its catalog data existed.
    # Written BEFORE activating Caldwell so the goal (which never overwrites) leaves
    # it incomplete → the right-click "Fill in missing metadata" demo.
    vra, vdec = C("ngc-6992")
    with config.LIBRARY_TOML.open("a") as f:
        f.write(f'\n[catalog.ngc-6992]\nid = "NGC 6992"\nname = ""\n'
                f'type = "unknown"\nra_deg = {vra}\ndec_deg = {vdec}\n')

    # Activate Caldwell as a 2nd goal (writes goals.toml). 5d: this no longer
    # bulk-seeds the Library — uncaptured Caldwell members show in the Goals page
    # checklist; the captured ones (NGC 7000 / 6888 / 6992 below) become Library
    # objects on refresh, with all identifiers ("C20 (NGC 7000)").
    goals.set_active_goals(["messier", "caldwell"])

    # Captured Caldwell objects → non-trivial Caldwell goal progress (full / partial /
    # stub reference coverage): C20 NGC 7000 (above), C27 Crescent (has mag), C33 Veil.
    ra, dec = C("ngc-6888")
    _lights("NGC 6888", "NGC 6888", ra, dec, 30, "LP", base + timedelta(days=8), 12, 3000)
    _lights("NGC 6992", "NGC 6992", vra, vdec, 30, "LP", base + timedelta(days=9), 14, 3100)

    # ---- journals: give a couple real notes (feed/detail), leave the rest stubs ----
    objects.write_journal("m51", (
        "---\nname: \"Whirlpool Galaxy\"\nhero_caption: \"Two nights, LP filter\"\n---\n\n"
        "# M51 — Whirlpool Galaxy\n\n"
        "Great spiral structure even from the back yard.\n"
        "Got the companion NGC 5195 nicely. Needs more integration on the tidal bridge.\n"))
    objects.write_journal("m81", (
        "---\nname: \"Bode's Galaxy\"\nhero_caption: \"\"\n---\n\n"
        "# M81 — Bode's Galaxy\n\n"
        "IRCUT looked better than LP here. Pair with M82 next time for the mosaic.\n"))

    # ---- Media: non-catalog stills + a video already in the store (Media page) ----
    for cat, seeds in (("Moon_photo", (1500, 1501)), ("Nightscape_photo", (1510,))):
        for s in seeds:
            _png(config.MEDIA_DIR / cat / f"IMG_{s}.jpg", s)
    _video(config.MEDIA_DIR / "Timelapse_video" / "IMG_1600.mp4")   # a video-row case

    # ---- Inbox: the 6c holding area — unclassifiable files only ----
    _inbox_holding(config.STAGING_DIR, 2500)

    # ---- An external import source to Browse→Import (ships beside the store) ----
    _build_import_source(out.parent / f"{out.name}-import-source")

    # Refresh once so captured folders are promoted into the Library (5d: the
    # Library is the captured collection, no longer bulk-seeded from goals) and
    # derived/renders are built — i.e. the post-launch state the app would produce.
    from m110 import refresh
    refresh.run_refresh()

    # A per-image curation override (#17): promote M42's device-stack preview into
    # the "Finished" gallery group so the detail pane's Finished / Working split has
    # a non-default example. After refresh so M42 is in the Library with a journal.
    objects.set_curation("m42", "stacked.jpg", "finished")

    return out


def _build_import_source(src: Path):
    """A messy **external** folder to point Import at (Browse…), beside the store and
    not part of it. A Seestar-style export that classifies cleanly (grouping, case
    canonicalisation m13→M13, a mis-pointed M65→M66 remap, an in-app stack, media) +
    a mixed dump that partly classifies and partly **sweeps into the holding area**."""
    if src.exists():
        shutil.rmtree(src)
    coords = catalog.load_coords()
    C = lambda slug: coord(coords, slug)                        # noqa: E731
    _src_sub(src, "M27", *C("m27"), 10, "LP", 30, 2000)        # new object
    _src_sub(src, "m13", *C("m13"), 10, "LP", 20, 2100)        # lowercase → M13
    _src_sub(src, "M65", *C("m66"), 10, "LP", 18, 2200)        # frames point at M66!
    _src_stack(src, "M57", *C("m57"), 60, 10, "LP", 2300)      # in-app stack
    _src_media(src, "Nightscape_photo", 2400)                  # media
    # a mixed dump: one header-bearing light classifies, the strays sweep to holding
    dump = src / "mixed_dump"
    ra, dec = C("m92")
    _fits(dump / "Light_M92_30s_LP_20260620-010000.fit", "M92", ra, dec, 30, "LP",
          datetime(2026, 6, 20, 1, 0, 0), 2600)                # → Images/M92/lights
    _fits_unclassifiable(dump / "capture_001.fit", 2610)       # headerless → holding
    _png(dump / "edit_final.png", 2620)                        # stray render → holding

    # DwarfLab Dwarf 3 on-device sessions (the `dwarf` layout, 6b): a raw-subs +
    # in-app-stack session → lights/stack tiers; a startrails folder → Media; an
    # `Unknown`-object session → the holding area (identify-by-pointing).
    _dwarf_import_session(src, "DWARF_RAW_TELE_M 1_EXP_15_GAIN_60_2026-06-19-22-00-00",
                          "M 1", *C("m1"))
    _dwarf_startrails(src, "STARTRAILS_DWARF_RAW_WIDE_EXP_10_GAIN_0_2026-06-19-23-00-00")
    _dwarf_unknown(src, "DWARF_RAW_WIDE_Unknown_EXP_10_GAIN_0_2026-06-19-23-30-00")


def _src_sub(src, obj, ra, dec, exp, filt, n, seed0):
    d = src / f"{obj}_sub"
    d.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 6, 18, 2, 0, 0)
    for i in range(n):
        when = start + timedelta(seconds=21 * i)
        _fits(d / f"Light_{obj}_{exp}s_{filt}_{when.strftime('%Y%m%d-%H%M%S')}.fit",
              obj, ra, dec, exp, filt, when, seed0 + i)


def _src_stack(src, obj, ra, dec, n, exp, filt, seed):
    d = src / obj
    d.mkdir(parents=True, exist_ok=True)
    when = datetime(2026, 6, 18, 4, 0, 0)
    base = f"Stacked_{n}_{obj}_{exp}s_{filt}_{when.strftime('%Y%m%d-%H%M%S')}"
    _fits(d / f"{base}.fit", obj, ra, dec, exp, filt, when, seed)
    _png(d / f"{base}.jpg", seed)


def _src_media(src, name, seed):
    d = src / name
    d.mkdir(parents=True, exist_ok=True)
    _png(d / "IMG_0001.jpg", seed)
    _png(d / "IMG_0002.jpg", seed + 1)


def _dwarf_import_session(src, folder, obj, ra, dec, exp=15, gain=60,
                          filt="Duo-Band", n=3):
    """A Dwarf 3 on-device session in the external source: raw `.fits` subs + the
    in-app `stacked-16_*` stack + `stacked.jpg`, beside a `Thumbnail/` sidecar +
    aux rasters (both ignored by the classifier — verifies the skip logic)."""
    d = src / folder
    d.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 6, 19, 22, 0, 0)
    for i in range(n):
        when = start + timedelta(seconds=(exp + 3) * i)
        _dwarf_fits(d / f"{obj}_{exp}s{gain}_{filt}_{when.strftime('%Y%m%d-%H%M%S')}{i:03d}_0C.fits",
                    obj, ra, dec, exp, filt, when, 5400 + i, gain)
    when = start + timedelta(minutes=5)
    stem = f"stacked-16_{obj}_{exp}s{gain}_{filt}_{when.strftime('%Y%m%d-%H%M%S')}"
    _dwarf_fits(d / f"{stem}.fits", obj, ra, dec, exp * n, filt, when, 5450, gain,
                rgb=True)
    (d / f"{stem}.png").write_bytes(b"png")            # in-app stack raster → stack tier
    _png(d / "stacked.jpg", 5460)                      # composite preview → stack tier
    (d / "stacked_thumbnail.jpg").write_bytes(b"t")    # aux raster → ignored
    (d / "shotsInfo.json").write_text("{}")            # non-content → ignored
    thumb = d / "Thumbnail"
    thumb.mkdir()
    for i in range(n):
        (thumb / f"sub_{i}.jpg").write_bytes(b"t")     # per-sub previews → ignored


def _dwarf_startrails(src, folder):
    """A Dwarf STARTRAILS_* session → Media (composite jpg + mp4; raw subs ignored)."""
    d = src / folder
    d.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        _dwarf_fits(d / f"startrails_10s0_2026061{i}-2300{i}0795_24C.fits",
                    "", 0.0, 0.0, 10, "", datetime(2026, 6, 19, 23, i, 0),
                    5500 + i, gain=0, camera="WIDE")
    _video(d / "startrails_classic_20260619-230000955.mp4")
    _png(d / "stacked.jpg", 5510)
    (d / "stacked_thumbnail.jpg").write_bytes(b"t")


def _dwarf_unknown(src, folder):
    """A Dwarf session whose OBJECT is the device placeholder `Unknown` → the subs
    fall to the holding area (identify-by-pointing), not a literal target."""
    d = src / folder
    d.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        _dwarf_fits(d / f"Unknown_10s0_2026061{i}-2330{i}0089_30C.fits",
                    "Unknown", 271.47, -14.05, 10, "",
                    datetime(2026, 6, 19, 23, 30 + i, 0), 5600 + i, gain=0,
                    camera="WIDE")


def _inbox_holding(inbox, seed0):
    """Seed the Inbox/ holding area (6c) with files the importer can't classify, so
    the Import → Holding area panel is populated on launch — the manual-assign demo.
      * `unsorted_dump/` — headerless FITS + a stray render (a grouped held folder)
      * `NGC 281.fit`    — a loose FITS with an OBJECT but no IMAGETYP (assign the kind)
      * `orphan.fit`     — a loose headerless file (the "(loose)" group)
    `*_thn.jpg`/hidden/non-content alongside are intentionally NOT surfaced."""
    dump = inbox / "unsorted_dump"
    for i in range(3):
        _fits_unclassifiable(dump / f"frame_{i:04d}.fit", seed0 + i)
    _png(dump / "screenshot.png", seed0 + 10)           # a stray image → held
    _png(dump / "screenshot_thn.png", seed0 + 11)       # thumbnail sidecar → skipped
    (dump / "notes.txt").write_text("scratch notes\n")  # non-content → skipped
    _fits_unclassifiable(inbox / "NGC 281.fit", seed0 + 20, obj="NGC 281")
    _fits_unclassifiable(inbox / "orphan.fit", seed0 + 30)


# ── self-check + packaging ────────────────────────────────────────────────────

def verify(out: Path):
    """Read-only sanity checks (no writes into the corpus)."""
    from m110 import scan_sessions, ingest
    config.set_data_root(out)
    sessions = scan_sessions.scan()
    objs = {s["object_dir"] for s in sessions}
    print(f"  sessions parsed: {len(sessions)} across {len(objs)} folders {sorted(objs)}")

    # 2nd device: M42 captured with a Dwarf 3 → `.fits` lights + stacked-16 stack.
    m42_lights = sorted(config.lights_dir("M42").glob("*.fits"))
    assert m42_lights, "M42 Dwarf `.fits` lights missing"
    assert "M42" in objs, "M42 (Dwarf) produced no session"
    assert (config.seestar_stacks_dir("M42") / "stacked.jpg").exists(), \
        "M42 Dwarf device-stack preview missing"
    assert "M13" in objs, "M13 cluster produced no session"
    print(f"  Dwarf M42: {len(m42_lights)} .fits lights + stacked-16 stack; "
          f"M13 cluster captured")

    # video media (the Media page's video-row path)
    from m110 import media
    media_kinds = {c["kind"] for c in media.scan()}
    assert "video" in media_kinds, "no video media in the store"

    # per-image curation override (#17): M42's device preview forced to "finished"
    assert objects.get_curation("m42").get("stacked.jpg") == "finished", \
        "M42 curation override not applied"

    # The external import source (Browse→Import): classifiable Seestar + Dwarf
    # exports + a mixed dump whose strays sweep into the holding area.
    src = out.parent / f"{out.name}-import-source"
    src_ops = ingest.scan_directory_plan(src)
    src_kinds = {o.kind for o in src_ops}
    print(f"  import source: {len(src_ops)} ops, kinds {sorted(src_kinds)}")
    assert "light" in src_kinds and "unassigned" in src_kinds, \
        "import source should both classify and sweep some files to holding"

    # Dwarf `dwarf`-layout sessions in the import source classify end-to-end.
    dwarf_ops = [o for o in src_ops if o.layout == "dwarf"]
    dwarf_lights = [o for o in dwarf_ops if o.kind == "light"]
    assert dwarf_lights and all(o.dest_rel.endswith(".fits") for o in dwarf_lights), \
        "Dwarf `.fits` subs should classify as lights"
    assert any(o.kind == "media" and "Startrails_video" in o.dest_rel for o in dwarf_ops), \
        "Dwarf startrails video should route to Media"
    unknown_held = [o for o in dwarf_ops
                    if o.kind == "unassigned" and "Unknown" in Path(o.src).name]
    assert unknown_held, "Dwarf Unknown-object subs should fall to the holding area"
    print(f"  Dwarf import: {len(dwarf_lights)} lights, "
          f"{sum(o.kind == 'media' for o in dwarf_ops)} media, "
          f"{len(unknown_held)} → holding")

    # 6c: the Inbox holding area carries unclassifiable files for the manual-assign demo
    held_ops = ingest.scan_holding()
    held = ingest.group_ops(held_ops)
    held_names = {Path(o.src).name for o in held_ops}
    print(f"  holding-area: {ingest.holding_count()} file(s) in {len(held)} group(s) "
          f"{sorted(g.group for g in held)}")
    assert ingest.holding_count() > 0, "holding area should carry unclassifiable files"
    assert "screenshot_thn.png" not in held_names, "thumbnail leaked into holding"
    assert "notes.txt" not in held_names, "non-content leaked into holding"
    # the M106 sandbox should report importable output
    from m110 import siril
    print(f"  M106 has unimported output: {siril.has_unimported_output('M106')}")
    assert sessions, "corpus produced no sessions"

    # Phase 5 (5d): Caldwell goal active; the Library is the captured collection
    # (only *captured* Caldwell members land here, not the whole catalog), and the
    # stale stub is left incomplete for the Fill-missing demo.
    from m110 import goals
    lib = catalog.load_library()
    assert goals.active_goal_ids() == ["messier", "caldwell"], "Caldwell not activated"
    assert "ngc-7000" in lib and "ngc-6992" in lib, "captured Caldwell objects not promoted"
    stub = lib["ngc-6992"]
    assert not stub.get("name") and stub.get("type") == "unknown", \
        "ngc-6992 should be a stale stub (Fill-missing target)"
    cald = catalog.load_bundled_catalog("caldwell")["members"]
    captured_cald = [s for s in ("ngc-7000", "ngc-6888", "ngc-6992") if s in cald]
    print(f"  goals: {goals.active_goal_ids()} · Library objects: {len(lib)} "
          f"(captured collection) · captured Caldwell: {captured_cald}")
    print(f"  ngc-6992 stub (Fill-missing target): name={stub.get('name')!r} "
          f"type={stub.get('type')!r}")


def make_tar(paths, tar_path: Path):
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    if tar_path.exists():
        tar_path.unlink()
    with tarfile.open(tar_path, "w:gz") as tf:
        for p in paths:
            if p.exists():
                tf.add(p, arcname=p.name)
    return tar_path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    home = Path.home()
    ap.add_argument("--out", type=Path, default=home / "m110-testdata" / "M110-test",
                    help="corpus directory to build (default ~/m110-testdata/M110-test)")
    ap.add_argument("--tar", type=Path,
                    default=home / "m110-testdata" / "m110-test-corpus.tar.gz",
                    help="output tarball (default ~/m110-testdata/m110-test-corpus.tar.gz)")
    ap.add_argument("--no-tar", action="store_true", help="skip the tarball")
    args = ap.parse_args()

    out = args.out.expanduser().resolve()
    import_src = out.parent / f"{out.name}-import-source"
    print(f"Building synthetic corpus → {out}")
    print(f"  + external import source → {import_src}")
    build(out)
    print("Verifying (read-only)…")
    verify(out)
    if not args.no_tar:
        tar = make_tar([out, import_src], args.tar.expanduser().resolve())
        size = tar.stat().st_size / 1024
        print(f"Wrote tarball → {tar}  ({size:.0f} KB)")
    print("\nTo test:")
    print(f"  tar xzf {args.tar} -C ~/Documents")
    print(f"  M110_DATA_ROOT=~/Documents/{out.name} m110     # then Refresh (Ctrl+R)")
    print(f"  # then Import → Browse… → ~/Documents/{import_src.name}  "
          f"(classifies + sweeps strays to the Holding area panel)")


if __name__ == "__main__":
    main()
