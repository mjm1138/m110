"""Rendering an object's image to in-memory JPEG bytes, for vision.

Kept out of `tools/images.py` on purpose: this is the one component that
touches the image pipeline, which is where an accidental disk write would most
plausibly creep in. Isolating it gives the read-only audit a single file to
scrutinise.

Explicitly NOT `webexport.export_for_sharing` — that writes its result to disk
(`_atomic_write`) and would break the read-only guarantee on the very first
vision call. The pure pieces are what we want:

    build_images._open_image  ->  webexport.resize_long_edge  ->  encode_jpeg

`_open_image` percentile-stretches FITS and float TIFs so a linear stack is
*visible* at all — which means what the model sees is M110's preview rendering,
not the user's processing. The metadata says so, and the critique skill is
required to disclose it; otherwise a model "critiques" a flat grey frame that
the user never produced.
"""
from __future__ import annotations

import base64
import threading
from pathlib import Path

from m110 import build_images, derived, objects as journals, webexport
from m110.assistant.registry import ToolError

# Claude's vision sweet spot: ~1.15 MP, enough to judge star shape and gradients
# without paying for detail the model can't use.
DEFAULT_LONG_EDGE = 1568
MAX_LONG_EDGE = 2576
# The client re-emits our bytes as an API image block, and the Messages API caps
# those at 5 MB base64. Base64 inflates by 4/3, so hold the encoded payload here
# and the wire stays inside the limit. Blowing it produces a 413 the user cannot
# diagnose.
MAX_ENCODED_BYTES = 3_500_000
QUALITY_LADDER = (85, 75, 65)

# A 300 MP FITS decodes to hundreds of MB. `_open_image` already caps pixels;
# this stops two concurrent calls from stacking their peaks.
_RENDER_LOCK = threading.Lock()
MAX_SOURCE_BYTES = 500 * 1024 * 1024

_LINEAR_SUFFIXES = {".fit", ".fits"}
_STRETCHED_SUFFIXES = _LINEAR_SUFFIXES | {".tif", ".tiff"}


def resolve_source(slug: str, which: str, name: str | None) -> tuple[Path, dict]:
    """Pick which file to show, and describe it. Returns (path, source_meta)."""
    gallery = derived.images_for(slug) if derived.derived_available() else []

    if which == "named":
        if not name:
            raise ToolError("which='named' requires a name; call get_object to list them.")
        row = next((i for i in gallery if i.get("name") == name), None)
        if row is None:
            available = ", ".join(i.get("name", "") for i in gallery) or "(none)"
            raise ToolError(f"No image named {name!r} for {slug}. Available: {available}")
        return _from_row(slug, row)

    if which == "finished":
        curation = journals.get_curation(slug)
        finished = [i for i in gallery
                    if journals.image_state(i.get("name", ""), i.get("label", ""),
                                            curation) == "finished"]
        if not finished:
            raise ToolError(
                f"{slug} has no finished image. Use which='hero' for its main render, "
                "or get_object to see what is on disk."
            )
        return _from_row(slug, max(finished, key=lambda i: i.get("mtime") or 0))

    # hero — go to the ORIGINAL source, via the .src sidecar. objects.hero_path
    # returns the 1200px hero JPG, and judging star shape on an already
    # downscaled, re-compressed thumbnail is worse than useless.
    src = build_images.hero_source_path(slug)
    if src and Path(src).is_file():
        row = next((i for i in gallery if i.get("name") == Path(src).name), {})
        return Path(src), _describe(slug, Path(src), row.get("label") or "hero source")

    fallback = journals.hero_path(slug)
    if fallback and Path(fallback).is_file():
        return Path(fallback), _describe(slug, Path(fallback), "hero (rendered preview)",
                                         is_preview=True)
    raise ToolError(f"{slug} has no images yet.")


def _from_row(slug: str, row: dict) -> tuple[Path, dict]:
    from m110 import config
    rel = row.get("src") or row.get("full") or ""
    path = Path(config.DATA_ROOT) / rel
    if not path.is_file():
        raise ToolError(f"{row.get('name')} is listed for {slug} but missing on disk.")
    return path, _describe(slug, path, row.get("label") or "", row=row)


def _describe(slug: str, path: Path, tier: str, *, row: dict | None = None,
              is_preview: bool = False) -> dict:
    suffix = path.suffix.lower()
    return {
        "name": path.name,
        "tier": tier,
        "was_linear_fits": suffix in _LINEAR_SUFFIXES,
        "auto_stretched": suffix in _STRETCHED_SUFFIXES,
        "is_rendered_preview": is_preview,
        "source_size_mb": round(path.stat().st_size / 1_048_576, 2),
        "state": (row or {}).get("state"),
    }


def render(path: Path, max_long_edge: int = DEFAULT_LONG_EDGE) -> dict:
    """Decode, downscale and JPEG-encode in memory. Nothing touches disk."""
    if max_long_edge > MAX_LONG_EDGE:
        raise ToolError(
            f"max_long_edge is capped at {MAX_LONG_EDGE}; {max_long_edge} would exceed "
            "what a vision model can use and what the API accepts."
        )
    size = path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ToolError(
            f"{path.name} is {size / 1_048_576:.0f} MB — too large to decode safely."
        )

    with _RENDER_LOCK:
        img = build_images._open_image(path)
        if img is None:
            raise ToolError(f"Could not decode {path.name}.")
        source_w, source_h = img.size

        long_edge = max_long_edge
        for quality in QUALITY_LADDER:
            scaled = webexport.resize_long_edge(img, long_edge)
            data = webexport.encode_jpeg(scaled, quality)
            if len(data) <= MAX_ENCODED_BYTES:
                break
        else:
            # Still too big at the lowest quality: halve the edge until it fits.
            while len(data) > MAX_ENCODED_BYTES and long_edge > 256:
                long_edge //= 2
                scaled = webexport.resize_long_edge(img, long_edge)
                data = webexport.encode_jpeg(scaled, QUALITY_LADDER[-1])

    return {
        "bytes": data,
        "base64": base64.b64encode(data).decode("ascii"),
        "mime_type": "image/jpeg",
        "width": scaled.width,
        "height": scaled.height,
        "source_width": source_w,
        "source_height": source_h,
        "downscaled": (scaled.width, scaled.height) != (source_w, source_h),
        "jpeg_quality": quality,
        "encoded_bytes": len(data),
    }
