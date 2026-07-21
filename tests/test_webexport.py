"""Tests for the size-budgeted web-share image exporter (`m110.webexport`).

Self-contained: images are generated with Pillow/numpy into tmp_path, so these
never touch the store. Noise images are used where an incompressible source is
needed to force the downscale ladder deterministically.
"""
from __future__ import annotations

import sys
from datetime import date

import numpy as np
import pytest
from PIL import Image

from m110 import webexport as wx

_MB = 1024 * 1024


def _noise_png(path, w, h, seed=0):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
    Image.fromarray(arr, "RGB").save(path, "PNG")
    return path


def _gradient_fits(path, w=600, h=400):
    from astropy.io import fits
    y, x = np.mgrid[0:h, 0:w]
    data = ((x + y).astype("float32"))
    data += np.random.default_rng(1).normal(0, 5, data.shape).astype("float32")
    fits.PrimaryHDU(data).writeto(path)
    return path


# --------------------------------------------------------------------------- #
# format + filename helpers
# --------------------------------------------------------------------------- #
def test_format_for():
    assert wx.format_for("lossless") == "png"
    assert wx.format_for("quality") == "jpeg"


def test_normalize_dest_fixes_extension(tmp_path):
    assert wx.normalize_dest(tmp_path / "x.foo", "lossless").suffix == ".png"
    assert wx.normalize_dest(tmp_path / "x.txt", "quality").suffix == ".jpg"
    # an already-valid extension is left untouched (jpg/jpeg both accepted)
    assert wx.normalize_dest(tmp_path / "x.jpeg", "quality").suffix == ".jpeg"
    assert wx.normalize_dest(tmp_path / "x.png", "lossless").suffix == ".png"


def test_size_label():
    assert wx.size_label(20.0) == "20mb"
    assert wx.size_label(15.5) == "15.5mb"
    assert wx.size_label(None) == "nomax"


def test_suggested_name():
    day = date(2026, 7, 21)
    assert wx.suggested_name("M42", 20.0, "lossless", day) == "M42-20mb-20260721.png"
    assert wx.suggested_name("M42", None, "quality", day) == "M42-nomax-20260721.jpg"
    assert wx.suggested_name("", 20, "lossless", day) == "image-20mb-20260721.png"


# --------------------------------------------------------------------------- #
# the ladder
# --------------------------------------------------------------------------- #
def test_fast_path_copies_original_verbatim(tmp_path):
    src = _noise_png(tmp_path / "src.png", 120, 120)
    dest = tmp_path / "out.png"
    res = wx.export_for_sharing(src, dest, strategy="lossless", max_bytes=20 * _MB)
    assert res.format == "png" and res.lossless and not res.downscaled
    assert dest.read_bytes() == src.read_bytes()   # byte-identical copy
    assert res.size_bytes == src.stat().st_size


def test_lossless_downscales_to_fit(tmp_path):
    src = _noise_png(tmp_path / "big.png", 2000, 2000)
    dest = tmp_path / "out.png"
    budget = 6 * _MB
    res = wx.export_for_sharing(src, dest, strategy="lossless", max_bytes=budget)
    assert res.format == "png" and res.lossless and res.downscaled
    assert res.size_bytes <= int(budget * (1 - wx.SAFETY_MARGIN))
    assert max(res.width, res.height) < 2000
    assert max(res.width, res.height) >= wx.MIN_LONG_EDGE
    assert dest.stat().st_size == res.size_bytes


def test_quality_keeps_full_resolution(tmp_path):
    src = _noise_png(tmp_path / "big.png", 2000, 2000)
    dest = tmp_path / "out.jpg"
    res = wx.export_for_sharing(src, dest, strategy="quality", max_bytes=20 * _MB)
    assert res.format == "jpeg" and not res.lossless and not res.downscaled
    assert (res.width, res.height) == (2000, 2000)   # full resolution retained
    assert res.size_bytes <= int(20 * _MB * (1 - wx.SAFETY_MARGIN))
    assert Image.open(dest).size == (2000, 2000)


def test_no_maximum_lossless_is_full_res_png(tmp_path):
    # An incompressible frame with NO budget must still export at full res.
    src = _noise_png(tmp_path / "big.png", 1600, 1200)
    dest = tmp_path / "out.png"
    res = wx.export_for_sharing(src, dest, strategy="lossless", max_bytes=None)
    assert res.format == "png" and res.lossless and not res.downscaled
    assert (res.width, res.height) == (1600, 1200)
    assert dest.exists()


def test_no_maximum_quality_is_full_res_jpeg(tmp_path):
    src = _noise_png(tmp_path / "big.png", 1600, 1200)
    dest = tmp_path / "out.jpg"
    res = wx.export_for_sharing(src, dest, strategy="quality", max_bytes=None)
    assert res.format == "jpeg" and not res.lossless and not res.downscaled
    assert (res.width, res.height) == (1600, 1200)


def test_fits_source_renders_and_exports(tmp_path):
    src = _gradient_fits(tmp_path / "stack.fit")
    dest = tmp_path / "out.png"
    res = wx.export_for_sharing(src, dest, strategy="lossless", max_bytes=20 * _MB)
    assert res.format == "png" and dest.exists()
    assert Image.open(dest).size == (600, 400)       # rendered at native size


def test_works_without_pyoxipng(tmp_path, monkeypatch):
    # Force the "oxipng not importable" branch regardless of what's installed.
    monkeypatch.setitem(sys.modules, "oxipng", None)
    src = _noise_png(tmp_path / "src.png", 400, 400)
    dest = tmp_path / "out.png"
    res = wx.export_for_sharing(src, dest, strategy="lossless", max_bytes=20 * _MB)
    assert res.format == "png" and dest.exists()


def test_unfittable_lossless_raises(tmp_path):
    src = _noise_png(tmp_path / "big.png", 1500, 1500)
    dest = tmp_path / "out.png"
    with pytest.raises(wx.ExportError):
        # 1 MB can't hold even a MIN_LONG_EDGE-px noise PNG losslessly.
        wx.export_for_sharing(src, dest, strategy="lossless", max_bytes=1 * _MB)
    assert not dest.exists()


def test_status_and_progress_callbacks_fire(tmp_path):
    src = _noise_png(tmp_path / "big.png", 2000, 2000)
    dest = tmp_path / "out.png"
    msgs, prog = [], []
    res = wx.export_for_sharing(
        src, dest, strategy="lossless", max_bytes=6 * _MB,
        status=msgs.append, progress=lambda d, t: prog.append((d, t)))
    assert msgs and res.steps == msgs      # steps mirror the status stream
    assert prog                            # progress reported during the search


def test_cancellation_raises_and_writes_nothing(tmp_path):
    src = _noise_png(tmp_path / "big.png", 1000, 1000)
    dest = tmp_path / "out.png"
    with pytest.raises(wx.ExportError):
        wx.export_for_sharing(src, dest, strategy="lossless", max_bytes=6 * _MB,
                              should_cancel=lambda: True)
    assert not dest.exists()
