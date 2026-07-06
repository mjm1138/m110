"""Ingest new captures from the 'Inbox' staging area into the collection.

Faithful port of `scan_staging.py`'s classification, but returns a structured
**plan** (list of IngestOp) the GUI previews *before* any move. The actual move
(`apply_ops`) is the only thing that writes into the content tree, and the UI
gates it behind an explicit confirmation — honouring the hard rule "never modify
the content tree without explicit confirmation."

Staging layout recognised:
  <object>_sub/      raw Light_*.fit    → Images/<object>/lights/
  <object>/          in-app stacks      → Images/<object>/seestar-stacks/
  <Category>_photo|_video/  media       → Media/<Category>_photo|_video/
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import catalog, config, hints

try:
    import tomllib
except ImportError:  # pragma: no cover - py<3.11
    import tomli as tomllib  # type: ignore

POINTING_TOL_DEG = 0.15   # frame-vs-catalog separation that flags a name mismatch


class IngestCancelled(Exception):
    """Raised inside a scan when the caller's should_cancel() turns true."""


def _staging() -> Path:
    return config.STAGING_DIR


@dataclass
class IngestOp:
    src: str         # absolute source file
    dest: str        # absolute destination file
    kind: str        # 'light'|'stack'|'media'|'dark'|'flat'|'bias'|'finished'
    group: str       # source directory name
    dest_rel: str    # destination relative to the data root (for display)
    new_object: bool = False  # a new capture-target dir will be created
    action: str = "move"      # 'move' (staging) | 'copy' (device)
    size_bytes: int = 0       # source file size (stat'd on the scan worker)
    layout: str = "seestar"   # recognizer that claimed it (LAYOUTS id)
    object: str = ""          # canonical object/category label this op lands under


@dataclass
class IngestGroup:
    """One source folder's worth of ops, aggregated for a per-object preview."""
    group: str               # source directory name (the selectable unit)
    object: str              # friendly object/category label
    kind: str                # 'light'|'stack'|'media'|'dark'|'flat'|'bias'|'finished'
    frames: int              # number of new files
    size_bytes: int          # total size of the new files
    dest_dir: str            # destination dir, relative to the data root
    new_object: bool
    action: str
    ops: list                # the underlying IngestOps
    pointing: str | None = None    # warning text if the frame's RA/DEC ≠ the name
    suggested: str | None = None   # slug of a better-matching catalog object
    layout: str = "seestar"        # detected source layout (LAYOUTS id)


# ── layout-recognizer registry (6b) ────────────────────────────────────────────
# Names the source layout a directory was classified as, mirroring the
# processing-workflow registry in processing.py. `available=False` entries are
# registered placeholders ("soon") that don't classify yet.

@dataclass(frozen=True)
class Layout:
    id: str
    label: str
    available: bool


LAYOUTS = [
    Layout("seestar",         "Seestar",         True),   # folder-name conventions (_sub/Stacked_/_photo)
    Layout("m110-store",      "M110 store",      True),    # FITS/<obj>/{lights,darks,…}, Finished Images/, Seestar_stacks/
    Layout("raw-fits",        "Raw FITS",        True),    # loose FITS sorted by header
    Layout("finished-render", "Finished render", True),    # a loose *_processed/final raster in an object folder
    Layout("asiair",          "ZWO ASIAIR",      False),   # registered placeholder
]
LAYOUTS_BY_ID = {l.id: l for l in LAYOUTS}


def layout_label(layout_id: str) -> str:
    l = LAYOUTS_BY_ID.get(layout_id)
    return l.label if l else layout_id


# ── classification helpers (ported verbatim) ───────────────────────────────────

def is_media_dir(name: str) -> bool:
    return name.endswith("_photo") or name.endswith("_video")


def fits_object_name(scope_name: str) -> str:
    """Seestar 'M 13' → FITS 'M13'; multi-object names left as-is."""
    return re.sub(r"^M (\d+)$", r"M\1", scope_name)


def is_stacked_fit(filename: str) -> bool:
    return (filename.startswith("Stacked_")
            or filename.startswith("DSO_Stacked_")
            or filename.startswith("Video_Stacked_"))


def _fit_files(d: Path) -> list[str]:
    if not d.is_dir():
        return []
    return sorted(f.name for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() in (".fit", ".fits"))


def _all_files(d: Path) -> list[str]:
    if not d.is_dir():
        return []
    return sorted(f.name for f in d.iterdir()
                  if f.is_file() and not f.name.startswith("."))


def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


# Content file types worth surfacing on import (6c): FITS + image/video. Anything
# else (text/json/sidecars) is not content and is never held.
CONTENT_EXTS = {".fit", ".fits", ".jpg", ".jpeg", ".png", ".tif", ".tiff",
                ".mp4", ".mov", ".avi"}


