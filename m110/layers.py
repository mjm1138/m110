"""Multi-layer FITS: a file that carries more than one image.

DwarfLab's Draco writes an "SHO" capture as **one** FITS with two image HDUs: the
primary is the HO (H-alpha/OIII) stack and an ``EXTNAME='SOO'`` extension is the SO
(SII/OIII) stack (firmware 1.1.0.55, Nov 2026). Every other reader in M110 — and
Siril and AstroWizard — sees only the primary, so the second half of the capture is
invisible unless something names it and can write it out on its own.

This module is that something, and nothing more:

- :func:`image_layers` lists the images in a file from headers alone (cheap enough
  for a scan or a dialog listing).
- :func:`layer_header` builds the header a layer would have as a file of its own:
  the device writes only FILTER/EXPTIME/STACKCNT on the extension, so the rest
  (OBJECT, DATE-OBS, TELESCOP, GAIN, pixel scale…) is inherited from the primary,
  and the layer's own cards win.
- :func:`write_layer` writes one layer as a standalone single-image FITS,
  pixel-exact (the raw integers and their BZERO/BSCALE go across untouched).

The device file itself is never modified: the split happens at handoff, into a
workflow sandbox (``stacking.apply_handoff``), so ``device-stacks/`` keeps exactly
what the telescope wrote. Qt-free.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Cards that describe the HDU's *container*, not the image: never carried from one
# HDU to another blindly. BZERO/BSCALE travel with the data they scale, so
# `write_layer` copies them from the layer itself, not the primary.
_STRUCTURAL = frozenset({
    "SIMPLE", "XTENSION", "BITPIX", "NAXIS", "EXTEND", "PCOUNT", "GCOUNT",
    "EXTNAME", "EXTVER", "BZERO", "BSCALE", "BLANK", "CHECKSUM", "DATASUM", "END",
})

# Provenance card stamped on an extracted layer: which HDU it was.
LAYER_CARD = "M110LAYR"


def _is_structural(key: str) -> bool:
    return key in _STRUCTURAL or (key.startswith("NAXIS") and key[5:].isdigit())


def _fits():
    from astropy.io import fits
    return fits


@dataclass(frozen=True)
class Layer:
    """One image inside a FITS file."""
    index: int                       # HDU index
    name: str                        # EXTNAME, or "PRIMARY"
    filter: str | None = None
    frames: int | None = None        # STACKCNT / NCOMBINE
    exptime: float | None = None     # EXPTIME as written (a total on Draco stacks)

    @property
    def tag(self) -> str:
        """Short, filename-safe name for the layer: its filter, else EXTNAME."""
        raw = (self.filter or self.name or f"HDU{self.index}").strip()
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)
        return safe or f"HDU{self.index}"

    @property
    def label(self) -> str:
        """``"SO 39×"`` — what a list or tooltip shows for the layer."""
        return f"{self.tag} {self.frames}×" if self.frames else self.tag

    def as_dict(self) -> dict:
        return {"index": self.index, "name": self.name, "filter": self.filter,
                "frames": self.frames, "exptime": self.exptime}


def _int(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_image(hdu) -> bool:
    """An image HDU with at least two axes — a binary/ASCII table also says
    NAXIS = 2, so the HDU type decides, not the card."""
    if not getattr(hdu, "is_image", False):
        return False
    try:
        return int(hdu.header.get("NAXIS", 0)) >= 2
    except (TypeError, ValueError):
        return False


def _layer_from_header(index: int, hdr) -> Layer:
    flt = hdr.get("FILTER")
    return Layer(
        index=index,
        name=(str(hdr.get("EXTNAME")).strip() if hdr.get("EXTNAME") else "PRIMARY"),
        filter=(str(flt).strip() or None) if flt not in (None, "") else None,
        frames=_int(hdr.get("STACKCNT")) or _int(hdr.get("NCOMBINE")),
        exptime=_float(hdr.get("EXPTIME")),
    )


def image_layers(path) -> list[Layer]:
    """Every image HDU in ``path`` (image type, NAXIS ≥ 2), in file order.
    Headers only — the pixel data is never read. An ordinary file yields one
    layer; an unreadable or non-FITS file yields ``[]``."""
    try:
        fits = _fits()
        with fits.open(str(path), memmap=True, lazy_load_hdus=True) as hdul:
            out = []
            for i, hdu in enumerate(hdul):
                if _is_image(hdu):
                    out.append(_layer_from_header(i, hdu.header))
            return out
    except Exception:
        return []


def is_multi_layer(path) -> bool:
    return len(image_layers(path)) > 1


def layer_header(primary_hdr, layer_hdr, *, index: int | None = None,
                 source: str | None = None):
    """The header a layer would carry as a file of its own.

    Starts from the primary's descriptive cards (the extension repeats almost
    nothing), then lets the layer's own descriptive cards win — FILTER, EXPTIME and
    STACKCNT are exactly the ones that differ. Structural cards come from neither;
    the writer derives them from the data. For the primary itself (``layer_hdr``
    is ``primary_hdr``) this is just its descriptive cards."""
    fits = _fits()
    out = fits.Header()
    seen: set[str] = set()
    for src in (primary_hdr, layer_hdr):
        for card in src.cards:
            key = card.keyword
            if not key or _is_structural(key) or key in ("COMMENT", "HISTORY", ""):
                continue
            out[key] = (card.value, card.comment)
            seen.add(key)
    for key in ("HISTORY", "COMMENT"):
        lines = [str(v) for v in primary_hdr.get(key, [])]
        if layer_hdr is not primary_hdr:
            lines += [str(v) for v in layer_hdr.get(key, [])]
        for line in lines:
            out[key] = line
    if index is not None and layer_hdr is not primary_hdr:
        name = str(layer_hdr.get("EXTNAME") or f"HDU{index}").strip()
        out[LAYER_CARD] = (name, "M110: layer extracted from a multi-image FITS")
        out["HISTORY"] = (f"M110: layer {name} (HDU {index}) of {source}"
                          if source else f"M110: layer {name} (HDU {index})")
    return out


def read_layer_header(path, index: int):
    """The merged header for layer ``index`` of ``path`` (see :func:`layer_header`).
    Raises ``IndexError`` for a missing HDU and ``ValueError`` for a non-image one."""
    fits = _fits()
    with fits.open(str(path), memmap=True, lazy_load_hdus=True) as hdul:
        if index < 0 or index >= len(hdul):
            raise IndexError(f"{Path(path).name} has no HDU {index}")
        if not _is_image(hdul[index]):
            raise ValueError(f"HDU {index} of {Path(path).name} is not an image")
        layer = hdul[index].header
        primary = hdul[0].header
        return layer_header(primary, layer if index else primary,
                            index=index, source=Path(path).name)


def write_layer(src, index: int, dest) -> Path:
    """Write layer ``index`` of ``src`` to ``dest`` as a single-image FITS.

    Pixel-exact: the stored integers are copied unscaled together with the layer's
    own BZERO/BSCALE, so a uint16 stack stays uint16. Written to ``dest.part`` and
    moved into place, so a cancelled or failed write never leaves a half file under
    the real name. ``src`` is opened read-only and never modified."""
    fits = _fits()
    src, dest = Path(src), Path(dest)
    with fits.open(str(src), memmap=False, do_not_scale_image_data=True) as hdul:
        if index < 0 or index >= len(hdul):
            raise IndexError(f"{src.name} has no HDU {index}")
        hdu = hdul[index]
        if not _is_image(hdu) or hdu.data is None:
            raise ValueError(f"HDU {index} of {src.name} is not an image")
        hdr = layer_header(hdul[0].header, hdu.header if index else hdul[0].header,
                           index=index, source=src.name)
        out = fits.PrimaryHDU(data=hdu.data, header=hdr,
                              do_not_scale_image_data=True)
        for key in ("BZERO", "BSCALE", "BLANK"):
            if key in hdu.header:
                out.header[key] = hdu.header[key]
        part = dest.with_name(dest.name + ".part")
        try:
            out.writeto(str(part), overwrite=True, output_verify="silentfix")
            os.replace(part, dest)
        finally:
            if part.exists():
                part.unlink()
    return dest


def describe(entries) -> str:
    """One line naming the layers of a multi-layer file, from `images.json`'s
    ``layers`` dicts (or :class:`Layer` objects): ``"2 layers — HO 20 frames ·
    SO 39 frames"``. Frame counts only: EXPTIME is a total on a Draco on-device
    stack but per-frame on DwarfLab's offline ones, so no exposure is derived.
    Empty for a single-layer file."""
    items = [e if isinstance(e, Layer) else Layer(
                 index=int(e.get("index") or 0), name=str(e.get("name") or ""),
                 filter=e.get("filter"), frames=e.get("frames"))
             for e in (entries or [])]
    if len(items) < 2:
        return ""
    parts = [f"{lay.tag} {lay.frames} frames" if lay.frames else lay.tag
             for lay in items]
    return f"{len(items)} layers — " + " · ".join(parts)
