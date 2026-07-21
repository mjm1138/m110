"""Export a finished image sized for web sharing (Reddit / Discord / forums).

Takes any finished image — a Siril ``.png``, a finished ``.fit`` / ``.tif``, or
any raster — and produces the highest-quality file that fits a chosen byte
budget, trying the *least*-destructive lever first:

* **lossless** strategy: an optimized lossless PNG, and only if that's over the
  budget, downscale (Lanczos) to the largest size that still fits losslessly.
* **quality** strategy: a full-resolution high-quality JPEG (4:4:4, no chroma
  subsampling — critical for stars). The explicit lossy alternative for when
  you'd rather keep every pixel than stay lossless.

Reuses :func:`build_images._open_image` as the front end, so the exported pixels
match what the app shows (FITS / float-TIF are percentile-stretched to 8-bit
RGB). Qt-free — the UI (``ui/export_dialog.py``) drives it on a worker thread.

Non-goals (v1): no 16-bit-preserving export — everything normalizes to 8-bit
RGB, the correct baseline for a display/share deliverable. A finished-but-
*linear* ``.fit`` is percentile-stretched, not curated; export from the finished
PNG for a curated result. ``pyoxipng`` is an optional accelerator (best-effort
import), never a required dependency.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import build_images

# Leave headroom under the platform ceiling for its own re-container / rounding
# (a 20 MB preset targets ~19.4 MB).
SAFETY_MARGIN = 0.03
# Don't binary-search below this long edge before giving up on a lossless fit.
MIN_LONG_EDGE = 1280
# Quality-strategy JPEG quality ladder (all at subsampling=0 / 4:4:4).
_JPEG_QUALITY_STEPS = (95, 92, 90, 85, 80)

_MB = 1024 * 1024


@dataclass(frozen=True)
class SharePreset:
    """A named size budget for a sharing destination."""
    id: str
    label: str
    max_bytes: int
    formats: tuple[str, ...]          # allowed output formats, preference order
    max_dim: int | None = None        # optional platform long-edge display cap
    note: str = ""                    # caveat shown in the dialog


PRESETS: list[SharePreset] = [
    SharePreset(
        "reddit", "Reddit (20 MB)", 20 * _MB, ("png", "jpeg"),
        note="Reddit re-compresses uploads — lossless mainly helps destinations "
             "that keep your original file."),
    SharePreset("discord", "Discord (10 MB)", 10 * _MB, ("png", "jpeg")),
    SharePreset("custom", "Custom…", 20 * _MB, ("png", "jpeg")),
]
PRESETS_BY_ID = {p.id: p for p in PRESETS}


@dataclass
class ExportResult:
    dest: Path
    format: str                       # "png" | "jpeg"
    width: int
    height: int
    size_bytes: int
    lossless: bool
    downscaled: bool
    steps: list[str] = field(default_factory=list)

    @property
    def size_mb(self) -> float:
        return self.size_bytes / _MB


class ExportError(Exception):
    """The export couldn't produce a file within the requested budget."""


# --------------------------------------------------------------------------- #
# Format helpers — the output format is deterministic from (strategy, preset),
# so the UI knows the extension before it opens the native save panel.
# --------------------------------------------------------------------------- #
def format_for(strategy: str, preset: SharePreset) -> str:
    """The single output format a (strategy, preset) pair produces. Lossless →
    PNG; quality → JPEG (falling back to the preset's first allowed format)."""
    if strategy == "quality":
        return "jpeg" if "jpeg" in preset.formats else preset.formats[0]
    return "png" if "png" in preset.formats else preset.formats[0]


def ext_for_format(fmt: str) -> str:
    return ".jpg" if fmt == "jpeg" else f".{fmt}"


def normalize_dest(dest, strategy: str, preset: SharePreset) -> Path:
    """Force `dest`'s extension to match the format the export will write, so a
    user who cleared/changed it in the save panel still gets a valid file."""
    dest = Path(dest)
    want = ext_for_format(format_for(strategy, preset))
    accepted = {".jpg", ".jpeg"} if want == ".jpg" else {want}
    if dest.suffix.lower() in accepted:
        return dest
    return dest.with_suffix(want)