def _is_content_file(name: str) -> bool:
    """A file worth importing/holding: a content extension, not hidden, not a
    Seestar `*_thn.` thumbnail sidecar."""
    if name.startswith(".") or "_thn." in name:
        return False
    return ("." + name.rsplit(".", 1)[-1].lower()) in CONTENT_EXTS if "." in name else False


def _content_files(d: Path) -> list[str]:
    if not d.is_dir():
        return []
    return sorted(f.name for f in d.iterdir()
                  if f.is_file() and _is_content_file(f.name))


_RASTER_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")
# A finished/processed deliverable bakes its provenance into the filename (e.g. a
# Siril/Naztronomy "…_drizzle…_processed.png"). The finished/intermediate keyword
# vocabulary is user-editable and shared across the app — see `hints.py`.


def _is_finished_raster(name: str) -> bool:
    """A loose viewable raster whose name marks it a finished render — but not a
    star-layer / intermediate by-product (e.g. `starless.png`)."""
    if "_thn." in name or "." not in name:
        return False
    if hints.is_intermediate_name(name):
        return False
    ext = "." + name.rsplit(".", 1)[-1].lower()
    return ext in _RASTER_EXTS and hints.is_finished_name(name)


# ── name canonicalization + alias table (#12a, #12c) ──────────────────────────

def _alias_path() -> Path:
    return config.INTERNAL_DIR / "ingest_aliases.toml"


def load_aliases() -> dict[str, str]:
    """Per-store known-quirk remaps {source name: canonical target}."""
    p = _alias_path()
    if not p.is_file():
        return {}
    try:
        with p.open("rb") as f:
            return dict(tomllib.load(f).get("alias", {}))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def add_alias(src: str, dst: str) -> None:
    """Remember a remap so future ingests of `src` route to `dst`. Only writer."""
    aliases = load_aliases()
    aliases[src] = dst
    p = _alias_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[alias]"]
    for k, v in sorted(aliases.items()):
        lines.append(f"{json.dumps(k)} = {json.dumps(v)}")   # TOML strings ≈ JSON
    p.write_text("\n".join(lines) + "\n")


def canonical_target(name: str) -> str:
    """Resolve a device folder name to a canonical destination object: alias →
    existing Images/<dir> casing → catalog id casing → normalized name. Folds
    case variants (`m82`→`M82`) and known quirks onto one folder."""
    aliases = load_aliases()
    low = name.lower()
    for k, v in aliases.items():
        if k.lower() == low:
            return v

    norm = fits_object_name(name)
    nlow = norm.lower()

    images = config.IMAGES_DIR
    if images.is_dir():
        for d in images.iterdir():
            # Match an existing folder by normalized name so a device "M 10" folds
            # onto an existing "M10" (or vice-versa) — otherwise dedup would look in
            # the wrong dir and re-import already-present frames.
            if d.is_dir() and (d.name.lower() == nlow
                               or fits_object_name(d.name).lower() == nlow):
                return d.name              # reuse the existing folder's spelling

    try:
        cat = catalog.load_library()
    except Exception:
        cat = {}
    # The user's Library first, then the bundled reference (so a brand-new catalog
    # object — not yet in the Library — still folds onto its canonical id casing).
    for source in (cat, catalog.load_reference()):
        for slug, e in source.items():
            if (e.get("id") or "").lower() == nlow or slug.lower() == nlow:
                return e.get("id") or norm
    return norm


# ── pointing verification (#12b) ──────────────────────────────────────────────

def _parse_sexagesimal(ra: str, dec: str):
    def _val(s):
        parts = [float(x) for x in str(s).replace(":", " ").split()]
        v = parts[0] + (parts[1] / 60 if len(parts) > 1 else 0) + \
            (parts[2] / 3600 if len(parts) > 2 else 0)
        return v, parts[0]
    try:
        ra_h, _ = _val(ra)
        dec_v, dec_first = _val(dec)
        sign = -1 if str(dec).strip().startswith("-") else 1
        return ra_h * 15.0, sign * abs(dec_v)
    except (ValueError, IndexError):
        return None


# IMAGETYP header values vary by capture software; fold them onto our four kinds.
_IMAGETYP_MAP = {
    "light": "light", "light frame": "light", "object": "light", "target": "light",
    "dark": "dark", "dark frame": "dark", "master dark": "dark",
    "flat": "flat", "flat frame": "flat", "flat field": "flat",
    "flatfield": "flat", "master flat": "flat",
    "bias": "bias", "bias frame": "bias", "offset": "bias",
    "offset frame": "bias", "master bias": "bias",
}


def _normalize_imagetyp(raw) -> str | None:
    """Fold a raw IMAGETYP header (ZWO/INDI/Seestar variants) onto
    'light'|'dark'|'flat'|'bias', or None if absent/unrecognized."""
    if not raw:
        return None
    return _IMAGETYP_MAP.get(str(raw).strip().lower())


