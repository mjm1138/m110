"""Generate gallery thumbnails, hero images, and the images.json manifest.

Focused port of build_site.py's image pipeline + generate_hero.py. Writes into
<data_root>/site/img/ (thumbnails), site/img/hero/<slug>.jpg (heroes), and
data/derived/images.json (the manifest the UI reads). Thumbnails are cached by
content hash (mtime+size), so re-runs are cheap.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import config, objects
from .display_names import display_name_for_image

IMG_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".fit", ".fits")
VIEWABLE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")
PHOTO_EXTS = (".jpg", ".jpeg", ".png")
THUMB_W = 480
HERO_SIZE = 1200
_IMG_CACHE_VER = b"v5"

_INTERMEDIATE_FIT_RE = re.compile(r"_(og|crop|stretch|stretched|spcc)(_|\.)", re.IGNORECASE)
HERO_TIERS = ["Finished Images", "FITS", "Seestar_stacks"]


def _is_intermediate_fit(path: Path) -> bool:
    if path.suffix.lower() not in (".fit", ".fits"):
        return False
    return bool(_INTERMEDIATE_FIT_RE.search(path.name))


def folders_for_slug(slug: str, by_folder: dict) -> list[str]:
    return [f for f, info in by_folder.items() if slug in info.get("slugs", [])]


def img_hash(path: Path) -> str:
    """Content-based cache key (mtime + size), move-stable."""
    st = path.stat()
    h = hashlib.sha1()
    h.update(str(st.st_mtime).encode())
    h.update(str(st.st_size).encode())
    h.update(_IMG_CACHE_VER)
    return h.hexdigest()[:12]


def _open_image(src: Path):
    """Open a raster / float-TIF / FITS source as a full-res RGB PIL image, or
    None. FITS and float TIF are percentile-stretched so a preview is visible."""
    try:
        from PIL import Image
    except ImportError:
        return None
    suffix = src.suffix.lower()
    try:
        if suffix in (".fit", ".fits"):
            from astropy.io import fits
            import numpy as np
            with fits.open(src) as hdul:
                data = next((h.data for h in hdul if h.data is not None), None)
                if data is None:
                    return None
                if data.ndim == 3 and data.shape[0] == 3:
                    data = np.transpose(data, (1, 2, 0))
                arr = data.astype("float32")
                lo, hi = np.percentile(arr, [1, 99.5])
                if hi <= lo:
                    return None
                arr = (np.clip((arr - lo) / (hi - lo), 0, 1) * 255).astype("uint8")
                return (Image.fromarray(arr, "L").convert("RGB")
                        if arr.ndim == 2 else Image.fromarray(arr, "RGB"))
        if suffix in (".tif", ".tiff"):
            import tifffile
            import numpy as np
            arr = tifffile.imread(src)
            if arr.dtype in (np.float32, np.float64):
                lo, hi = np.percentile(arr, [0.5, 99.7])
                if hi <= lo:
                    hi = arr.max() or 1.0
                    lo = arr.min()
                arr = (np.clip((arr - lo) / (hi - lo), 0, 1) * 255).astype("uint8")
            elif arr.dtype == np.uint16:
                arr = (arr / 256).astype("uint8")
            if arr.ndim == 2:
                return Image.fromarray(arr, "L").convert("RGB")
            if arr.ndim == 3 and arr.shape[2] >= 3:
                return Image.fromarray(arr[..., :3], "RGB")
            return None
        img = Image.open(src)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        return img
    except Exception as e:
        print(f"  image open failed for {src.name}: {e}")
        return None


def make_thumb(src: Path, dest_dir: Path) -> Path | None:
    """JPG thumbnail for src into dest_dir (cached, content-hashed). Handles
    png/jpg, float TIF, and FITS. Returns the output path or None."""
    out = dest_dir / f"{img_hash(src)}.jpg"
    if out.exists():
        return out
    img = _open_image(src)
    if img is None:
        return None
    try:
        img.thumbnail((THUMB_W, THUMB_W * 4))
        img.save(out, "JPEG", quality=85, optimize=True)
        return out
    except Exception as e:
        print(f"  thumb save failed for {src.name}: {e}")
        return None


def discover_images(slug: str, folders: list[str], by_folder: dict) -> list[dict]:
    imgs = config.IMAGES_DIR
    out = []
    for fname in folders:
        n_slugs = (len(by_folder.get(fname, {}).get("slugs", [])) or 1) if by_folder else 1
        for src_dir, label in [
            (imgs / "Finished Images" / fname, "Finished render"),
            (imgs / "FITS" / fname, "Siril stack"),
            (imgs / "FITS" / fname / "stacks", "Siril stack"),
            (imgs / "Seestar_stacks" / fname, "Seestar in-app stack"),
        ]:
            if not src_dir.is_dir():
                continue
            for f in sorted(src_dir.iterdir()):
                if not f.is_file() or f.suffix.lower() not in IMG_EXTS:
                    continue
                if "_thn." in f.name or _is_intermediate_fit(f):
                    continue
                st = f.stat()
                out.append({
                    "path": f, "name": f.name,
                    "display_name": display_name_for_image(f, fname, n_slugs),
                    "label": label, "size_mb": round(st.st_size / (1024 * 1024), 1),
                    "mtime": st.st_mtime, "viewable": f.suffix.lower() in VIEWABLE_EXTS,
                })
    out.sort(key=lambda im: -im["mtime"])
    return out


# ── hero selection (tier order: Finished → FITS → Seestar; PNG > JPG, newest) ──

def _photos_in(d: Path) -> list[Path]:
    if not d.is_dir():
        return []
    return [f for f in d.iterdir() if f.is_file() and not f.name.startswith(".")
            and f.suffix.lower() in PHOTO_EXTS]


def _hero_sort_key(p: Path):
    return (0 if p.suffix.lower() == ".png" else 1, -p.stat().st_mtime)


def find_hero_source(folders: list[str]) -> Path | None:
    for tier in HERO_TIERS:
        cands = []
        for fname in folders:
            cands += _photos_in(config.IMAGES_DIR / tier / fname)
        if cands:
            cands.sort(key=_hero_sort_key)
            return cands[0]
    return None


def _hero_source(slug: str, folders: list[str], imgs: list[dict]) -> Path | None:
    """Honour frontmatter overrides (hero: display-name, or hero_image: path),
    else fall back to tier auto-discovery."""
    fm, _ = objects.read_journal(slug)
    name = fm.get("hero")
    if name:
        for im in imgs:
            if im.get("display_name") == name or im.get("name") == name:
                return im["path"]
    hp = fm.get("hero_image")
    if hp:
        p = config.DATA_ROOT / hp
        if p.is_file():
            return p
    # Prefer a raster (jpg/png) photo via the tier order; otherwise fall back to
    # the newest discovered image — which may be a FITS stack (rendered below).
    photo = find_hero_source(folders)
    if photo:
        return photo
    return imgs[0]["path"] if imgs else None


def _render_hero(src: Path, dst: Path) -> bool:
    img = _open_image(src)   # handles raster / TIF / FITS
    if img is None:
        return False
    try:
        img.thumbnail((HERO_SIZE, HERO_SIZE))
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, "JPEG", quality=90, optimize=True)
        return True
    except Exception as e:
        print(f"  hero save failed for {src.name}: {e}")
        return False


def render_images(catalog: dict, totals: dict, slugs=None, progress=None) -> dict:
    """Generate thumbnails + heroes for captured objects and write images.json."""
    by_folder = totals.get("by_folder", {})
    site_img = config.SITE_DIR / "img"
    hero_dir = site_img / "hero"
    site_img.mkdir(parents=True, exist_ok=True)
    hero_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, list] = {}
    targets = list(slugs) if slugs is not None else list(catalog.keys())
    for i, slug in enumerate(targets, 1):
        folders = folders_for_slug(slug, by_folder)
        if not folders:
            continue
        imgs = discover_images(slug, folders, by_folder)
        if not imgs:
            continue
        entries = []
        for im in imgs:
            # Thumbnail every discovered image, including FITS stacks (rendered
            # via a percentile stretch) — so even .fit-only objects show a preview.
            tp = make_thumb(im["path"], site_img)
            entries.append({"name": im["name"], "display_name": im["display_name"],
                            "label": im["label"], "size_mb": im["size_mb"],
                            "mtime": im["mtime"], "viewable": im["viewable"],
                            "thumb": f"img/{tp.name}" if tp else None, "full": None})
        manifest[slug] = entries
        src = _hero_source(slug, folders, imgs)
        if src:
            _render_hero(src, hero_dir / f"{slug}.jpg")
        if progress:
            progress(i, len(targets))

    config.DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    (config.DERIVED_DIR / "images.json").write_text(json.dumps(manifest, indent=2))
    return {"slugs": len(manifest)}
