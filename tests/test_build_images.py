"""Tests for thumbnail/hero/manifest generation (temp fixtures + real PIL)."""
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
    monkeypatch.setattr(config, "DATA_ROOT", root)
    monkeypatch.setattr(config, "IMAGES_DIR", root / "Images")
    monkeypatch.setattr(config, "DERIVED_DIR", root / "data" / "derived")
    monkeypatch.setattr(config, "SITE_DIR", root / "site")
    monkeypatch.setattr(config, "OBJECTS_DIR", root / "data" / "objects")
    return root


def test_render_generates_thumb_hero_manifest(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    # a finished render for M99 in the highest hero tier
    _png(root / "Images" / "Finished Images" / "M99" / "M99_final.png")

    catalog = {"m99": {"id": "M99", "name": "Test"}}
    totals = {"by_folder": {"M99": {"slugs": ["m99"]}}, "by_slug": {}}

    result = build_images.render_images(catalog, totals)
    assert result["slugs"] == 1

    # manifest written with a thumb path
    manifest = json.loads((root / "data" / "derived" / "images.json").read_text())
    assert "m99" in manifest
    entry = manifest["m99"][0]
    assert entry["viewable"] is True
    assert entry["thumb"] and (root / "site" / entry["thumb"]).is_file()

    # hero rendered
    assert (root / "site" / "img" / "hero" / "m99.jpg").is_file()


def test_thumb_is_cached(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    src = root / "Images" / "Finished Images" / "M99" / "x.png"
    _png(src)
    site_img = root / "site" / "img"
    site_img.mkdir(parents=True)
    a = build_images.make_thumb(src, site_img)
    b = build_images.make_thumb(src, site_img)  # second call hits cache
    assert a == b and a.is_file()


def test_uncaptured_slug_skipped(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    catalog = {"m1": {"id": "M1"}}
    totals = {"by_folder": {}, "by_slug": {}}   # no folders → nothing to render
    result = build_images.render_images(catalog, totals)
    assert result["slugs"] == 0