def frame_info(path: str) -> dict | None:
    """Normalized header facts from a FITS frame, or None.
    Returns {object, imagetyp, filter, ra_deg, dec_deg} — `imagetyp` folded onto
    light/dark/flat/bias (or None), coords in degrees (Seestar RA/DEC, else
    sexagesimal OBJCTRA/OBJCTDEC). Header-only read (no pixel load)."""
    try:
        from astropy.io import fits
    except ImportError:
        return None
    try:
        hdr = fits.getheader(path)
    except Exception:
        return None
    ra_deg = dec_deg = None
    try:
        if hdr.get("RA") is not None and hdr.get("DEC") is not None:
            ra_deg, dec_deg = float(hdr["RA"]), float(hdr["DEC"])
        else:
            ra, dec = hdr.get("OBJCTRA"), hdr.get("OBJCTDEC")
            if ra and dec:
                parsed = _parse_sexagesimal(ra, dec)
                if parsed:
                    ra_deg, dec_deg = parsed
    except (ValueError, TypeError):
        ra_deg = dec_deg = None
    obj = hdr.get("OBJECT")
    return {
        "object": str(obj).strip() if obj not in (None, "") else None,
        "imagetyp": _normalize_imagetyp(hdr.get("IMAGETYP")),
        "filter": (str(hdr.get("FILTER")).strip() or None) if hdr.get("FILTER") else None,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
    }


def frame_radec(path: str):
    """(ra_deg, dec_deg) from a frame header, or None. Thin wrapper over
    `frame_info` kept for the pointing check (#12b)."""
    info = frame_info(path)
    if info and info["ra_deg"] is not None and info["dec_deg"] is not None:
        return info["ra_deg"], info["dec_deg"]
    return None


def _separation_deg(ra1, dec1, ra2, dec2) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    h = (math.sin((d2 - d1) / 2) ** 2
         + math.cos(d1) * math.cos(d2) * math.sin((r2 - r1) / 2) ** 2)
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(h))))


def _slug_for_object(obj: str, cat: dict) -> str | None:
    # Library first, then the bundled reference (catalog objects not yet captured).
    for source in (cat, catalog.load_reference()):
        for slug, e in source.items():
            if (e.get("id") or "") == obj:
                return slug
        if obj in source:
            return obj
    return None


def _nearest(coords: dict, ra: float, dec: float):
    best, best_sep = None, 999.0
    for slug, (cra, cdec) in coords.items():
        s = _separation_deg(ra, dec, cra, cdec)
        if s < best_sep:
            best, best_sep = slug, s
    return best, best_sep


def annotate_pointing(groups: list[IngestGroup], should_cancel=None) -> list[IngestGroup]:
    """Flag groups whose sample frame points >0.15° from the named object, and
    suggest the nearest catalog object. Reads ONE frame per group (worker I/O).
    Degrades to no-op where coords/frames are unavailable."""
    coords = catalog.load_coords()
    if not coords:
        return groups
    try:
        cat = catalog.load_library()
    except Exception:
        cat = {}
    for g in groups:
        if should_cancel and should_cancel():
            break
        if g.kind in ("media", "dark", "flat", "bias", "finished") or not g.ops:
            continue
        radec = frame_radec(g.ops[0].src)
        if radec is None:
            continue
        slug = _slug_for_object(g.object, cat)
        proposed = coords.get(slug) if slug else None
        if proposed is None:
            continue                          # unknown object → unverified
        sep = _separation_deg(radec[0], radec[1], proposed[0], proposed[1])
        if sep <= POINTING_TOL_DEG:
            continue                          # pointing matches the name ✓
        near, near_sep = _nearest(coords, *radec)
        if near and near != slug and near_sep <= POINTING_TOL_DEG:
            near_id = (cat.get(near, {}).get("id")
                       or catalog.load_reference().get(near, {}).get("id") or near)
            g.pointing = f"⚠ {sep:.2f}° off — looks like {near_id}"
            g.suggested = near
        else:
            g.pointing = f"⚠ points {sep:.2f}° from {g.object}"
    return groups


def retarget(group: IngestGroup, new_object: str) -> IngestGroup:
    """Rebuild a group's ops to land under a different destination object (used by
    the remap dropdown). Media groups don't retarget; every per-target kind does."""
    root = config.DATA_ROOT
    dst_dir = _KIND_DIR.get(group.kind, config.lights_dir)(new_object)
    new_flag = not config.target_dir(new_object).is_dir()
    new_ops = []
    for op in group.ops:
        dest = dst_dir / Path(op.src).name
        new_ops.append(replace(op, dest=str(dest),
                               dest_rel=str(dest.relative_to(root)),
                               new_object=new_flag, object=new_object))
    return replace(group, object=new_object, dest_dir=str(dst_dir.relative_to(root)),
                   new_object=new_flag, ops=new_ops, pointing=None, suggested=None)


