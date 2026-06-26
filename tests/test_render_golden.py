"""Golden-image regression for the render pipeline (m110/build_images.py).

Renders fixed, deterministic inputs (a gradient raster + a linear-ramp FITS —
*no* RNG) through the real thumbnail/hero code and compares to committed
reference images under tests/goldens/. This is the deterministic, zero-token
alternative to a human eyeballing renders: a stretch/resize/crop regression
shows up as a pixel diff.

Comparison is a small mean-absolute-pixel tolerance, not byte equality — so a
Pillow/libjpeg encoder bump doesn't cause false alarms, while a real change
(blank image, wrong stretch, wrong size) does.

Regenerate goldens intentionally with:  M110_UPDATE_GOLDENS=1 pytest -q tests/test_render_golden.py
"""
import os
import shutil
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
import numpy as np  # noqa: E402
from astropy.io import fits  # noqa: E402
from PIL import Image  # noqa: E402

from m110 import build_images, config  # noqa: E402

GOLDENS = Path(__file__).parent / "goldens"


# ── deterministic inputs ─────────────────────────────────────────────────────

def _gradient_png(path, w=600, h=360):
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.linspace(0, 255, w, dtype=np.uint8)
    band = np.tile(x, (h, 1))
    rgb = np.stack([band, band // 2, 255 - band], axis=-1).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(path)


def _ramp_fits(path, w=200, h=120):
    path.parent.mkdir(parents=True, exist_ok=True)
    ramp = np.linspace(0, 1000, w * h).reshape(h, w).astype("float32")
    fits.PrimaryHDU(ramp).writeto(path)


def _check(rendered: Path, name: str, tol: float):
    """Compare a freshly-rendered image to its committed golden (or refresh it
    when M110_UPDATE_GOLDENS is set)."""
    assert rendered is not None and rendered.is_file(), "nothing was rendered"
    golden = GOLDENS / name
    if os.environ.get("M110_UPDATE_GOLDENS"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(rendered, golden)
        pytest.skip(f"updated golden {name}")
    assert golden.is_file(), f"missing golden {name} — run with M110_UPDATE_GOLDENS=1"
    a = np.asarray(Image.open(rendered).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(golden).convert("RGB"), dtype=np.int16)
    assert a.shape == b.shape, f"{name}: size {a.shape} != golden {b.shape}"
    mad = float(np.abs(a - b).mean())
    assert mad <= tol, f"{name}: mean abs pixel diff {mad:.2f} > {tol} — rendering changed"


def _setup(tmp_path, monkeypatch):
    root = tmp_path / "M110"
    internal = root / config.INTERNAL_DIRNAME
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "DERIVED_DIR", internal / "derived")
    monkeypatch.setattr(config, "RENDERS_DIR", internal / "renders")
    monkeypatch.setattr(config, "HERO_DIR", internal / "renders" / "hero")
    monkeypatch.setattr(config, "LIBRARY_TOML", tmp_path / "absent.toml")
    return root, internal


# ── golden tests ─────────────────────────────────────────────────────────────

def test_thumb_raster_golden(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    src = config.finished_dir("M99") / "gradient.png"
    _gradient_png(src)
    renders = tmp_path / "renders"; renders.mkdir()
    out = build_images.make_thumb(src, renders)
    _check(out, "thumb_raster.png", tol=2.0)


def test_thumb_fits_stretch_golden(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    src = config.seestar_stacks_dir("M99") / "Stacked_ramp.fit"
    _ramp_fits(src)
    renders = tmp_path / "renders"; renders.mkdir()
    out = build_images.make_thumb(src, renders)      # exercises the percentile stretch
    _check(out, "thumb_fits_stretch.png", tol=2.0)


def test_hero_render_golden(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _gradient_png(config.finished_dir("M99") / "M99_final.png")
    catalog = {"m99": {"id": "M99", "name": "Test"}}
    totals = {"by_folder": {"M99": {"slugs": ["m99"]}}, "by_slug": {}}
    build_images.render_images(catalog, totals)
    hero = config.HERO_DIR / "m99.jpg"
    _check(hero, "hero_m99.jpg", tol=3.0)            # JPEG: slightly looser tolerance
