"""Tests for thumbnail/hero/manifest generation (temp fixtures + real PIL).

Renders land in the hidden internal store: thumbnails in RENDERS_DIR, heroes in
HERO_DIR, the manifest in DERIVED_DIR. Sources come from per-target subfolders
(Images/<target>/{finished,stacks,seestar-stacks}).
"""
import json

import pytest

from m110 import config, build_images

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _png(path, size=(200, 120), color=(40, 80, 160)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def _setup(tmp_path, monkeypatch):
    root = tmp_path / "M110"
    internal = root / config.INTERNAL_DIRNAME
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "Objects")
    monkeypatch.setattr(config, "DERIVED_DIR", internal / "derived")
    monkeypatch.setattr(config, "RENDERS_DIR", internal / "renders")
    monkeypatch.setattr(config, "HERO_DIR", internal / "renders" / "hero")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    return root, internal


def test_render_generates_thumb_hero_manifest(tmp_path, monkeypatch):
    root, internal = _setup(tmp_path, monkeypatch)
    # a finished render for M99 in the highest hero tier
    _png(config.finished_dir("M99") / "M99_final.png")

    catalog = {"m99": {"id": "M99", "name": "Test"}}
    totals = {"by_folder": {"M99": {"slugs": ["m99"]}}, "by_slug": {}}

    result = build_images.render_images(catalog, totals)
    assert result["slugs"] == 1

    # manifest written with a thumb filename (relative to RENDERS_DIR)
    manifest = json.loads((internal / "derived" / "images.json").read_text())
    assert "m99" in manifest
    entry = manifest["m99"][0]
    assert entry["viewable"] is True
    assert entry["thumb"] and (internal / "renders" / entry["thumb"]).is_file()
    # viewable raster → `full` points at the source (data-root-relative) for the viewer
    assert entry["full"] and (root / entry["full"]).is_file()

    # hero rendered
    assert (internal / "renders" / "hero" / "m99.jpg").is_file()


def test_orphaned_thumb_pruned_on_reprocess(tmp_path, monkeypatch):
    """#14: a reprocessed source gets a new content-hash thumb; the stale one is
    pruned (not left to grow the renders cache)."""
    import time
    root, internal = _setup(tmp_path, monkeypatch)
    src = config.finished_dir("M99") / "M99_final.png"
    _png(src)
    catalog = {"m99": {"id": "M99"}}
    totals = {"by_folder": {"M99": {"slugs": ["m99"]}}, "by_slug": {}}
    build_images.render_images(catalog, totals)
    renders = internal / "renders"
    first = sorted(p.name for p in renders.glob("*.jpg"))
    assert len(first) == 1
    time.sleep(0.01)
    _png(src, size=(240, 160), color=(200, 30, 30))      # reprocess → new hash
    res = build_images.render_images(catalog, totals)
    now = sorted(p.name for p in renders.glob("*.jpg"))
    assert len(now) == 1 and now != first                # old pruned, new present
    assert res["pruned"] == 1


def test_orphaned_hero_pruned_when_slug_drops(tmp_path, monkeypatch):
    root, internal = _setup(tmp_path, monkeypatch)
    _png(config.finished_dir("M99") / "M99_final.png")
    catalog = {"m99": {"id": "M99"}}
    totals = {"by_folder": {"M99": {"slugs": ["m99"]}}, "by_slug": {}}
    build_images.render_images(catalog, totals)
    assert (internal / "renders" / "hero" / "m99.jpg").is_file()
    # object no longer has images → not in the manifest → hero pruned
    res = build_images.render_images(catalog, {"by_folder": {}, "by_slug": {}})
    assert not (internal / "renders" / "hero" / "m99.jpg").exists()
    assert res["pruned"] >= 1


def test_partial_render_does_not_prune(tmp_path, monkeypatch):
    """A targeted `slugs=` render writes a partial manifest, so it must NOT prune
    other slugs' live derivatives."""
    root, internal = _setup(tmp_path, monkeypatch)
    _png(config.finished_dir("M99") / "M99_final.png")
    _png(config.finished_dir("M81") / "M81_final.png")
    catalog = {"m99": {"id": "M99"}, "m81": {"id": "M81"}}
    totals = {"by_folder": {"M99": {"slugs": ["m99"]}, "M81": {"slugs": ["m81"]}},
              "by_slug": {}}
    build_images.render_images(catalog, totals)                 # full
    renders = internal / "renders"
    assert len(list(renders.glob("*.jpg"))) == 2
    res = build_images.render_images(catalog, totals, slugs=["m99"])  # partial
    assert res["pruned"] == 0
    assert len(list(renders.glob("*.jpg"))) == 2                # M81's thumb kept


def test_thumb_is_cached(tmp_path, monkeypatch):
    root, internal = _setup(tmp_path, monkeypatch)
    src = config.finished_dir("M99") / "x.png"
    _png(src)
    renders = internal / "renders"
    renders.mkdir(parents=True)
    a = build_images.make_thumb(src, renders)
    b = build_images.make_thumb(src, renders)  # second call hits cache
    assert a == b and a.is_file()


def test_uncaptured_slug_skipped(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    catalog = {"m1": {"id": "M1"}}
    totals = {"by_folder": {}, "by_slug": {}}   # no folders → nothing to render
    result = build_images.render_images(catalog, totals)
    assert result["slugs"] == 0


def test_fit_stack_gets_thumbnail_and_hero(tmp_path, monkeypatch):
    """A FITS-only Seestar stack must still produce a gallery thumbnail + hero
    (bug: nothing displayed for objects with only .fit stacks)."""
    import numpy as np
    from astropy.io import fits
    root, internal = _setup(tmp_path, monkeypatch)
    p = config.seestar_stacks_dir("M99") / "Stacked_10_M99.fit"
    p.parent.mkdir(parents=True)
    fits.PrimaryHDU((np.random.rand(40, 40) * 1000).astype("float32")).writeto(p)

    catalog = {"m99": {"id": "M99", "name": "Test"}}
    totals = {"by_folder": {"M99": {"slugs": ["m99"]}}, "by_slug": {}}
    res = build_images.render_images(catalog, totals)
    assert res["slugs"] == 1

    entry = json.loads((internal / "derived" / "images.json").read_text())["m99"][0]
    assert entry["viewable"] is False                 # it's a .fit
    assert entry["full"] is None                      # FITS isn't directly viewable
    assert entry["thumb"] and (internal / "renders" / entry["thumb"]).is_file()
    assert (internal / "renders" / "hero" / "m99.jpg").is_file()    # hero from the .fit


def test_is_intermediate_fit_honors_final_hint():
    """A pipeline-step token doesn't make a FITS an intermediate when it's also
    marked final — the imported deliverable bakes its steps into the name."""
    from pathlib import Path
    assert build_images._is_intermediate_fit(Path("M51_spcc.fit")) is True
    assert build_images._is_intermediate_fit(Path("M51_og.fit")) is True
    assert build_images._is_intermediate_fit(Path("M51_spcc_processed.fit")) is False
    assert build_images._is_intermediate_fit(Path("M51_processed.png")) is False  # raster
