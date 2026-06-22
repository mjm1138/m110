#!/usr/bin/env python3
"""Generate a synthetic M110 data store for manual testing, and tar it up.

Builds a realistic-but-tiny store (real FITS with proper headers + filenames,
small rendered PNGs) that exercises the whole app:

  * captured objects with lights + Seestar stacks   → gallery / hero / sessions
  * an object with an imported finished render+stack → "finished" display
  * an object with UNIMPORTED Siril output           → Import-finished-work round-trip
  * a captured-but-uncatalogued folder (NGC 7000)    → auto-cataloging on refresh
  * a multi-object folder ("M81 M82")                → many-to-many target→object
  * an Inbox laid out like a Seestar export          → ingest (move): grouping,
        case-canonicalisation (m13→M13), a mis-pointed group (M65 frames that
        actually point at M66 → the ⚠ remap), an in-app stack, and a media folder

The generator is committed (it's small + reproducible); its OUTPUT is meant to
live OUTSIDE the repo (default ~/m110-testdata) so the repo stays lean.

Usage:
    python tools/make_test_corpus.py                 # → ~/m110-testdata/...
    python tools/make_test_corpus.py --out DIR --tar FILE
    python tools/make_test_corpus.py --no-tar        # leave the dir, skip the tarball

Then test against it (no install changes needed):
    tar xzf ~/m110-testdata/m110-test-corpus.tar.gz -C ~/Documents
    M110_DATA_ROOT=~/Documents/M110-test m110     # then Refresh (Ctrl+R)
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

    # NGC 7000 — captured but NOT in the seed catalog (auto-catalog on refresh)
    _lights("NGC 7000", "NGC 7000", 314.7, 44.5, 10, "LP", base + timedelta(days=6), 20, 900)
    _seestar_stack("NGC 7000", "NGC 7000", 314.7, 44.5, 100, 10, "LP",
                   base + timedelta(days=6, hours=1), 950)

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

    # ---- Inbox: a Seestar-style export to ingest ----
    inbox = config.STAGING_DIR
    _inbox_sub(inbox, "M27", *C("m27"), 10, "LP", 30, 2000)            # new object
    _inbox_sub(inbox, "m13", *C("m13"), 10, "LP", 20, 2100)           # lowercase → M13
    _inbox_sub(inbox, "M65", *C("m66"), 10, "LP", 18, 2200)          # frames point at M66!
    _inbox_stack(inbox, "M57", *C("m57"), 60, 10, "LP", 2300)        # in-app stack
    _inbox_media(inbox, "Nightscape_photo", 2400)                     # media

    return out


def _inbox_sub(inbox, obj, ra, dec, exp, filt, n, seed0):
    d = inbox / f"{obj}_sub"
    d.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 6, 18, 2, 0, 0)
    for i in range(n):
        when = start + timedelta(seconds=21 * i)
        _fits(d / f"Light_{obj}_{exp}s_{filt}_{when.strftime('%Y%m%d-%H%M%S')}.fit",
              obj, ra, dec, exp, filt, when, seed0 + i)


def _inbox_stack(inbox, obj, ra, dec, n, exp, filt, seed):
    d = inbox / obj
    d.mkdir(parents=True, exist_ok=True)
    when = datetime(2026, 6, 18, 4, 0, 0)
    base = f"Stacked_{n}_{obj}_{exp}s_{filt}_{when.strftime('%Y%m%d-%H%M%S')}"
    _fits(d / f"{base}.fit", obj, ra, dec, exp, filt, when, seed)
    _png(d / f"{base}.jpg", seed)


def _inbox_media(inbox, name, seed):
    d = inbox / name
    d.mkdir(parents=True, exist_ok=True)
    _png(d / "IMG_0001.jpg", seed)
    _png(d / "IMG_0002.jpg", seed + 1)


# ── self-check + packaging ────────────────────────────────────────────────────

def verify(out: Path):
    """Read-only sanity checks (no writes into the corpus)."""
    from m110 import scan_sessions, ingest
    config.set_data_root(out)
    sessions = scan_sessions.scan()
    staging = ingest.scan_staging_plan()
    objs = {s["object_dir"] for s in sessions}
    print(f"  sessions parsed: {len(sessions)} across {len(objs)} folders {sorted(objs)}")
    print(f"  inbox ops planned: {len(staging)}")
    # the M106 sandbox should report importable output
    from m110 import siril
    print(f"  M106 has unimported output: {siril.has_unimported_output('M106')}")
    assert sessions and staging, "corpus produced no sessions/inbox ops"


def make_tar(out: Path, tar_path: Path):
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    if tar_path.exists():
        tar_path.unlink()
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(out, arcname=out.name)
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
    print(f"Building synthetic corpus → {out}")
    build(out)
    print("Verifying (read-only)…")
    verify(out)
    if not args.no_tar:
        tar = make_tar(out, args.tar.expanduser().resolve())
        size = tar.stat().st_size / 1024
        print(f"Wrote tarball → {tar}  ({size:.0f} KB)")
    print("\nTo test:")
    print(f"  tar xzf {args.tar} -C ~/Documents")
    print(f"  M110_DATA_ROOT=~/Documents/{out.name} m110     # then Refresh (Ctrl+R)")


if __name__ == "__main__":
    main()