# ── planning ────────────────────────────────────────────────────────────────

def staging_available() -> bool:
    return _staging().is_dir()


def seestar_available() -> bool:
    return config.find_seestar_myworks() is not None


# kind → per-target destination dir (media routes to MEDIA_DIR, handled separately)
_KIND_DIR = {
    "light": config.lights_dir,
    "dark": config.darks_dir,
    "flat": config.flats_dir,
    "bias": config.biases_dir,
    "stack": config.seestar_stacks_dir,
    "siril-stack": config.stacks_dir,
    "finished": config.finished_dir,
    "working": config.working_files_dir,
}

# M110-store-shaped sources (6b): a subdir named like this under an <object> dir
# (the ~/Astronomy/Images precursor: FITS/<obj>/lights, …), or an <object> dir
# under one of these parents (Finished Images/<obj>, Seestar_stacks/<obj>).
_STORE_SUBDIR_KIND = {
    "lights": "light", "darks": "dark", "flats": "flat", "biases": "bias",
    "stacks": "siril-stack", "seestar-stacks": "stack", "finished": "finished",
}
_STORE_PARENT_KIND = {
    "finished images": "finished", "finished": "finished",
    "seestar_stacks": "stack", "seestar-stacks": "stack",
}
# Working/sandbox dirs that are never content — don't import or recurse into them.
_SKIP_DIRS = {"process", "siril"}


def _emit_files(src_dir: Path, files, kind: str, obj: str, group: str,
                action: str, layout: str) -> list[IngestOp]:
    """Ops routing `files` (names in `src_dir`) into the target subdir for `kind`
    under object `obj`, skipping ones already present at the dest. `group` is the
    grouping/label key shown in the preview.

    **Lights guard (bug A):** ``lights/`` must hold only raw subs. Any file
    routed as ``light`` that isn't a genuine sub (`config.is_light_frame` — a
    processing by-product like ``M27_final.fit`` / ``starless_*.fit`` that a
    flat/mixed source dir put next to the subs) is diverted to ``working_files/``
    (kind ``working``) instead, so it never pollutes ``lights/`` nor gets
    misread by Siril prep as an extra filter."""
    if kind == "light":
        subs = [f for f in files if config.is_light_frame(f)]
        nonsubs = [f for f in files if not config.is_light_frame(f)]
        ops = _emit_one_kind(src_dir, subs, "light", obj, group, action, layout)
        if nonsubs:
            ops += _emit_one_kind(src_dir, nonsubs, "working", obj, group,
                                  action, layout)
        return ops
    return _emit_one_kind(src_dir, files, kind, obj, group, action, layout)


def _emit_one_kind(src_dir: Path, files, kind: str, obj: str, group: str,
                   action: str, layout: str) -> list[IngestOp]:
    """Route `files` into the single target subdir for `kind` (skip already-present)."""
    root = config.DATA_ROOT
    dst_dir = _KIND_DIR[kind](obj)
    existing = set(_all_files(dst_dir))
    new_object = not config.target_dir(obj).is_dir()
    ops: list[IngestOp] = []
    for f in files:
        if f in existing:
            continue
        dest = dst_dir / f
        ops.append(IngestOp(str(src_dir / f), str(dest), kind, group,
                            str(dest.relative_to(root)), new_object, action,
                            _size(src_dir / f), layout, obj))
    return ops


def _detect_layout(src_dir: Path, name: str) -> str | None:
    """Which LAYOUTS recognizer claims this directory (or None to skip it)."""
    if name.lower() in _SKIP_DIRS:
        return None
    # M110-store-shaped (precursor like ~/Astronomy/Images): a known content
    # subdir under an <object>, or an <object> under a known container.
    if name.lower() in _STORE_SUBDIR_KIND or src_dir.parent.name.lower() in _STORE_PARENT_KIND:
        if _all_files(src_dir):
            return "m110-store"
    # Seestar folder conventions.
    if name.endswith("_sub") or is_media_dir(name):
        return "seestar"
    if any(is_stacked_fit(f) for f in _fit_files(src_dir)):
        return "seestar"
    # Anything else holding loose FITS → sort by header.
    if _fit_files(src_dir):
        return "raw-fits"
    return None


def _classify_store_dir(src_dir: Path, name: str, action: str,
                        handled: set) -> list[IngestOp]:
    """Import an M110-store-shaped directory (6b). Maps a content subdir
    (lights/darks/…/stacks/finished) onto the matching M110 target dir; the object
    comes from the parent (FITS/<obj>/lights) or from this dir (Finished Images/<obj>).
    Records every recognized file in `handled` (so the sweep won't re-hold ones that
    were skipped as already-present)."""
    sub_kind = _STORE_SUBDIR_KIND.get(name.lower())
    if sub_kind:
        obj = canonical_target(src_dir.parent.name)
        files = (_fit_files(src_dir) if sub_kind in ("light", "dark", "flat", "bias")
                 else _all_files(src_dir))
        handled.update(files)
        return _emit_files(src_dir, files, sub_kind, obj, name, action, "m110-store")
    kind = _STORE_PARENT_KIND.get(src_dir.parent.name.lower())
    if kind:
        obj = canonical_target(name)
        files = _all_files(src_dir)
        handled.update(files)
        return _emit_files(src_dir, files, kind, obj, name, action, "m110-store")
    return []


