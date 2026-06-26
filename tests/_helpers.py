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
    monkeypatch.setattr(config, "SESSIONS_JSONL", internal / "sessions.jsonl")
    monkeypatch.setattr(config, "MEDIA_DIR", root / "Media")
    monkeypatch.setattr(config, "STAGING_DIR", root / "Inbox")
    monkeypatch.setattr(config, "GOALS_TOML", internal / "goals.toml")
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


def seed_sandbox(target="M51"):
    """A siril sandbox with two unimported deliverables (render + stack)."""
    sb = config.siril_dir(target)
    sb.mkdir(parents=True, exist_ok=True)
    (sb / f"{target}_x_processed.png").write_text("png")
    (sb / f"{target}_x_processed.fit").write_text("fit")
    return sb
