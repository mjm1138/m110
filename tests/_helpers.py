"""Shared builders for the offscreen UI / integration tests.

One copy of the temp-store setup and the small fixtures that several test modules
need (previously duplicated as `_seed_root` / `_seed_capture` / … in each file)."""
from __future__ import annotations

from m110 import config


def seed_root(tmp_path, monkeypatch):
    """Point every per-store `config` path at a fresh temp root, bootstrap it, and
    return the root. Patches all the globals the engine reads dynamically (incl.
    PROFILES_DIR for the planning engine) so tests never touch live data."""
    root = tmp_path / "M110"
    internal = root / config.INTERNAL_DIRNAME
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "LIBRARY_TOML", internal / "library.toml")
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "DERIVED_DIR", internal / "derived")
    monkeypatch.setattr(config, "RENDERS_DIR", internal / "renders")
    monkeypatch.setattr(config, "HERO_DIR", internal / "renders" / "hero")
    monkeypatch.setattr(config, "MEDIA_RENDERS_DIR", internal / "renders" / "media")
    monkeypatch.setattr(config, "SESSIONS_JSONL", internal / "sessions.jsonl")
    monkeypatch.setattr(config, "MEDIA_DIR", root / "Media")
    monkeypatch.setattr(config, "STAGING_DIR", root / "Inbox")
    monkeypatch.setattr(config, "PLANS_DIR", root / "Plans")
    monkeypatch.setattr(config, "GOALS_TOML", internal / "goals.toml")
    monkeypatch.setattr(config, "PINS_TOML", internal / "pins.toml")
    monkeypatch.setattr(config, "PROFILES_DIR", internal / "profiles")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.ensure_data_root(root)
    return root


def messier_member():
    """A known bundled Messier (slug, designation) — the Library starts empty
    (5d), so tests capture/add a real catalog object to populate it."""
    from m110 import catalog
    return next(iter(catalog.load_bundled_catalog("messier")["members"].items()))


def add_library(root, entries):
    """Append minimal `[catalog.<slug>]` blocks to the (empty) Library so a test
    can populate the collection directly (5d: the Library no longer bulk-seeds)."""
    lib = root / config.INTERNAL_DIRNAME / "library.toml"
    with lib.open("a") as f:
        for slug, e in entries.items():
            f.write(f"\n[catalog.{slug}]\n")
            for k, v in e.items():
                f.write(f'{k} = "{v}"\n')


def seed_capture(root):
    """Give one Messier object a light frame (→ a session) and rebuild derived.
    Returns (slug, target_id)."""
    from m110 import refresh
    slug, tid = messier_member()
    lights = config.lights_dir(tid)
    lights.mkdir(parents=True)
    (lights / f"Light_{tid}_30.0s_LP_20260529-010101.fit").write_text("x")
    refresh.run_refresh(render=False)
    return slug, tid


def fits_at(path, ra, dec):
    """Write a tiny real FITS frame carrying RA/DEC headers (for the ingest
    pointing check). Mirrors the helper in tests/test_ingest.py."""
    import numpy as np
    from astropy.io import fits
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="float32"))
    h.header["RA"] = ra
    h.header["DEC"] = dec
    h.writeto(path)


# ── fake device mounts ──────────────────────────────────────────────────────
#
# A smart telescope is just a mounted filesystem — USB or SMB, it lands under
# /Volumes either way — so a scratch directory shaped like one is a faithful
# stand-in. Building the volume and pointing `config.VOLUMES_DIR` at it means the
# tests drive the **real** probe (`find_seestar_myworks`) and the real device scan,
# rather than stubbing the probe out and testing the layer below it.