def _classify_seestar_dir(src_dir: Path, name: str, action: str,
                          handled: set) -> list[IngestOp]:
    """Seestar folder conventions (the original classifier), with a 6b header
    override: a calibration frame (IMAGETYP=DARK/FLAT/BIAS) inside a lights folder is
    split out to its calibration dir — the header wins over the folder name. Records
    recognized files in `handled`."""
    root = config.DATA_ROOT

    if name.endswith("_sub"):
        obj = canonical_target(name[:-4])      # strip "_sub"; fold case/aliases
        fits = _fit_files(src_dir)
        # A `_sub` folder is a lights folder: the `.fit` are lights; the Seestar's
        # per-sub `.jpg` previews (one beside every sub) are recognized sidecars we
        # intentionally don't import — mark the whole folder handled so they aren't
        # swept into the holding area.
        handled.update(_content_files(src_dir))
        # Bucket by kind, then emit per kind in ONE batch — `_emit_files` lists the
        # destination once per call, so a per-file loop is O(files × dest) (the
        # device-scan slowdown). Seestar lights are `Light_*` by convention, so trust
        # the name and skip the per-frame header read; only header-check odd names.
        buckets: dict[str, list[str]] = {}
        for f in fits:
            if f.startswith("Light_"):
                kind = "light"
            else:
                info = frame_info(str(src_dir / f))
                kind = (info["imagetyp"] if info and info["imagetyp"] in ("dark", "flat", "bias")
                        else "light")
            buckets.setdefault(kind, []).append(f)
        ops: list[IngestOp] = []
        for kind, fs in buckets.items():
            ops += _emit_files(src_dir, fs, kind, obj, name, action, "seestar")
        return ops

    if is_media_dir(name):
        dst_dir = config.MEDIA_DIR / name
        existing = set(_all_files(dst_dir))
        ops = []
        for f in _all_files(src_dir):
            handled.add(f)
            if f in existing:
                continue
            dest = dst_dir / f
            ops.append(IngestOp(str(src_dir / f), str(dest), "media", name,
                                str(dest.relative_to(root)), False, action,
                                _size(src_dir / f), "seestar", name))
        return ops

    # Stack candidate — only if it really holds in-app stacks.
    stacked = [f for f in _fit_files(src_dir) if is_stacked_fit(f)]
    if not stacked:
        return []
    obj = canonical_target(name)
    handled.update(stacked)
    ops = _emit_files(src_dir, stacked, "stack", obj, name, action, "seestar")
    # Also pull the device's preview renders (.jpg/.png) into the same stack folder
    # so the gallery has ready-made images; skip the Seestar's *_thn.* thumbnails.
    previews = [f for f in _all_files(src_dir)
                if "_thn." not in f and f.rsplit(".", 1)[-1].lower() in ("jpg", "jpeg", "png")]
    handled.update(previews)
    ops.extend(_emit_files(src_dir, previews, "stack", obj, name, action, "seestar"))
    return ops


def _classify_raw_dir(src_dir: Path, name: str, action: str,
                      handled: set) -> list[IngestOp]:
    """Header-sort a directory of loose FITS (6b raw-FITS fallback). Each frame is
    routed by its IMAGETYP; the object comes from the OBJECT header, else the
    containing folder name. Frames with neither a usable type nor an object are left
    unclassified (the 6c holding area). Records recognized files in `handled`."""
    buckets: dict[tuple, list[str]] = {}          # (kind, obj) → files
    for f in _fit_files(src_dir):
        info = frame_info(str(src_dir / f))
        kind = info["imagetyp"] if info else None
        obj_hdr = canonical_target(info["object"]) if info and info["object"] else None
        if kind in ("dark", "flat", "bias"):
            obj = obj_hdr or canonical_target(name)
        elif kind == "light" or obj_hdr:
            kind, obj = "light", (obj_hdr or canonical_target(name))
        else:
            continue                              # unclassifiable → 6c holding area
        handled.add(f)                            # recognized (even if skipped as dup)
        buckets.setdefault((kind, obj), []).append(f)
    ops: list[IngestOp] = []
    for (kind, obj), fs in buckets.items():       # one dest listing per (kind, obj)
        ops += _emit_files(src_dir, fs, kind, obj, name, action, "raw-fits")
    return ops


