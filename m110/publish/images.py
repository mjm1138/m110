"""Web image derivatives for the published site.

Writes into `<output>/img/`: gallery thumbnails (480px JPEG) + full-size lightbox
images (≤1920px JPEG) + per-object hero copies. Reuses `build_images`' raster /
float-TIF / FITS opener, content-hash cache key, and gallery discovery so the
publish path can't drift from the in-app render path. Qt-free.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .. import build_images, config

FULL_MAX = 1920  # longest-edge cap for lightbox images


def make_full(src: Path, dest_dir: Path) -> Path | None:
    """Full-size lightbox JPEG (≤FULL_MAX px) for a viewable source, cached by
    content hash. FITS isn't directly viewable, so callers skip it."""
    if src.suffix.lower() not in build_images.VIEWABLE_EXTS:
        return None
    out = dest_dir / f"{build_images.img_hash(src)}.jpg"
    if out.exists():
        return out
    img = build_images._open_image(src)
    if img is None:
        return None
    try:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > FULL_MAX:
            from PIL import Image
            img.thumbnail((FULL_MAX, FULL_MAX), Image.LANCZOS)
        dest_dir.mkdir(parents=True, exist_ok=True)
        img.save(out, "JPEG", quality=90, optimize=True)
        return out
    except Exception as e:  # pragma: no cover - defensive
        print(f"  full-size failed for {src.name}: {e}")
        return None


def emit_gallery(slug: str, folders: list[str], by_folder: dict,
                 img_dir: Path, *, galleries: bool) -> list[dict]:
    """Discover an object's gallery images and emit web derivatives into
    `img_dir`. With `galleries=False` returns no records (gallery omitted)."""
    if not galleries:
        return []
    img_dir.mkdir(parents=True, exist_ok=True)
    full_dir = img_dir / "full"
    records = []
    for im in build_images.discover_images(slug, folders, by_folder):
        thumb = build_images.make_thumb(im["path"], img_dir)
        full = make_full(im["path"], full_dir) if im["viewable"] else None
        records.append({
            "name": im["name"],
            "label": im["label"],
            "size_mb": im["size_mb"],
            "mtime": im["mtime"],
            "viewable": im["viewable"],
            "thumb": f"img/{thumb.name}" if thumb else None,
            "full": f"img/full/{full.name}" if full else None,
        })
    return records


def emit_hero(slug: str, img_dir: Path) -> str | None:
    """Copy the already-generated hero (`renders/hero/<slug>.jpg`) into the site
    as `img/hero/<slug>.jpg`. Returns the site-relative path or None."""
    src = config.HERO_DIR / f"{slug}.jpg"
    if not src.is_file():
        return None
    hero_dir = img_dir / "hero"
    hero_dir.mkdir(parents=True, exist_ok=True)
    dst = hero_dir / f"{slug}.jpg"
    shutil.copyfile(src, dst)
    return f"img/hero/{slug}.jpg"