def _device_fits(path, obj, when, *, exp=30.0, filt="LP", ra=202.5, dec=47.2,
                 eqmode=None, extra=None):
    """A tiny FITS sub with the header cards the importer and session scanner
    actually read (OBJECT / DATE-OBS / EXPTIME / FILTER / RA / DEC)."""
    import numpy as np
    from astropy.io import fits
    path.parent.mkdir(parents=True, exist_ok=True)
    h = fits.PrimaryHDU(np.zeros((2, 2), dtype="float32"))
    h.header["OBJECT"] = obj
    h.header["DATE-OBS"] = when.strftime("%Y-%m-%dT%H:%M:%S")
    h.header["EXPTIME"] = exp
    h.header["FILTER"] = filt
    h.header["RA"] = ra
    h.header["DEC"] = dec
    if eqmode is not None:
        h.header["EQMODE"] = eqmode
    for k, v in (extra or {}).items():
        h.header[k] = v
    h.writeto(path)
    return path


def mount_seestar(tmp_path, monkeypatch, obj="M51", *, count=3, exp=30,
                  filt="LP", volume="Seestar S50"):
    """Create a scratch volume shaped like a **mounted Seestar** and point the real
    mount probe at it: ``<tmp>/Volumes/<volume>/MyWorks/<obj>_sub/Light_*.fit``.

    Returns (myworks_path, [sub filenames]). After this, `config.find_seestar_myworks()`
    finds it for real and `ingest.scan_seestar_plan()` works end to end."""
    from datetime import datetime, timedelta
    volumes = tmp_path / "Volumes"
    monkeypatch.setattr(config, "VOLUMES_DIR", volumes)
    subs_dir = volumes / volume / "MyWorks" / f"{obj}_sub"
    start = datetime(2026, 5, 29, 1, 0, 0)
    names = []
    for i in range(count):
        when = start + timedelta(seconds=(exp + 3) * i)
        name = f"Light_{obj}_{exp}.0s_{filt}_{when.strftime('%Y%m%d-%H%M%S')}.fit"
        _device_fits(subs_dir / name, obj, when, exp=float(exp), filt=filt,
                     eqmode=1)
        names.append(name)
    return volumes / volume / "MyWorks", names


def mount_dwarf(tmp_path, obj="M 1", *, count=3, exp=15, gain=60,
                filt="Duo-Band", volume="DWARF3"):
    """Create a scratch volume shaped like a **mounted DwarfLab Dwarf 3**:
    ``<tmp>/Volumes/<volume>/Astronomy/DWARF_RAW_TELE_<obj>_EXP_…/<obj>_…fits``.

    Returns (astronomy_dir, [sub filenames]). There is no Dwarf mount *probe* yet
    (ROADMAP 6d) — the user browses to the volume — so callers scan the returned
    directory directly, which is exactly what the Import page does."""
    from datetime import datetime, timedelta
    session = (tmp_path / "Volumes" / volume / "Astronomy"
               / f"DWARF_RAW_TELE_{obj}_EXP_{exp}_GAIN_{gain}_2026-06-19-22-00-00")
    start = datetime(2026, 6, 19, 22, 0, 0)
    names = []
    for i in range(count):
        when = start + timedelta(seconds=(exp + 3) * i)
        name = (f"{obj}_{exp}s{gain}_{filt}_"
                f"{when.strftime('%Y%m%d-%H%M%S')}{i:03d}_0C.fits")
        # Dwarf DATE-OBS is end-of-exposure and the object comes from the header,
        # not the filename — the two facts the importer keys on for this device.
        _device_fits(session / name, obj, when, exp=float(exp), filt=filt,
                     eqmode=0, extra={"GAIN": gain, "TELESCOP": "Dwarf3"})
        names.append(name)
    return tmp_path / "Volumes" / volume / "Astronomy", names


def seed_sandbox(target="M51"):
    """A siril sandbox with two unimported deliverables (render + stack)."""
    sb = config.siril_dir(target)
    sb.mkdir(parents=True, exist_ok=True)
    (sb / f"{target}_x_processed.png").write_text("png")
    (sb / f"{target}_x_processed.fit").write_text("fit")
    return sb