def _emit_unassigned(src_dir: Path, files, name: str, action: str,
                     layout: str) -> list[IngestOp]:
    """Ops routing content files into the `Inbox/<name>/` holding area (6c) for later
    manual assign. kind='unassigned', object='' — skips ones already held."""
    root = config.DATA_ROOT
    dst_dir = config.STAGING_DIR / name
    existing = set(_all_files(dst_dir))
    ops: list[IngestOp] = []
    for f in files:
        if f in existing:
            continue
        dest = dst_dir / f
        ops.append(IngestOp(str(src_dir / f), str(dest), "unassigned", name,
                            str(dest.relative_to(root)), False, action,
                            _size(src_dir / f), layout, ""))
    return ops


def _classify_dir(src_dir: Path, name: str, action: str) -> list[IngestOp]:
    """Classify ONE source directory and return the ops for its NEW files. Picks a
    layout recognizer (6b) — M110-store-shaped, Seestar folder conventions, or a
    raw-FITS header sort — delegates, then **sweeps any unclaimed content file into
    the Inbox/ holding area** (6c — nothing is silently ignored). A directory inside
    this app's own store, or a sandbox (process/siril), is skipped. Reads only."""
    if _in_own_store(src_dir) or name.lower() in _SKIP_DIRS:
        return []
    layout = _detect_layout(src_dir, name)
    handled: set[str] = set()      # files the recognizer claimed (new OR already-present)
    if layout == "m110-store":
        ops = _classify_store_dir(src_dir, name, action, handled)
    elif layout == "seestar":
        ops = _classify_seestar_dir(src_dir, name, action, handled)
    elif layout == "raw-fits":
        ops = _classify_raw_dir(src_dir, name, action, handled)
    else:
        ops = []
    # Claim a loose finished/processed raster (a Siril export dropped in an object
    # folder) the recognizer above didn't take → finished/ for the object. Only for
    # leaf dirs (m110-store/seestar already route their finished outputs); object from
    # the folder name. Without this, such a file falls through to the holding area.
    ops += _claim_loose_finished(src_dir, name, action, handled, layout)
    # Sweep: any content file the recognizer didn't claim → holding area. `handled`
    # (not the emitted ops) is the authority, so files skipped as already-present
    # don't get mistaken for unclassifiable and re-held.
    leftover = [f for f in _content_files(src_dir) if f not in handled]
    ops += _emit_unassigned(src_dir, leftover, name, action, layout or "unknown")
    return ops


def _claim_loose_finished(src_dir: Path, name: str, action: str, handled: set,
                          layout: str | None) -> list[IngestOp]:
    """Route unclaimed loose `*_processed/final/finished` rasters to the object's
    `finished/` tier (object = folder name). Skips dirs already handled by the
    multi-file recognizers (m110-store/seestar handle their own finished outputs)."""
    if layout not in (None, "raw-fits"):
        return []
    files = [f for f in _content_files(src_dir)
             if f not in handled and _is_finished_raster(f)]
    if not files:
        return []
    obj = canonical_target(name)
    handled.update(files)
    return _emit_files(src_dir, files, "finished", obj, name, action, "finished-render")


def _in_own_store(src_dir: Path) -> bool:
    """True if `src_dir` is inside this app's own content tree (`Images/` or the
    hidden internals) — don't re-import the library into itself. The Inbox staging
    area and everything *outside* the content tree (a foreign M110 store, the
    ~/Astronomy/Images precursor) import normally."""
    try:
        rp = src_dir.resolve()
    except OSError:
        rp = src_dir
    for base in (config.IMAGES_DIR, config.INTERNAL_DIR):
        try:
            rp.relative_to(Path(base).resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def _scan_base(base, action: str, should_cancel=None) -> list[IngestOp]:
    """Classify the immediate children of a base dir laid out like the Seestar
    staging/MyWorks structure and return the operations to bring NEW files into the
    collection. Reads only. `action` is 'move' (staging) or 'copy' (device — leaves
    originals in place). `should_cancel` is checked at directory boundaries; if it
    returns true, IngestCancelled is raised (for a responsive Cancel)."""
    if base is None or not base.is_dir():
        return []
    ops: list[IngestOp] = []
    for d in sorted((e for e in base.iterdir()
                     if e.is_dir() and not e.name.startswith(".")),
                    key=lambda p: p.name):
        if should_cancel and should_cancel():
            raise IngestCancelled()
        ops.extend(_classify_dir(d, d.name, action))
    return ops


def scan_directory_plan(root, action: str = "copy", should_cancel=None) -> list[IngestOp]:
    """Dry-run plan for an **arbitrary** directory (ROADMAP 6a). Walks `root`
    recursively and classifies *every* directory by the layout recognizers (6b) —
    M110-store-shaped, Seestar conventions, or a raw-FITS header sort — so a nested
    layout (a per-object tree, device folders, a precursor store) is found, not just
    the immediate children. **Copy** semantics by default, so the source is left
    untouched. Reads only; raises IngestCancelled if `should_cancel()` turns true."""
    root = Path(root) if root is not None else None
    if root is None or not root.is_dir():
        return []
    ops: list[IngestOp] = []
    for dirpath, dirnames, _files in os.walk(root):
        if should_cancel and should_cancel():
            raise IngestCancelled()
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and d.lower() not in _SKIP_DIRS)
        d = Path(dirpath)
        if d.name.startswith("."):
            continue
        ops.extend(_classify_dir(d, d.name, action))
    return ops