def suggested_name(stem: str, preset: SharePreset, strategy: str) -> str:
    """A pre-fill filename for the save panel, e.g. ``M101-reddit.png``."""
    stem = (stem or "image").strip() or "image"
    return f"{stem}-{preset.id}{ext_for_format(format_for(strategy, preset))}"


def _fmt_mb(n: int) -> str:
    return f"{n / _MB:.1f} MB"


# --------------------------------------------------------------------------- #
# Encoders
# --------------------------------------------------------------------------- #
def _oxipng(png_bytes: bytes) -> bytes:
    """Losslessly shrink PNG bytes with pyoxipng if it's installed, else return
    them unchanged (best-effort accelerator, never a hard dependency)."""
    try:
        import oxipng
    except Exception:
        return png_bytes
    try:
        return oxipng.optimize_from_memory(png_bytes, level=3)
    except Exception:
        return png_bytes


def _encode_png(img, *, final: bool) -> bytes:
    """PNG bytes. During the downscale search we favour speed; for the chosen
    size we compress hard and run oxipng if available."""
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=final, compress_level=9 if final else 6)
    data = buf.getvalue()
    return _oxipng(data) if final else data


def _encode_jpeg(img, quality: int) -> bytes:
    from PIL import ImageFile
    # `optimize=True` buffers a whole Huffman-optimization pass; the default
    # MAXBLOCK (64 KB) overflows on large frames → "broken data stream". Size it
    # to the raw upper bound. (Baseline, not progressive — progressive tripped
    # the same encoder on incompressible frames and buys nothing here: Reddit &
    # co. re-encode uploads anyway.)
    ImageFile.MAXBLOCK = max(ImageFile.MAXBLOCK, img.width * img.height * 3)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, subsampling=0, optimize=True)
    return buf.getvalue()


def _resized(img, long_edge: int):
    """Lanczos-resize so the longest edge is `long_edge` (no upscaling)."""
    from PIL import Image
    w, h = img.size
    if max(w, h) <= long_edge:
        return img
    if w >= h:
        nw, nh = long_edge, max(1, round(h * long_edge / w))
    else:
        nh, nw = long_edge, max(1, round(w * long_edge / h))
    return img.resize((nw, nh), Image.LANCZOS)


def _atomic_write(dest: Path, data: bytes) -> None:
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, dest)


# --------------------------------------------------------------------------- #
# The ladder
# --------------------------------------------------------------------------- #
def export_for_sharing(src, preset: SharePreset, dest, *, strategy: str = "lossless",
                       max_bytes: int | None = None, jpeg_quality: int = 95,
                       progress=None, status=None, should_cancel=None) -> ExportResult:
    """Write `src` to `dest` sized within the budget, best quality first.

    `strategy` is ``"lossless"`` (PNG, downscale to fit) or ``"quality"``
    (full-resolution high-q JPEG). `progress(done, total)` / `status(label)` feed
    the UI; `should_cancel()` is polled between encode attempts. Raises
    :class:`ExportError` if no file within budget can be produced.
    """
    src, dest = Path(src), Path(dest)
    budget = int((max_bytes or preset.max_bytes) * (1 - SAFETY_MARGIN))
    steps: list[str] = []

    def emit(msg: str) -> None:
        steps.append(msg)
        if status:
            status(msg)

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    if cancelled():
        raise ExportError("Cancelled.")

    # --- fast path: a lossless original that already fits, copied verbatim ---
    src_ext = src.suffix.lower().lstrip(".")
    if (strategy == "lossless" and src_ext == "png" and "png" in preset.formats
            and src.stat().st_size <= budget):
        from PIL import Image
        try:
            with Image.open(src) as probe:
                w, h = probe.size
        except Exception:
            w = h = None
        if w is not None and (preset.max_dim is None or max(w, h) <= preset.max_dim):
            _atomic_write(dest, src.read_bytes())
            emit(f"Copied the original ({_fmt_mb(dest.stat().st_size)}) — "
                 f"already within budget.")
            return ExportResult(dest, "png", w, h, dest.stat().st_size,
                                lossless=True, downscaled=False, steps=steps)

    if cancelled():
        raise ExportError("Cancelled.")
    if progress:
        progress(0, 1)

    img = build_images._open_image(src)
    if img is None:
        raise ExportError(f"Couldn't read {src.name} as an image.")
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Platform display cap — never upload more pixels than the platform shows.
    if preset.max_dim is not None:
        before = img.size
        img = _resized(img, preset.max_dim)
        if img.size != before:
            emit(f"Capped to {img.width}×{img.height} (platform maximum).")

    full_size = img.size
    if strategy == "quality":
        return _export_quality(img, dest, budget, jpeg_quality, full_size,
                               steps, emit, cancelled, progress)
    return _export_lossless(img, dest, budget, full_size, steps, emit,
                            cancelled, progress)