def _object_label(op: IngestOp) -> str:
    """Friendly object/category name for an op. Prefers the canonical object the op
    resolved to (6b sets it on every op); falls back to folding the source folder
    name for any legacy op without one (e.g. `m13_sub` → "M13")."""
    if op.object:
        return op.object
    if op.kind == "media":
        return op.group
    base = op.group[:-4] if op.group.endswith("_sub") else op.group
    return canonical_target(base)


def group_ops(ops: list[IngestOp]) -> list[IngestGroup]:
    """Aggregate a flat op list into one IngestGroup per (object, kind) — the unit
    the preview shows and the user selects. Keying on the **resolved object** (not the
    bare source-folder name) is essential for a recursive import (6a): a precursor
    store has a `lights/` (and `stacks/`) folder under *every* object, so keying on the
    folder name collapsed M51/lights + "M81 M82"/lights + … into one bogus row.
    Unassigned/holding ops carry no object, so they fall back to their source folder
    (keeps the holding area per-folder). Order: objects A→Z, media last."""
    by_group: dict[tuple, list[IngestOp]] = {}
    for op in ops:
        key = (op.object or str(Path(op.src).parent), op.kind)
        by_group.setdefault(key, []).append(op)

    groups: list[IngestGroup] = []
    for (_key, kind), gops in by_group.items():
        # destination dir = parent of the first op's destination
        dest_dir = str(Path(gops[0].dest_rel).parent)
        groups.append(IngestGroup(
            group=gops[0].group,        # display label = source folder name (not the key)
            object=_object_label(gops[0]),
            kind=kind,
            frames=len(gops),
            size_bytes=sum(o.size_bytes for o in gops),
            dest_dir=dest_dir,
            new_object=any(o.new_object for o in gops),
            action=gops[0].action,
            ops=gops,
            layout=gops[0].layout,
        ))
    # media rows after catalog objects, then by natural catalog order (M1, M2, …
    # M100 — not M1, M10, M100), then kind
    groups.sort(key=lambda g: (g.kind == "media",
                               catalog.catalog_sort_key(g.object), g.kind))
    return groups


def scan_staging_plan(should_cancel=None) -> list[IngestOp]:
    """Dry-run plan for the Inbox staging area (moves). Reads only."""
    return _scan_base(_staging(), "move", should_cancel)


def scan_seestar_plan(should_cancel=None) -> list[IngestOp]:
    """Dry-run plan for a mounted Seestar's MyWorks (copies — leaves the device
    untouched). Empty if no Seestar is mounted. Reads only."""
    return _scan_base(config.find_seestar_myworks(), "copy", should_cancel)


# ── holding area (6c): manual assign of unclassifiable files ───────────────────

def scan_holding(should_cancel=None) -> list[IngestOp]:
    """List the Inbox/ holding area's content files as unassigned ops (6c), for the
    manual-assign panel. group = the top-level subfolder under Inbox (or '(loose)'
    for files sitting directly in Inbox). dest is a placeholder until `assign` routes
    them. Reads only; raises IngestCancelled if `should_cancel()` turns true."""
    base = config.STAGING_DIR
    if not base.is_dir():
        return []
    root = config.DATA_ROOT
    ops: list[IngestOp] = []
    for dirpath, dirnames, files in os.walk(base):
        if should_cancel and should_cancel():
            raise IngestCancelled()
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        d = Path(dirpath)
        rel = d.relative_to(base)
        group = "(loose)" if rel == Path(".") else rel.parts[0]
        for f in sorted(files):
            if not _is_content_file(f):
                continue
            src = d / f
            ops.append(IngestOp(str(src), str(src), "unassigned", group,
                                str(src.relative_to(root)), False, "move",
                                _size(src), "holding", ""))
    return ops


def holding_count() -> int:
    """Number of content files currently in the Inbox/ holding area (cheap)."""
    base = config.STAGING_DIR
    if not base.is_dir():
        return 0
    return sum(1 for dp, _dn, files in os.walk(base) for f in files
               if _is_content_file(f))


def assign(group: IngestGroup, object: str, kind: str) -> IngestGroup:
    """Rebuild a held (unassigned) group's ops to **move** its files into the content
    tree under `object` as `kind` (6c manual assign). Mirrors `retarget` but sets the
    kind and move semantics; `apply_ops` remains the only writer."""
    root = config.DATA_ROOT
    obj = canonical_target(object)
    dst_dir = (config.MEDIA_DIR / obj if kind == "media"
               else _KIND_DIR[kind](obj))
    new_flag = kind != "media" and not config.target_dir(obj).is_dir()
    new_ops = []
    for op in group.ops:
        dest = dst_dir / Path(op.src).name
        new_ops.append(replace(op, dest=str(dest), kind=kind, object=obj,
                               action="move", new_object=new_flag,
                               dest_rel=str(dest.relative_to(root))))
    return replace(group, object=obj, kind=kind,
                   dest_dir=str(dst_dir.relative_to(root)),
                   new_object=new_flag, ops=new_ops)


def _digest(path: str) -> str:
    """SHA-256 of a file's bytes (streamed; cheap enough — only run on a name
    collision, not on every op)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _same_content(a: str, b: str) -> bool:
    """True if two files are byte-identical (size short-circuits the hash)."""
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        return _digest(a) == _digest(b)
    except OSError:
        return False


def _free_dest(dest: str) -> str:
    """A non-colliding destination path: `dest` if free, else `stem_1.ext`,
    `stem_2.ext`, … (preserves the original filename, just disambiguates)."""
    if not os.path.exists(dest):
        return dest
    stem, ext = os.path.splitext(dest)
    i = 1
    while os.path.exists(f"{stem}_{i}{ext}"):
        i += 1
    return f"{stem}_{i}{ext}"


def apply_ops(ops: list[IngestOp], progress=None, should_cancel=None) -> dict:
    """Perform the moves/copies. THIS WRITES INTO Images/ — callers must confirm.

    Creates destination dirs. **Collision handling is content-aware** (replaces the
    old skip-by-name-only): on a destination filename clash, a byte-identical file
    is a true **duplicate** → skipped; a same-name but **distinct** file is written
    under a disambiguating `_N` suffix (never a lossy rename, never an overwrite).
    `progress(i, total)` is called after each op. `should_cancel()` is checked
    before each op; cancelling stops cleanly (files already done stay done — safe,
    since a re-scan simply lists whatever's still missing).
    """
    moved = skipped = 0
    total = len(ops)
    cancelled = False
    for i, op in enumerate(ops, 1):
        if should_cancel and should_cancel():
            cancelled = True
            break
        os.makedirs(os.path.dirname(op.dest), exist_ok=True)
        if os.path.exists(op.dest) and _same_content(op.src, op.dest):
            skipped += 1                    # identical bytes already present
        else:
            dest = _free_dest(op.dest)      # free → op.dest; distinct clash → _N
            if op.action == "copy":
                # Bytes only (no copystat): copying from an SMB-mounted Seestar,
                # copying the source's flags/xattrs onto the destination raises
                # EPERM on macOS. Write to a temp then atomically rename so an
                # interrupted copy never leaves a partial file that a re-scan
                # would treat as "already present".
                tmp = dest + ".part"
                try:
                    shutil.copyfile(op.src, tmp)
                    os.replace(tmp, dest)
                except BaseException:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                    raise
            else:
                shutil.move(op.src, dest)
            moved += 1
        if progress:
            progress(i, total)
    return {"moved": moved, "skipped": skipped, "cancelled": cancelled}


def plan_lights_cleanup(targets: list[str] | None = None) -> list[IngestOp]:
    """Read-only plan (bug C): find non-sub ``.fit`` files sitting in any target's
    ``lights/`` and plan to **move** them to that target's ``working_files/``.

    A ``lights/`` folder must contain only raw subs (`config.is_light_frame`); an
    earlier import from a flat/mixed source (e.g. the ~/Astronomy ``FITS/<obj>/``
    dirs that mingle subs with Siril/PixInsight by-products) can leave processing
    products there. These moves are intra-store `os.rename`-cheap; `apply_ops` is
    the only writer and callers must confirm. Idempotent — a file already present
    in ``working_files/`` is skipped by `apply_ops`.
    """
    root = config.DATA_ROOT
    images = config.IMAGES_DIR
    if not images.is_dir():
        return []
    names = targets if targets is not None else [
        d.name for d in sorted(images.iterdir()) if d.is_dir()]
    ops: list[IngestOp] = []
    for name in names:
        ldir = config.lights_dir(name)
        if not ldir.is_dir():
            continue
        for f in sorted(ldir.iterdir()):
            if not (f.is_file() and f.suffix.lower() == ".fit"):
                continue
            if config.is_light_frame(f.name):
                continue                        # genuine sub — leave it
            dest = config.working_files_dir(name) / f.name
            ops.append(IngestOp(str(f), str(dest), "working", name,
                                str(dest.relative_to(root)), action="move",
                                size_bytes=_size(f), layout="cleanup",
                                object=name))
    return ops