def _fit_by_downscale(img, budget: int, encode, *, cancelled, emit, progress):
    """Binary-search the long edge for the largest image whose `encode(img)`
    fits `budget`. Returns the winning (PIL image). Raises ExportError if even
    MIN_LONG_EDGE is over budget."""
    lo, hi = MIN_LONG_EDGE, max(img.size)
    best = None
    done, total = 0, max(1, (hi - lo).bit_length())
    while lo <= hi:
        if cancelled():
            raise ExportError("Cancelled.")
        mid = (lo + hi) // 2
        cand = _resized(img, mid)
        size = len(encode(cand))
        done += 1
        if progress:
            progress(min(done, total), total)
        fits = size <= budget
        emit(f"{cand.width}×{cand.height}: {_fmt_mb(size)}"
             + (" ✓" if fits else " (over)"))
        if fits:
            best = cand
            lo = mid + 1          # can we keep more resolution?
        else:
            hi = mid - 1          # go smaller
    if best is None:
        raise ExportError("over-budget")
    return best


def _export_lossless(img, dest, budget, full_size, steps, emit, cancelled, progress):
    if cancelled():
        raise ExportError("Cancelled.")
    data = _encode_png(img, final=True)
    fits = len(data) <= budget
    emit(f"Lossless PNG {img.width}×{img.height}: {_fmt_mb(len(data))}"
         + (" ✓" if fits else " (over)"))
    if fits:
        _atomic_write(dest, data)
        return ExportResult(dest, "png", img.width, img.height, len(data),
                            lossless=True, downscaled=False, steps=steps)

    try:
        best = _fit_by_downscale(img, budget, lambda im: _encode_png(im, final=False),
                                 cancelled=cancelled, emit=emit, progress=progress)
    except ExportError as e:
        if str(e) == "over-budget":
            raise ExportError(
                f"Can't fit within {_fmt_mb(budget)} losslessly even at "
                f"{MIN_LONG_EDGE}px. Try 'Keep full resolution (JPEG)' instead.")
        raise
    final = _encode_png(best, final=True)
    _atomic_write(dest, final)
    return ExportResult(dest, "png", best.width, best.height, len(final),
                        lossless=True, downscaled=True, steps=steps)


def _export_quality(img, dest, budget, jpeg_quality, full_size, steps, emit,
                    cancelled, progress):
    # Full resolution first; drop quality, then (last resort) downscale.
    for q in (jpeg_quality, *[s for s in _JPEG_QUALITY_STEPS if s < jpeg_quality]):
        if cancelled():
            raise ExportError("Cancelled.")
        data = _encode_jpeg(img, q)
        fits = len(data) <= budget
        emit(f"JPEG q{q} {img.width}×{img.height}: {_fmt_mb(len(data))}"
             + (" ✓" if fits else " (over)"))
        if fits:
            _atomic_write(dest, data)
            return ExportResult(dest, "jpeg", img.width, img.height, len(data),
                                lossless=False, downscaled=False, steps=steps)

    q = _JPEG_QUALITY_STEPS[-1]
    try:
        best = _fit_by_downscale(img, budget, lambda im: _encode_jpeg(im, q),
                                 cancelled=cancelled, emit=emit, progress=progress)
    except ExportError as e:
        if str(e) == "over-budget":
            raise ExportError(
                f"Can't fit within {_fmt_mb(budget)} even at {MIN_LONG_EDGE}px.")
        raise
    final = _encode_jpeg(best, q)
    _atomic_write(dest, final)
    return ExportResult(dest, "jpeg", best.width, best.height, len(final),
                        lossless=False, downscaled=True, steps=steps)
